# -*- coding: utf-8 -*-
"""
汽水音乐 · 自动看广告 GUI 版
实时手机截图预览 + OCR 识别信息 + 自动点击 + 运行日志
"""

from __future__ import annotations

import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageTk

from live_screen import LiveScreen, app_dir, find_scrcpy

# ---------------- 控制台/编码 ----------------
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 延迟导入 OCR（启动更快，也方便在未装包时提示）
RapidOCR = None

# ========================= 配置 =========================
TARGETS = ["领取奖励", "领取", "继续观看", "领取成功", "我知道了"]
OCR_SCORE = 0.55
OCR_MAX_WIDTH = 720
POLL_INTERVAL = 1.2
CLICK_COOLDOWN = 1.8
# 点击坐标随机抖动（像素），及等待时间浮动，降低脚本特征
CLICK_JITTER = 6
SCREEN_W = 0  # 运行时写入
SCREEN_H = 0
MISS_BACK_THRESHOLD = 6
NO_COOLDOWN_TARGETS = {"领取成功", "领取奖励", "领取", "我知道了"}
CENTER_TARGETS = {"领取奖励", "领取"}
# 「继续观看」以底部大按钮为准（顶部可能有同名关闭/跳过）
BOTTOM_TARGETS = {"继续观看"}

# ROI 放宽：按钮常在底部，旧值会把 y>0.92 的「领取奖励」滤掉导致只识别不点击
TARGET_ROI = {
    "领取奖励": {"x": (0.10, 0.90), "y": (0.10, 0.98)},
    "领取": {"x": (0.10, 0.90), "y": (0.10, 0.98)},
    "继续观看": {"x": (0.05, 0.98), "y": (0.02, 0.98)},
    "领取成功": {"x": (0.00, 1.00), "y": (0.00, 1.00)},
    "我知道了": {"x": (0.10, 0.90), "y": (0.15, 0.98)},
}

OCR_FIX = {
    "领収": "领取", "领职": "领取", "领敢": "领取", "领联": "领取",
    "奨": "奖", "奬": "奖", "勵": "励",
    "继渎": "继续", "继读": "继续", "観看": "观看", "观着": "观看",
}
COUNTDOWN_PAT = re.compile(
    r"(秒后|后再|再看|再闯|后可|后领|后得|后获得|试看|完整观看|观看完整)"
)

SCRIPT_DIR = Path(__file__).resolve().parent
DEBUG_DIR = SCRIPT_DIR / "debug_clicks"
# =========================================================


# --------------------------- ADB ---------------------------

def find_adb() -> str:
    hit = which("adb") or which("adb.exe")
    if hit:
        return hit
    for p in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "platform-tools" / "adb.exe",
        Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools" / "adb.exe",
        Path(r"C:\platform-tools\adb.exe"),
        SCRIPT_DIR / "platform-tools" / "adb.exe",
        SCRIPT_DIR / "adb.exe",
    ):
        try:
            if p.is_file():
                return str(p)
        except Exception:
            pass
    return "adb"


ADB = find_adb()
DEVICE_SERIAL: Optional[str] = None

# Windows: 调用 adb 时不弹出黑色控制台窗口
CREATE_NO_WINDOW = 0x08000000
_NO_WINDOW = {"creationflags": CREATE_NO_WINDOW} if os.name == "nt" else {}


def adb_args(args: list[str]) -> list[str]:
    if DEVICE_SERIAL:
        return [ADB, "-s", DEVICE_SERIAL, *args]
    return [ADB, *args]


def run_adb(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(adb_args(args), capture_output=True, timeout=timeout, **_NO_WINDOW)


def run_adb_text(args: list[str], timeout: int = 15) -> str:
    r = run_adb(args, timeout=timeout)
    return (r.stdout or b"").decode("utf-8", errors="replace").strip()


def screenshot() -> Optional[np.ndarray]:
    r = run_adb(["exec-out", "screencap", "-p"], timeout=20)
    if r.returncode != 0 or not r.stdout:
        return None
    return cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)


