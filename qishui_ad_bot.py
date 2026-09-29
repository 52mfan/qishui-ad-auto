# -*- coding: utf-8 -*-
"""
汽水音乐 · 自动看广告领时长

原理：
  1. ADB 截取手机屏幕
  2. OCR 识别屏幕文字
  3. 命中「领取奖励 / 继续观看 / 领取成功」就自动点击
  4. 识别到直播间顶部特征则按返回秒退
  5. 连续未命中时按返回，防止卡死

依赖：opencv-python, numpy, rapidocr-onnxruntime
环境：手机开启 USB 调试，adb 可用
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import Optional

import cv2
import numpy as np
import random
from rapidocr_onnxruntime import RapidOCR

from live_screen import LiveScreen

# ---------------- 控制台编码（Windows GBK 崩溃防护） ----------------
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ========================= 可调配置 =========================
# 要点击的目标按钮（优先级从左到右）
# 「领取奖励」最高优先：倒计时结束出现后立刻点
TARGETS: list[str] = ["领取奖励", "领取", "继续观看", "领取成功", "我知道了"]

# OCR 置信度下限
OCR_SCORE = 0.55

# 主按钮允许出现的区域（相对屏幕宽高 0~1）
# ROI 放宽：按钮常在底部，旧值会把 y>0.92 的「领取奖励」滤掉
TARGET_ROI: dict[str, dict[str, tuple[float, float]]] = {
    "领取奖励": {"x": (0.10, 0.90), "y": (0.10, 0.98)},
    "领取": {"x": (0.10, 0.90), "y": (0.10, 0.98)},
    "继续观看": {"x": (0.05, 0.98), "y": (0.02, 0.98)},
    "领取成功": {"x": (0.00, 1.00), "y": (0.00, 1.00)},
    "我知道了": {"x": (0.10, 0.90), "y": (0.15, 0.98)},
}

# 主按钮需靠近屏幕中心（防止点到角落误触）
CENTER_TARGETS = {"领取奖励", "领取"}
BOTTOM_TARGETS = {"继续观看"}

# 直播间顶部特征：出现就立刻返回
LIVE_KEYWORDS = ("关注", "更多直播", "正在直播")

# 识别轮询间隔（秒）
POLL_INTERVAL = 1.2
# 点击后冷却（秒），避免连点
CLICK_COOLDOWN = 1.8
# 连续未命中多少次后按返回（防卡死）
MISS_BACK_THRESHOLD = 6
# OCR 截图最大宽度，过大先缩小加速
OCR_MAX_WIDTH = 720
# 是否保存点击调试图
SAVE_DEBUG = True
# 未命中时是否随机上滑（默认关）
ENABLE_RANDOM_SWIPE = False
SWIPE_PROB = 0.08

# 无冷却目标（点完立刻继续识别）
NO_COOLDOWN_TARGETS = {"领取成功", "领取奖励", "领取", "我知道了"}
# ===========================================================

SCRIPT_DIR = Path(__file__).resolve().parent
DEBUG_DIR = SCRIPT_DIR / "debug_clicks"

# OCR 常见错字映射
OCR_FIX = {
    "领収": "领取", "领职": "领取", "领敢": "领取", "领联": "领取",
    "奨": "奖", "奬": "奖", "勵": "励",
    "继渎": "继续", "继读": "继续",
    "観看": "观看", "观着": "观看",
}


@dataclass
class OcrBox:
    text: str
    score: float
    cx: float  # 中心 x（原图坐标）
    cy: float  # 中心 y（原图坐标）
    matched: str = ""


# --------------------------- ADB ---------------------------

def find_adb() -> str:
    """查找 adb：优先 PATH，其次常见目录与程序旁 platform-tools。"""
    hit = which("adb") or which("adb.exe")
    if hit:
        return hit
    for p in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "platform-tools" / "adb.exe",
        Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools" / "adb.exe",
        Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools" / "adb.exe",
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
# 多设备时指定序列号；单设备可为 None
DEVICE_SERIAL: Optional[str] = None
DEV_W, DEV_H = 1080, 2340
_last_click: dict[tuple, float] = {}

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
    img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
    return img


def get_device_size() -> tuple[int, int]:
    txt = run_adb_text(["shell", "wm", "size"])
    m = re.search(r"(\d+)\s*x\s*(\d+)", txt or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return 1080, 2340


def map_to_device(x: float, y: float, fw: int, fh: int, dw: int, dh: int) -> tuple[int, int]:
    if fw <= 0 or fh <= 0:
        return int(x), int(y)
    return int(round(x * dw / fw)), int(round(y * dh / fh))


CLICK_JITTER = 6


def tap(x: int, y: int) -> None:
    time.sleep(random.uniform(0.03, 0.15))
    jx = random.randint(-CLICK_JITTER, CLICK_JITTER)
    jy = random.randint(-CLICK_JITTER, CLICK_JITTER)
    tx, ty = max(2, int(x) + jx), max(2, int(y) + jy)
    run_adb(["shell", "input", "tap", str(tx), str(ty)])


def human_sleep(base: float, spread: float = 0.35) -> None:
    time.sleep(max(0.15, base + random.uniform(-spread, spread)))


def press_back() -> None:
    run_adb(["shell", "input", "keyevent", "4"])


# --------------------------- OCR ---------------------------

_ocr: Optional[RapidOCR] = None


def get_ocr() -> RapidOCR:
    global _ocr
    if _ocr is None:
        print("⏳ 加载 OCR 模型…")
        _ocr = RapidOCR()
        print("✅ OCR 就绪")
    return _ocr


def normalize(text: str) -> str:
    s = (text or "").strip().replace(" ", "").replace("　", "")
    s = re.sub(r"[×xX✕✖·•|丨\[\]【】()（）]+$", "", s)
    s = re.sub(r"^[×xX✕✖·•|丨]+", "", s)
    for a, b in OCR_FIX.items():
        s = s.replace(a, b)
    return s


# 倒计时/解说类文案，绝不能当按钮点
COUNTDOWN_PAT = re.compile(
    r"(秒后|后再|再看|再闯|后可|后领|后得|后获得|可领奖励$|试看|完整观看|观看完整)"
)


def is_countdown_noise(recognized: str) -> bool:
    s = normalize(recognized)
    if not s:
        return True
    # 「14秒后可领奖励」「再看15秒继续解锁」等
    if re.search(r"\d+\s*秒", s) or COUNTDOWN_PAT.search(s):
        return True
    return False


def text_hit(recognized: str, target: str) -> bool:
    a, b = normalize(recognized), normalize(target)
    if not a or not b:
        return False
    if is_countdown_noise(a):
        return False
    # 短目标（「领取」）只认按钮本身，避免点到「领取成功/领取奖励」长文案
    if len(b) <= 2:
        return a == b or a == b + "了"
    # 优先精确相等，避免把说明文字点成按钮
    if a == b:
        return True
    # 短标签允许包含（如「去领取奖励」）
    if b in a and len(a) <= len(b) + 4:
        return True
    # OCR 缺一字仍可命中
    if len(b) >= 4 and any(b[:i] + b[i + 1 :] in a for i in range(len(b))):
        return True
    return False


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
        # RapidOCR: [points, text, score]
        pts, text, score = item[0], item[1], float(item[2])
        if score < OCR_SCORE:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx = (min(xs) + max(xs)) / 2 / scale
        cy = (min(ys) + max(ys)) / 2 / scale
        boxes.append(OcrBox(text=str(text), score=score, cx=cx, cy=cy))
    return boxes


# --------------------------- 主逻辑 ---------------------------

def in_roi(target: str, cx: float, cy: float, sw: int, sh: int) -> bool:
    roi = TARGET_ROI.get(target)
    if not roi:
        return True
    x0, x1 = roi["x"]
    y0, y1 = roi["y"]
    return x0 * sw <= cx <= x1 * sw and y0 * sh <= cy <= y1 * sh


def save_debug(screen: np.ndarray, target: str, x: int, y: int, text: str, score: float) -> None:
    if not SAVE_DEBUG:
        return
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S_%f")[:-3]
    path = DEBUG_DIR / f"{ts}_{target}.jpg"
    vis = screen.copy()
    cv2.circle(vis, (int(x), int(y)), 24, (0, 0, 255), 3)
    cv2.putText(vis, f"{target} {score:.2f} {text}", (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    cv2.imwrite(str(path), vis)


def find_and_click(screen: np.ndarray, boxes: list[OcrBox]) -> Optional[str]:
    sh, sw = screen.shape[:2]
    for target in TARGETS:
        cands: list[tuple[float, float, float, str]] = []
        for b in boxes:
            if not text_hit(b.text, target):
                continue
            if not in_roi(target, b.cx, b.cy, sw, sh):
                continue
            cands.append((b.score, b.cx, b.cy, b.text))
        if not cands:
            continue

        if target in CENTER_TARGETS:
            mx, my = sw * 0.5, sh * 0.5
            cands.sort(key=lambda c: (-c[0], (c[1] - mx) ** 2 + (c[2] - my) ** 2))
        elif target in BOTTOM_TARGETS:
            cands.sort(key=lambda c: (-c[0], -c[2], abs(c[1] - sw * 0.5)))
        else:
            cands.sort(key=lambda c: (-c[0], c[2], -c[1]))

        score, cx, cy, text = cands[0]
        fx, fy = int(round(cx)), int(round(cy))
        x, y = map_to_device(fx, fy, sw, sh, DEV_W, DEV_H)
        now = time.time()
        key = (target, x, y)
        if key in _last_click and now - _last_click[key] < 2.0:
            return None
        _last_click[key] = now
        print(f"🎯 点击「{target}」 score={score:.2f} text={text!r} 帧({fx},{fy})→机({x},{y})")
        save_debug(screen, target, fx, fy, text, score)
        tap(x, y)
        return target
    return None


def is_live_room(boxes: list[OcrBox], sh: int) -> bool:
    top = sh * 0.25
    for b in boxes:
        if b.cy > top:
            continue
        t = normalize(b.text)
        if t in ("关注", "更多直播") or "更多直播" in t or t == "正在直播":
            return True
    return False


def is_in_ad(boxes: list[OcrBox]) -> bool:
    """屏幕还在播广告（含倒计时），此时绝不能按返回。"""
    for b in boxes:
        t = normalize(b.text)
        if t == "广告" or t.endswith("秒后可领奖励") or "秒后可领" in t:
            return True
        if re.search(r"\d+\s*秒后", t):
            return True
    return False


def parse_countdown_seconds(boxes: list[OcrBox]) -> Optional[int]:
    best: Optional[int] = None
    for b in boxes:
        t = normalize(b.text)
        m = re.search(r"(\d{1,3})\s*秒后", t)
        if m:
            n = int(m.group(1))
            if 0 <= n <= 180:
                best = n if best is None else min(best, n)
            continue
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
    return any(w in t for w in FOCUS_WORDS) or bool(re.search(r"\d+\s*秒", t))


def filter_focus(boxes: list[OcrBox], sw: int, sh: int) -> list[OcrBox]:
    for target in TARGETS:
        for b in boxes:
            if text_hit(b.text, target) and in_roi(target, b.cx, b.cy, sw, sh):
                if not b.matched:
                    b.matched = target
    return [b for b in boxes if b.matched or is_focus_text(b.text)]


def main() -> None:
    global DEVICE_SERIAL

    print("🚀 汽水音乐 · 自动看广告脚本")
    print(f"   ADB     : {ADB}")
    devices_out = run_adb_text(["devices"]) if Path(ADB).exists() or which(ADB) else ""
    lines = [ln.strip() for ln in devices_out.splitlines()[1:] if ln.strip()]
    ready = [ln.split()[0] for ln in lines if ln.endswith("device")]
    if not ready:
        print("❌ 没有已连接授权的设备，请检查 USB 调试")
        sys.exit(1)
    DEVICE_SERIAL = ready[0] if len(ready) > 1 else None
    serial_show = ready[0]
    model = run_adb_text(["shell", "getprop", "ro.product.model"]) or "?"
    print(f"   设备    : {serial_show} ({model})")
    print(f"   目标    : {TARGETS}")
    print(f"   置信度  : ≥{OCR_SCORE}  轮询={POLL_INTERVAL}s")
    print(f"   调试图  : {DEBUG_DIR}")
    print("   停止    : Ctrl+C")
    print("-" * 48)
    print("📱 请把手机停在汽水音乐「看广告领时长」页面，屏幕保持常亮")
    print("-" * 48)

    get_ocr()

    global DEV_W, DEV_H
    DEV_W, DEV_H = get_device_size()
    scale = 0.5 if DEV_W >= 1000 else 1.0
    stream_w, stream_h = int(DEV_W * scale) // 2 * 2, int(DEV_H * scale) // 2 * 2
    print(f"   真机分辨率 {DEV_W}x{DEV_H} · 影像流 {stream_w}x{stream_h}")
    live = LiveScreen(ADB, DEVICE_SERIAL, size=f"{stream_w}x{stream_h}", on_log=lambda s: print(s))
    live.start()
    print("📡 实时影像已启动（优先 H264 流）")

    miss = 0
    clicks = 0
    started = time.time()

    while True:
        try:
            screen = live.latest()
            if screen is None:
                print("⚠️ 等待实时影像…")
                time.sleep(1)
                continue

            boxes = run_ocr(screen)
            sh = screen.shape[0]

            if is_live_room(boxes, sh):
                print("⚡ 识别到直播间顶部特征，立即返回")
                press_back()
                miss = 0
                time.sleep(1.5)
                continue

            in_ad = is_in_ad(boxes)
            cd = parse_countdown_seconds(boxes)
            if in_ad and cd is not None and cd >= 1:
                wait = max(0.3, min(cd - 0.2, 25.0))
                print(f"⏱ 广告倒计时 {cd}s，等待 {wait:.1f}s 后探查领取奖励")
                time.sleep(wait)
                continue

            clicked = find_and_click(screen, boxes)
            if clicked:
                clicks += 1
                miss = 0
                if clicked in NO_COOLDOWN_TARGETS:
                    print(f"⚡ 「{clicked}」已点，立即继续识别")
                    continue
                human_sleep(CLICK_COOLDOWN, 0.5)
                continue

            # 未命中
            focus = filter_focus(boxes, screen.shape[1], screen.shape[0])
            texts = " | ".join(normalize(b.text) for b in focus[:8]) or "（无重点文字）"
            tag = "广告中" if in_ad else "待机"
            print(f"· 未命中[{tag}] · 已点{clicks}次 · 重点: {texts[:100]}")

            if ENABLE_RANDOM_SWIPE and not in_ad and np.random.random() < SWIPE_PROB:
                h, w = screen.shape[:2]
                x, y1, y2 = w // 2, int(h * 0.55), int(h * 0.40)
                print(f"↕ 随机上滑 {y1}->{y2}")
                run_adb(["shell", "input", "swipe", str(x), str(y1), str(x), str(y2), "350"])

            human_sleep(POLL_INTERVAL, 0.4)
            # 广告播放中只等待，绝不返回，避免中断领奖
            if in_ad:
                miss = 0
                continue

            miss += 1
            if miss >= MISS_BACK_THRESHOLD:
                print(f"⚠️ 连续 {miss} 次未命中且不在广告中，按返回防卡死")
                press_back()
                miss = 0
                time.sleep(2)

        except KeyboardInterrupt:
            mins = (time.time() - started) / 60
            print(f"\n🛑 已停止 · 本次共点击 {clicks} 次 · 运行 {mins:.1f} 分钟")
            live.stop()
            break
        except subprocess.TimeoutExpired:
            print("⚠️ ADB 超时，稍后重试")
            time.sleep(3)
        except Exception as e:
            print(f"⚠️ 异常: {type(e).__name__}: {e}")
            time.sleep(4)


if __name__ == "__main__":
    main()
