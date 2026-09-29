# -*- coding: utf-8 -*-
"""
实时屏幕影像源

优先：scrcpy + Windows 命名管道 + PyAV 解码 H.264（约 30 FPS）
回退：RAW screencap 连续抓帧（约 1.5 FPS，无 scrcpy/失败时用）
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
PIPE_NAME = "\\\\.\\pipe\\qishui_scrspy_live"


def _popen_flags() -> dict:
    return {"creationflags": CREATE_NO_WINDOW} if os.name == "nt" else {}


def app_dir() -> Path:
    """运行目录：exe 所在目录（打包后），或源码目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_scrcpy(start_dir: Optional[Path] = None) -> Optional[Path]:
    bases = []
    if start_dir:
        bases.append(Path(start_dir))
    bases.append(app_dir())
    # 源码调试时可能在上一级
    bases.append(app_dir().parent)
    bases.append(Path.cwd())
    tried = []
    for base in bases:
        for sub in (
            Path("scrcpy") / "scrcpy.exe",
            Path("dist") / "scrcpy" / "scrcpy.exe",
            Path("scrcpy.exe"),
        ):
            p = base / sub
            tried.append(str(p))
            try:
                if p.is_file():
                    return p
            except Exception:
                pass
    # 记录搜索路径便于排查
    find_scrcpy.tried = tried  # type: ignore
    return None


class _PipeReader:
    """给 PyAV 当 file-like，从命名管道持续读字节。"""

    def __init__(self, handle):
        self.handle = handle
        self.closed = False

    def read(self, n: int = -1) -> bytes:
        if self.closed:
            return b""
        if n is None or n < 0:
            n = 65536
        try:
            import win32file

            _hr, data = win32file.ReadFile(self.handle, max(int(n), 1))
            return data or b""
        except Exception:
            return b""

    def seek(self, *a, **k):
        return 0

    def tell(self):
        return 0

    def close(self):
        self.closed = True