def collect_device_info() -> dict:
    """采集手机基础信息：机型/系统/分辨率/电量/充电/网络。"""
    info: dict = {
        "model": "?",
        "brand": "?",
        "android": "?",
        "resolution": "?",
        "battery": "?",
        "charging": "?",
        "network": "?",
        "ip": "?",
        "wifi": "?",
    }
    try:
        info["model"] = run_adb_text(["shell", "getprop", "ro.product.model"]) or "?"
        info["brand"] = run_adb_text(["shell", "getprop", "ro.product.brand"]) or "?"
        info["android"] = run_adb_text(["shell", "getprop", "ro.build.version.release"]) or "?"
    except Exception:
        pass
    try:
        w, h = get_device_size()
        info["resolution"] = f"{w}x{h}"
    except Exception:
        pass
    # 电量 / 充电
    try:
        bat = run_adb_text(["shell", "dumpsys", "battery"])
        m = re.search(r"level:\s*(\d+)", bat)
        if m:
            info["battery"] = f"{m.group(1)}%"
        st = re.search(r"status:\s*(\d+)", bat)
        # 2=charging 5=full
        if st:
            code = st.group(1)
            info["charging"] = {"2": "充电中", "5": "已充满", "3": "放电", "4": "未充电"}.get(code, f"状态{code}")
        if "AC powered: true" in bat or "USB powered: true" in bat or "Wireless powered: true" in bat:
            if info["charging"] in ("?", "放电", "未充电"):
                info["charging"] = "充电中"
    except Exception:
        pass
    # 网络：WiFi 名 / IP
    try:
        wifi = run_adb_text(["shell", "dumpsys", "wifi"])
        m = re.search(r"mWifiInfo SSID:\s*(.+?),", wifi)
        if not m:
            m = re.search(r'SSID:\s*"?([^",\n]+)"?', wifi)
        if m:
            info["wifi"] = m.group(1).strip().strip('"')
        ip = run_adb_text(["shell", "ip", "-f", "inet", "addr", "show", "wlan0"])
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", ip)
        if m:
            info["ip"] = m.group(1)
            info["network"] = f"WiFi {info['wifi']}" if info["wifi"] not in ("?", "") else "WiFi"
        else:
            # 蜂窝
            cell = run_adb_text(["shell", "ip", "-f", "inet", "addr", "show", "rmnet_data0"])
            m2 = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", cell)
            if m2:
                info["ip"] = m2.group(1)
                info["network"] = "移动数据"
            else:
                info["network"] = "未联网"
    except Exception:
        pass
    return info


def get_device_size() -> tuple[int, int]:
    """读取真机分辨率，优先 Physical size。"""
    txt = run_adb_text(["shell", "wm", "size"])
    m = re.search(r"(\d+)\s*x\s*(\d+)", txt or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return 1080, 2340


def map_to_device(x: float, y: float, fw: int, fh: int, dw: int, dh: int) -> tuple[int, int]:
    """把影像帧坐标换算成真机点击坐标。"""
    if fw <= 0 or fh <= 0:
        return int(x), int(y)
    return int(round(x * dw / fw)), int(round(y * dh / fh))


def tap(x: int, y: int) -> None:
    """点击并加小幅随机抖动，降低固定坐标点击特征。"""
    time.sleep(random.uniform(0.03, 0.15))
    jx = random.randint(-CLICK_JITTER, CLICK_JITTER)
    jy = random.randint(-CLICK_JITTER, CLICK_JITTER)
    tx, ty = int(x) + jx, int(y) + jy
    if SCREEN_W:
        tx = max(2, min(tx, SCREEN_W - 2))
    if SCREEN_H:
        ty = max(2, min(ty, SCREEN_H - 2))
    run_adb(["shell", "input", "tap", str(tx), str(ty)])


def human_sleep(base: float, spread: float = 0.35) -> None:
    """在 base 附近随机浮动的等待。"""
    time.sleep(max(0.15, base + random.uniform(-spread, spread)))


def press_back() -> None:
    run_adb(["shell", "input", "keyevent", "4"])


# --------------------------- OCR ---------------------------

_ocr = None


def get_ocr():
    global _ocr, RapidOCR
    if _ocr is None:
        if RapidOCR is None:
            from rapidocr_onnxruntime import RapidOCR as _R
            RapidOCR = _R
        _ocr = RapidOCR()
    return _ocr


def normalize(text: str) -> str:
    s = (text or "").strip().replace(" ", "").replace("　", "")
    s = re.sub(r"[×xX✕✖·•|丨\[\]【】()（）]+$", "", s)
    s = re.sub(r"^[×xX✕✖·•|丨]+", "", s)
    for a, b in OCR_FIX.items():
        s = s.replace(a, b)
    return s


def is_countdown_noise(recognized: str) -> bool:
    s = normalize(recognized)
    if not s:
        return True
    if re.search(r"\d+\s*秒", s) or COUNTDOWN_PAT.search(s):
        return True
    return False


def text_hit(recognized: str, target: str) -> bool:
    a, b = normalize(recognized), normalize(target)
    if not a or not b:
        return False
    if is_countdown_noise(a):
        return False
    if len(b) <= 2:
        return a == b or a == b + "了"
    if a == b:
        return True
    if b in a and len(a) <= len(b) + 4:
        return True
    if len(b) >= 4 and any(b[:i] + b[i + 1 :] in a for i in range(len(b))):
        return True
    return False


@dataclass
class OcrBox:
    text: str
    score: float
    cx: float
    cy: float
    matched: str = ""


def run_ocr(screen: np.ndarray) -> list[OcrBox]:
    h, w = screen.shape[:2]
    scale = 1.0
    img = screen
    if w > OCR_MAX_WIDTH:
        scale = OCR_MAX_WIDTH / w
        img = cv2.resize(screen, (OCR_MAX_WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)
    result, _ = get_ocr()(img)
    boxes: list[OcrBox] = []
    if not result:
        return boxes
    for item in result:
        pts, text, score = item[0], item[1], float(item[2])
        if score < OCR_SCORE:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx = (min(xs) + max(xs)) / 2 / scale
        cy = (min(ys) + max(ys)) / 2 / scale
        boxes.append(OcrBox(str(text), score, cx, cy))
    return boxes


def in_roi(target: str, cx: float, cy: float, sw: int, sh: int) -> bool:
    roi = TARGET_ROI.get(target)
    if not roi:
        return True
    x0, x1 = roi["x"]
    y0, y1 = roi["y"]
    return x0 * sw <= cx <= x1 * sw and y0 * sh <= cy <= y1 * sh


def is_live_room(boxes: list[OcrBox], sh: int) -> bool:
    """仅在顶部出现明确直播间特征时返回 True，避免音乐页「关注」误判。"""
    top = sh * 0.18
    has_follow = False
    has_live = False
    for b in boxes:
        if b.cy > top:
            continue
        t = normalize(b.text)
        if "更多直播" in t or t == "正在直播" or t.endswith("的直播间"):
            return True
        if t == "关注":
            has_follow = True
        if "直播" in t:
            has_live = True
    return has_follow and has_live


def is_in_ad(boxes: list[OcrBox]) -> bool:
    for b in boxes:
        t = normalize(b.text)
        if t == "广告" or "秒后可领" in t or re.search(r"\d+\s*秒后", t):
            return True
    return False


def parse_countdown_seconds(boxes: list[OcrBox]) -> Optional[int]:
    """从「03秒后可领奖励 / 再看15秒」等文案解析剩余秒数。"""
    best: Optional[int] = None
    for b in boxes:
        t = normalize(b.text)
        # 03秒后可领奖励 / 5秒后
        m = re.search(r"(\d{1,3})\s*秒后", t)
        if m:
            n = int(m.group(1))
            if 0 <= n <= 180:
                best = n if best is None else min(best, n)
            continue
        # 再看15秒继续解锁
        m = re.search(r"再看\s*(\d{1,3})\s*秒", t)
        if m:
            n = int(m.group(1))
            if 0 <= n <= 180:
                best = n if best is None else min(best, n)
    return best


# 只关注这几个目标（以及广告/直播间状态词）
FOCUS_WORDS = ("领取", "继续", "观看", "成功", "知道", "广告", "关注", "直播", "反馈")


def is_focus_text(text: str) -> bool:
    t = normalize(text)
    if not t:
        return False
    if any(w in t for w in FOCUS_WORDS):
        return True
    # 倒计时也算状态信息
    if re.search(r"\d+\s*秒", t):
        return True
    return False


def filter_focus(boxes: list[OcrBox], sw: int, sh: int) -> list[OcrBox]:
    """只保留与按钮/状态相关的识别结果，并标记命中目标。"""
    for target in TARGETS:
        for b in boxes:
            if text_hit(b.text, target) and in_roi(target, b.cx, b.cy, sw, sh):
                if not b.matched:
                    b.matched = target
    return [b for b in boxes if b.matched or is_focus_text(b.text)]


def pick_click(boxes: list[OcrBox], sw: int, sh: int) -> Optional[tuple[str, OcrBox, float]]:
    """返回 (target, box, score)。优先级即 TARGETS 顺序。"""
    rejects: list[str] = []
    for target in TARGETS:
        cands = []
        for b in boxes:
            if not text_hit(b.text, target):
                continue
            if not in_roi(target, b.cx, b.cy, sw, sh):
                rejects.append(f"{target}:{b.text!r}@({int(b.cx)},{int(b.cy)}) 出界")
                continue
            cands.append(b)
        if not cands:
            continue
        if target in CENTER_TARGETS:
            mx, my = sw * 0.5, sh * 0.5
            cands.sort(key=lambda b: (-b.score, (b.cx - mx) ** 2 + (b.cy - my) ** 2))
        elif target in BOTTOM_TARGETS:
            # 优先底部按钮，避免点到顶部同名「继续观看」
            cands.sort(key=lambda b: (-b.score, -b.cy, abs(b.cx - sw * 0.5)))
        else:
            cands.sort(key=lambda b: (-b.score, b.cy, -b.cx))
        best = cands[0]
        best.matched = target
        pick_click.last_rejects = []
        return target, best, best.score
    # 便于排查：识别到了但 ROI/文案没过
    if rejects:
        pick_click.last_rejects = rejects[:6]
    else:
        pick_click.last_rejects = []
    return None


pick_click.last_rejects = []  # type: ignore


# --------------------------- GUI ---------------------------

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except Exception as e:  # pragma: no cover
    print("无法加载 tkinter:", e)
    sys.exit(1)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("汽水音乐 · 自动看广告 GUI")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.configure(bg="#1e1f26")

        self.msg_q: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.running = False
        self.clicks = 0
        self.rounds = 0
        self.started_at = 0.0
        self._photo = None
        self._last_frame: Optional[np.ndarray] = None
        self.log_buf = deque(maxlen=800)

        self._build_style()
        self._build_ui()
        self.after(120, self._poll_queue)

        # 启动时探测设备 + 周期刷新手机信息
        self.after(200, self._refresh_device)
        self.after(400, self._refresh_device_info)
        self.after(8000, self._schedule_device_info)

    # ---------- UI ----------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#1e1f26")
        style.configure("TLabelframe", background="#1e1f26", foreground="#e8e8ef")
        style.configure("TLabelframe.Label", background="#1e1f26", foreground="#a8b1ff")
        style.configure("TLabel", background="#1e1f26", foreground="#e8e8ef")
        style.configure("Header.TLabel", background="#1e1f26", foreground="#ffffff", font=("Segoe UI", 14, "bold"))
        style.configure("Status.TLabel", background="#1e1f26", foreground="#9aa3b2", font=("Consolas", 10))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", background="#2a2c36", fieldbackground="#2a2c36",
                        foreground="#e8e8ef", rowheight=24)
        style.configure("Treeview.Heading", background="#3a3d4a", foreground="#ffffff")

    def _build_ui(self):
        # 顶栏
        top = ttk.Frame(self, padding=(12, 10))
        top.pack(fill="x")
        ttk.Label(top, text="汽水音乐 · 自动看广告", style="Header.TLabel").pack(side="left")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(top, textvariable=self.status_var, style="Status.TLabel").pack(side="left", padx=16)

        btns = ttk.Frame(top)
        btns.pack(side="right")
        self.btn_start = ttk.Button(btns, text="▶ 启动", style="Accent.TButton", command=self.start_bot)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(btns, text="⏹ 停止", command=self.stop_bot, state="disabled")
        self.btn_stop.pack(side="left", padx=4)
        self.screen_off_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btns, text="熄屏运行", variable=self.screen_off_var).pack(side="left", padx=6)
        ttk.Button(btns, text="刷新设备", command=self._refresh_device).pack(side="left", padx=4)
        ttk.Button(btns, text="保存截图", command=self._save_shot).pack(side="left", padx=4)
        ttk.Button(btns, text="清空日志", command=self._clear_log).pack(side="left", padx=4)

        # 主体
        main = ttk.Frame(self, padding=(12, 0, 12, 8))
        main.pack(fill="both", expand=True)

        # 左：截图预览
        left = ttk.LabelFrame(main, text="手机实时影像（H264 流）", padding=8)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self.preview = tk.Label(left, bg="#12131a", text="尚未截图\n启动后自动刷新",
                                fg="#6b7280", font=("Segoe UI", 12), anchor="center")
        self.preview.pack(fill="both", expand=True)
        self.preview_info = tk.StringVar(value="分辨率: -   缩放: -")
        ttk.Label(left, textvariable=self.preview_info, style="Status.TLabel").pack(fill="x", pady=(6, 0))

        # 右：识别信息
        right = ttk.Frame(main)
        right.pack(side="right", fill="both", expand=False)
        right.configure(width=430)

        # WiFi ADB
        wf = ttk.LabelFrame(right, text="WiFi ADB", padding=8)
        wf.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(wf)
        row.pack(fill="x")
        ttk.Label(row, text="IP:").pack(side="left")
        self.wifi_ip_var = tk.StringVar(value="192.168.")
        self.wifi_ip_entry = ttk.Entry(row, textvariable=self.wifi_ip_var, width=18)
        self.wifi_ip_entry.pack(side="left", padx=4)
        ttk.Button(row, text="连接", command=self._wifi_connect).pack(side="left", padx=2)
        ttk.Button(row, text="开启无线", command=self._wifi_enable).pack(side="left", padx=2)
        ttk.Button(row, text="断开", command=self._wifi_disconnect).pack(side="left", padx=2)
        self.wifi_status_var = tk.StringVar(value="可先 USB 连接后点「开启无线」，再填手机 IP 连接")
        ttk.Label(wf, textvariable=self.wifi_status_var, wraplength=400, foreground="#9aa3b2").pack(fill="x", pady=(4, 0))

        # 手机信息
        devf = ttk.LabelFrame(right, text="手机信息", padding=8)
        devf.pack(fill="x", pady=(0, 8))
        self.device_var = tk.StringVar(value="设备信息获取中…")
        ttk.Label(devf, textvariable=self.device_var, wraplength=400, justify="left").pack(fill="x")

        # 统计
        statf = ttk.LabelFrame(right, text="运行统计", padding=8)
        statf.pack(fill="x", pady=(0, 8))
        self.stat_var = tk.StringVar(value="点击 0 次 · 轮次 0 · 用时 0s · ADB: 未检测")
        ttk.Label(statf, textvariable=self.stat_var, wraplength=400).pack(fill="x")

        # OCR 表格
        ocrf = ttk.LabelFrame(right, text="重点识别（领取/继续观看/成功等）", padding=8)
        ocrf.pack(fill="both", expand=True, pady=(0, 8))
        cols = ("text", "score", "pos", "hit")
        self.tree = ttk.Treeview(ocrf, columns=cols, show="headings", height=12)
        self.tree.heading("text", text="识别文本")
        self.tree.heading("score", text="置信度")
        self.tree.heading("pos", text="坐标")
        self.tree.heading("hit", text="命中")
        self.tree.column("text", width=170, anchor="w")
        self.tree.column("score", width=70, anchor="center")
        self.tree.column("pos", width=110, anchor="center")
        self.tree.column("hit", width=70, anchor="center")
        self.tree.pack(fill="both", expand=True)

        # 日志
        logf = ttk.LabelFrame(right, text="运行日志", padding=8)
        logf.pack(fill="both", expand=False)
        self.log_text = tk.Text(logf, height=10, bg="#15161c", fg="#c9d1d9",
                                insertbackground="#c9d1d9", font=("Consolas", 9),
                                relief="flat", wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    # ---------- helpers ----------
    def log(self, msg: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.log_buf.append(line)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        if level == "click":
            self.log_text.tag_add("click", "end-2l", "end-1l")
            self.log_text.tag_configure("click", foreground="#4ade80")
        elif level == "warn":
            self.log_text.tag_add("warn", "end-2l", "end-1l")
            self.log_text.tag_configure("warn", foreground="#fbbf24")
        elif level == "err":
            self.log_text.tag_add("err", "end-2l", "end-1l")
            self.log_text.tag_configure("err", foreground="#f87171")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.log_buf.clear()

    def _schedule_device_info(self):
        self._refresh_device_info()
        self.after(8000, self._schedule_device_info)

    def _refresh_device_info(self):
        def work():
            try:
                info = collect_device_info()
                self.msg_q.put(("device_info", info))
            except Exception as e:
                self.msg_q.put(("device_info", {"error": str(e)}))

        threading.Thread(target=work, daemon=True).start()

    def _wifi_enable(self):
        """USB 已连接时，开启手机 TCP/IP 调试（默认 5555）。"""
        def work():
            self.wifi_status_var.set("正在开启无线调试…")
            try:
                # 用当前已连 USB 设备执行 tcpip
                r = run_adb_text(["tcpip", "5555"], timeout=10)
                # 读取手机 WiFi IP
                info = collect_device_info()
                ip = info.get("ip", "")
                if ip and ip != "?":
                    self.wifi_ip_var.set(f"{ip}:5555")
                    self.wifi_status_var.set(f"已开启无线调试，请拔线后点「连接」→ {ip}:5555")
                else:
                    self.wifi_status_var.set(f"已发送 tcpip 5555，请手动填手机 IP（{r[:60]}）")
            except Exception as e:
                self.wifi_status_var.set(f"开启失败: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _wifi_connect(self):
        host = (self.wifi_ip_var.get() or "").strip()
        if not host:
            self.wifi_status_var.set("请填写 IP，如 192.168.1.8:5555")
            return
        if ":" not in host:
            host = host + ":5555"
            self.wifi_ip_var.set(host)

        def work():
            self.wifi_status_var.set(f"正在连接 {host} …")
            try:
                # 先 adb connect
                r1 = run_adb_text(["connect", host], timeout=12)
                out = run_adb_text(["devices"])
                ok = any(host.split(":")[0] in ln and "device" in ln for ln in out.splitlines())
                if "connected" in (r1 or "").lower() or ok:
                    self.wifi_status_var.set(f"已连接 {host}")
                    self.wifi_ip_var.set(host)
                    self._refresh_device()
                    self._refresh_device_info()
                    self.log(f"WiFi ADB 已连接: {host}", "info")
                else:
                    self.wifi_status_var.set(f"连接结果: {r1 or out[:80]}")
            except Exception as e:
                self.wifi_status_var.set(f"连接失败: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _wifi_disconnect(self):
        host = (self.wifi_ip_var.get() or "").strip()

        def work():
            try:
                if host:
                    run_adb_text(["disconnect", host], timeout=8)
                self.wifi_status_var.set("已断开 WiFi 连接（USB 不受影响）")
                self._refresh_device()
            except Exception as e:
                self.wifi_status_var.set(f"断开失败: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _refresh_device(self):
        def work():
            try:
                out = run_adb_text(["devices"])
                lines = [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]
                ready = [ln.split()[0] for ln in lines if ln.endswith("device")]
                if not ready:
                    self.msg_q.put(("device", None, "未连接设备"))
                    return
                serial = ready[0]
                model = run_adb_text(["shell", "getprop", "ro.product.model"]) or "?"
                self.msg_q.put(("device", serial, f"{serial} ({model})"))
            except Exception as e:
                self.msg_q.put(("device", None, f"设备检测失败: {e}"))

        threading.Thread(target=work, daemon=True).start()
        self.status_var.set("正在检测设备…")

    def _save_shot(self):
        if self._last_frame is None:
            messagebox.showinfo("提示", "还没有截图，请先启动脚本")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
            initialfile=f"screen_{datetime.now().strftime('%H%M%S')}.png",
        )
        if not path:
            return
        cv2.imwrite(path, self._last_frame)
        self.log(f"截图已保存: {path}")

    def _update_preview(self, frame: np.ndarray, boxes: list[OcrBox]):
        self._last_frame = frame
        h, w = frame.shape[:2]
        # 画框标注
        vis = frame.copy()
        for b in boxes:
            color = (0, 255, 0) if b.matched else (255, 200, 0)
            thickness = 3 if b.matched else 1
            # 用中心画小框
            x, y = int(b.cx), int(b.cy)
            cv2.rectangle(vis, (max(0, x - 40), max(0, y - 18)),
                          (min(w - 1, x + 120), min(h - 1, y + 18)), color, thickness)

        # 缩放到预览区
        max_h = 560
        scale = min(1.0, max_h / h)
        disp_w, disp_h = int(w * scale), int(h * scale)
        rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
        img = Image.fromarray(rgb)
        self._photo = ImageTk.PhotoImage(img)
        self.preview.configure(image=self._photo, text="")
        self.preview_info.set(f"分辨率: {w}x{h}   显示: {disp_w}x{disp_h}   OCR框: {len(boxes)}")

    def _update_ocr_table(self, boxes: list[OcrBox]):
        self.tree.delete(*self.tree.get_children())
        for b in boxes[:30]:
            hit = b.matched or "-"
            self.tree.insert(
                "", "end",
                values=(b.text[:28], f"{b.score:.2f}", f"({int(b.cx)},{int(b.cy)})", hit),
            )

    def _poll_queue(self):
        try:
            while True:
                kind = self.msg_q.get_nowait()
                if kind[0] == "log":
                    _, msg, level = kind
                    self.log(msg, level)
                elif kind[0] == "frame":
                    _, frame, boxes = kind
                    self._update_preview(frame, boxes)
                    self._update_ocr_table(boxes)
                elif kind[0] == "stat":
                    _, clicks, rounds, elapsed, extra = kind
                    self.stat_var.set(
                        f"点击 {clicks} 次 · 轮次 {rounds} · 用时 {elapsed:.0f}s · {extra}"
                    )
                elif kind[0] == "device":
                    _, serial, text = kind
                    if serial:
                        global DEVICE_SERIAL
                        DEVICE_SERIAL = serial
                        self.status_var.set(f"设备: {text}")
                        self.log(f"已连接设备: {text}", "info")
                    else:
                        self.status_var.set(text)
                        self.log(text, "err")
                elif kind[0] == "device_info":
                    info = kind[1]
                    if "error" in info:
                        self.device_var.set(f"设备信息: {info['error']}")
                    else:
                        self.device_var.set(
                            f"机型: {info.get('brand','?')} {info.get('model','?')}  ·  Android {info.get('android','?')}\n"
                            f"分辨率: {info.get('resolution','?')}  ·  电量: {info.get('battery','?')} ({info.get('charging','?')})\n"
                            f"网络: {info.get('network','?')}  ·  IP: {info.get('ip','?')}\n"
                            f"WiFi: {info.get('wifi','?')}"
                        )
                elif kind[0] == "stopped":
                    self.running = False
                    self.btn_start.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    self.status_var.set("已停止")
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    # ---------- 控制 ----------
    def start_bot(self):
        if self.running:
            return
        self.stop_event.clear()
        self.running = True
        self.clicks = 0
        self.rounds = 0
        self.started_at = time.time()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status_var.set("运行中…")
        self.log("启动自动看广告脚本（实时影像）", "info")
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def stop_bot(self):
        self.stop_event.set()
        self.status_var.set("正在停止…")
        self.log("收到停止指令", "warn")

    def _worker_loop(self):
        global DEVICE_SERIAL
        live: Optional[LiveScreen] = None
        try:
            self.msg_q.put(("log", f"ADB: {ADB}", "info"))
            out = run_adb_text(["devices"])
            lines = [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]
            ready = [ln.split()[0] for ln in lines if ln.endswith("device")]
            if not ready:
                self.msg_q.put(("log", "未检测到已授权设备，请开启 USB 调试", "err"))
                self.msg_q.put(("stopped",))
                return
            DEVICE_SERIAL = ready[0]
            if len(ready) > 1:
                self.msg_q.put(("log", f"多设备，使用 {ready[0]}", "warn"))

            dev_w, dev_h = get_device_size()
            global SCREEN_W, SCREEN_H
            SCREEN_W, SCREEN_H = dev_w, dev_h
            # 流分辨率保持真机宽高比，避免坐标系/ROI 被拉变形
            scale = 0.5 if dev_w >= 1000 else 1.0
            stream_w, stream_h = int(dev_w * scale) // 2 * 2, int(dev_h * scale) // 2 * 2
            self.msg_q.put(("log", f"真机分辨率 {dev_w}x{dev_h} · 影像流 {stream_w}x{stream_h}", "info"))

            self.msg_q.put(("log", "加载 OCR 模型…", "info"))
            get_ocr()
            self.msg_q.put(("log", "OCR 就绪，启动实时影像流", "info"))
            # 尽量保持设备不休眠（USB 供电时）
            try:
                run_adb_text(["shell", "svc", "power", "stayon", "true"])
            except Exception:
                pass

            live = LiveScreen(
                ADB,
                DEVICE_SERIAL,
                size=f"{stream_w}x{stream_h}",
                on_log=lambda s: self.msg_q.put(("log", s, "info")),
                screen_off=bool(self.screen_off_var.get()),
            )
            live.start()

            miss = 0
            last_seq = -1
            last_click: dict[tuple, float] = {}
            ocr_gap = 0.0
            while not self.stop_event.is_set():
                # 预览始终跟最新影像帧
                frame = live.latest()
                if frame is None:
                    if int(time.time()) % 3 == 0:
                        self.msg_q.put(("log", f"等待实时影像 mode={live.mode}", "info"))
                    time.sleep(0.15)
                    continue

                seq = live.latest_seq()
                if seq != last_seq:
                    self.msg_q.put(("frame", frame.copy(), []))
                    last_seq = seq

                # OCR 节流：约每 1 秒识别一次，中间只刷预览
                now = time.time()
                if now - ocr_gap < 0.9:
                    time.sleep(0.12)
                    continue
                ocr_gap = now

                boxes = run_ocr(frame)
                sh, sw = frame.shape[:2]
                focus = filter_focus(boxes, sw, sh)
                self.msg_q.put(("frame", frame.copy(), focus))
                self.rounds += 1

                if is_live_room(boxes, sh):
                    self.msg_q.put(("log", "识别到直播间顶部特征，立即返回", "warn"))
                    press_back()
                    miss = 0
                    time.sleep(1.2)
                    continue

                in_ad = is_in_ad(boxes)
                cd = parse_countdown_seconds(boxes)
                if in_ad and cd is not None and cd >= 1:
                    # 按倒计时休眠，结束后立刻探查「领取奖励」
                    wait = max(0.3, min(cd - 0.2, 25.0))
                    self.msg_q.put(("log", f"广告倒计时 {cd}s，等待 {wait:.1f}s 后探查领取奖励", "info"))
                    time.sleep(wait)
                    continue

                picked = pick_click(boxes, sw, sh)
                if picked:
                    target, box, score = picked
                    fx, fy = int(box.cx), int(box.cy)
                    # 影像帧坐标 → 真机坐标（帧分辨率可能被缩放）
                    x, y = map_to_device(fx, fy, sw, sh, dev_w, dev_h)
                    # 同点防抖：2 秒内不重复点同一按钮
                    now = time.time()
                    key = (target, x, y)
                    if key in last_click and now - last_click[key] < 2.0:
                        self.msg_q.put(("log", f"跳过重复点击「{target}」@({x},{y})", "warn"))
                        time.sleep(0.4)
                        continue
                    last_click[key] = now
                    self.clicks += 1
                    self.msg_q.put(
                        ("log",
                         f"点击「{target}」 score={score:.2f} text={box.text!r} "
                         f"帧({fx},{fy})→机({x},{y})",
                         "click")
                    )
                    try:
                        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                        vis = frame.copy()
                        cv2.circle(vis, (fx, fy), 28, (0, 0, 255), 3)
                        cv2.imwrite(str(DEBUG_DIR / f"{datetime.now().strftime('%H%M%S')}_{target}.jpg"), vis)
                    except Exception:
                        pass
                    tap(x, y)
                    miss = 0
                    if target in NO_COOLDOWN_TARGETS:
                        self.msg_q.put(("stat", self.clicks, self.rounds,
                                        time.time() - self.started_at, f"{target} 已点"))
                        continue
                    human_sleep(CLICK_COOLDOWN, 0.5)
                else:
                    tag = "广告中" if in_ad else "待机"
                    preview = " | ".join(normalize(b.text) for b in focus[:8]) or "（无重点文字）"
                    extra = ""
                    if getattr(pick_click, "last_rejects", None):
                        extra = " · 拒绝: " + "; ".join(pick_click.last_rejects[:3])
                    self.msg_q.put(("log", f"未命中[{tag}] {preview[:80]}{extra}", "info"))
                    human_sleep(POLL_INTERVAL, 0.4)
                    if in_ad:
                        miss = 0
                    else:
                        miss += 1
                        if miss >= MISS_BACK_THRESHOLD:
                            self.msg_q.put(("log", f"连续 {miss} 次未命中，按返回防卡死", "warn"))
                            press_back()
                            miss = 0
                            time.sleep(1.5)

                self.msg_q.put((
                    "stat", self.clicks, self.rounds, time.time() - self.started_at,
                    f"{live.mode}/{live.fps:.1f}fps · " + ("广告等待中" if in_ad else "识别中"),
                ))

        except Exception as e:
            self.msg_q.put(("log", f"工作线程异常: {type(e).__name__}: {e}", "err"))
        finally:
            if live is not None:
                try:
                    live.stop()
                except Exception:
                    pass
            self.msg_q.put(("stopped",))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