class LiveScreen:
    def __init__(
        self,
        adb: str,
        serial: Optional[str] = None,
        size: str = "",
        on_log: Optional[Callable[[str], None]] = None,
        scrcpy_path: Optional[str] = None,
        screen_off: bool = False,
    ):
        self.adb = adb
        self.serial = serial
        self.size = size
        self.on_log = on_log or (lambda s: None)
        self.scrcpy_path = Path(scrcpy_path) if scrcpy_path else find_scrcpy()
        self.screen_off = screen_off
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._seq = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.mode = "idle"
        self.fps = 0.0
        self._fps_n = 0
        self._fps_t0 = time.time()

    def _adb_args(self, args: list[str]) -> list[str]:
        if self.serial:
            return [self.adb, "-s", self.serial, *args]
        return [self.adb, *args]

    def _log(self, msg: str) -> None:
        try:
            self.on_log(msg)
        except Exception:
            pass

    def latest(self) -> Optional[np.ndarray]:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def latest_seq(self) -> int:
        return self._seq

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=4)
            self._thread = None
        self.mode = "idle"

    def _put(self, frame: np.ndarray) -> None:
        with self._lock:
            self._frame = frame
            self._seq += 1
        self._fps_n += 1
        now = time.time()
        dt = now - self._fps_t0
        if dt >= 1.0:
            self.fps = self._fps_n / dt
            self._fps_t0 = now
            self._fps_n = 0

    def _run(self) -> None:
        fps_t0 = time.time()
        fps_n = 0
        while not self._stop.is_set():
            try:
                if self.scrcpy_path and os.name == "nt":
                    n = self._run_scrcpy()
                    fps_n += n
                    if n == 0:
                        time.sleep(1.0)  # scrcpy 秒退时避免忙等
                else:
                    self._log("无 scrcpy，使用截图模式")
                    fps_n += self._run_screencap_loop()
            except Exception as e:
                self._log(f"影像源异常: {type(e).__name__}: {e}")
                time.sleep(1.0)
            if self._stop.is_set():
                break
            # 短暂回退截图，避免完全黑屏
            try:
                self.mode = "screencap"
                for _ in range(3):
                    if self._stop.is_set():
                        break
                    if self._capture_once():
                        fps_n += 1
                    time.sleep(0.2)
            except Exception as e:
                self._log(f"截图失败: {e}")
                time.sleep(1.0)
            now = time.time()
            if now - fps_t0 >= 2.0 and fps_n:
                self.fps = fps_n / (now - fps_t0)
                fps_t0, fps_n = now, 0

    # ---------------- scrcpy H.264 ----------------
    def _run_scrcpy(self) -> int:
        try:
            import win32file
            import win32pipe
        except ImportError:
            self._log("缺少 pywin32，无法使用 scrcpy 管道")
            return self._run_screencap_loop()

        self.mode = "scrcpy"
        self._log(f"启动 scrcpy 实时流 ({self.scrcpy_path.name})")
        pipe = win32pipe.CreateNamedPipe(
            PIPE_NAME,
            win32pipe.PIPE_ACCESS_INBOUND,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            1,
            1 << 22,
            1 << 22,
            0,
            None,
        )
        cmd = [
            str(self.scrcpy_path),
            "--no-window",
            f"--record={PIPE_NAME}",
            "--record-format=mkv",
            "--max-fps=30",
            "--video-bit-rate=8M",
            "--stay-awake",
        ]
        # 限制分辨率（格式 WxH，保持宽高比）降低带宽
        if self.size and "x" in self.size.lower():
            try:
                w_s, h_s = self.size.lower().split("x", 1)
                max_side = max(int(w_s), int(h_s))
                if max_side > 0:
                    cmd += [f"--max-size={max_side}"]
            except Exception:
                pass
        # 熄屏运行：手机屏幕关掉，但仍推流给本程序（scrcpy 官方能力）
        if self.screen_off:
            cmd.append("--turn-screen-off")
            cmd.append("--no-power-on")
        if self.serial:
            cmd[1:1] = ["-s", self.serial]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **_popen_flags())
        frames = 0
        started = time.time()
        box = None
        try:
            win32pipe.ConnectNamedPipe(pipe, None)
            self._log("scrcpy 管道已连接")
            import av

            box = av.open(_PipeReader(pipe), format="matroska", mode="r")
            for frame in box.decode(box.streams.video[0]):
                if self._stop.is_set():
                    break
                img = frame.to_ndarray(format="bgr24")
                self._put(img)
                frames += 1
                if frames == 1:
                    self._log(f"scrcpy 出帧 {img.shape[1]}x{img.shape[0]}")
                # 一次会话最长 4 分钟后重启（防止句柄泄漏）
                if time.time() - started > 240:
                    break
            self._log(f"scrcpy 会话结束，共 {frames} 帧")
            return frames
        finally:
            try:
                if box is not None:
                    box.close()
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass
            try:
                win32file.CloseHandle(pipe)
            except Exception:
                pass

    # ---------------- 截图回退 ----------------
    def _run_screencap_loop(self) -> int:
        self.mode = "screencap"
        self._log("实时影像：RAW screencap")
        n = 0
        while not self._stop.is_set():
            t0 = time.time()
            if self._capture_once():
                n += 1
            dt = time.time() - t0
            if dt < 0.05:
                time.sleep(0.05 - dt)
        return n

    def _capture_once(self) -> bool:
        r = subprocess.run(
            self._adb_args(["exec-out", "screencap"]),
            capture_output=True, timeout=15, **_popen_flags(),
        )
        data = r.stdout or b""
        if len(data) > 16:
            frame = self._parse_raw(data)
            if frame is not None:
                self._put(frame)
                return True
        r = subprocess.run(
            self._adb_args(["exec-out", "screencap", "-p"]),
            capture_output=True, timeout=15, **_popen_flags(),
        )
        if not r.stdout:
            return False
        frame = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return False
        self._put(frame)
        return True

    @staticmethod
    def _parse_raw(data: bytes) -> Optional[np.ndarray]:
        try:
            w, h, fmt = struct.unpack_from("<III", data, 0)
            if not (0 < w < 8000 and 0 < h < 8000):
                return None
            for offset in (12, 16):
                need = offset + w * h * 4
                if len(data) >= need:
                    pix = np.frombuffer(data, np.uint8, count=w * h * 4, offset=offset)
                    rgba = np.reshape(pix, (h, w, 4))
                    return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        except Exception:
            return None
        return None
