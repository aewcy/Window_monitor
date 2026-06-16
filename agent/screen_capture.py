"""
屏幕截图采集模块
使用 mss 库进行高效屏幕捕获，兼容多显示器
多显示器: 每屏独立截图 → 分别缩放 → 逐张上报 (Dashboard 可选屏)
"""
import time
import io
import base64
import threading
from datetime import datetime
from PIL import Image

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False
    print("[WARN] mss 未安装，回退到 pyautogui。建议: pip install mss")

from config import SCREENSHOT_QUALITY, SCREENSHOT_MAX_WIDTH


class ScreenCapture:
    """定时屏幕截图采集器 — 多屏独立捕获"""

    def __init__(self, interval: int = 30):
        self.interval = interval
        self._running = False
        self._thread = None
        self._listeners = []
        self._capture_lock = threading.Lock()
        self.monitor_count = 1  # 首次捕获后更新

    def add_listener(self, callback):
        """添加截图回调 - callback(data_dict) 每屏调用一次"""
        self._listeners.append(callback)

    def _capture_one(self, sct, monitor: dict, mon_idx: int) -> tuple | None:
        """捕获单个显示器，返回 (b64_str, timestamp, mon_idx, mon_total)"""
        try:
            img = sct.grab(monitor)
            frame = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

            # 缩放到最大宽度
            if frame.width > SCREENSHOT_MAX_WIDTH:
                ratio = SCREENSHOT_MAX_WIDTH / frame.width
                frame = frame.resize(
                    (SCREENSHOT_MAX_WIDTH, int(frame.height * ratio)),
                    Image.LANCZOS
                )

            # JPEG 压缩
            buf = io.BytesIO()
            frame.save(buf, format="JPEG", quality=SCREENSHOT_QUALITY)
            b64_data = base64.b64encode(buf.getvalue()).decode("ascii")

            return b64_data, mon_idx
        except Exception as e:
            print(f"[ScreenCapture] 屏{mon_idx+1} 捕获失败: {e}")
            return None

    def _capture_all(self) -> list:
        """捕获所有显示器，返回 [(b64, timestamp, mon_idx, mon_total), ...]"""
        results = []
        try:
            if HAS_MSS:
                with mss.mss() as sct:
                    monitors = sct.monitors[1:]  # 跳过 monitors[0] (虚拟全屏)
                    total = len(monitors)
                    self.monitor_count = max(total, 1)

                    timestamp = datetime.now().isoformat()
                    for idx, mon in enumerate(monitors):
                        shot = self._capture_one(sct, mon, idx)
                        if shot:
                            b64_data, mon_idx = shot
                            results.append((b64_data, timestamp, mon_idx, total))
            else:
                import pyautogui
                pil_img = pyautogui.screenshot()
                if pil_img.width > SCREENSHOT_MAX_WIDTH:
                    ratio = SCREENSHOT_MAX_WIDTH / pil_img.width
                    pil_img = pil_img.resize(
                        (SCREENSHOT_MAX_WIDTH, int(pil_img.height * ratio)),
                        Image.LANCZOS
                    )
                buf = io.BytesIO()
                pil_img.save(buf, format="JPEG", quality=SCREENSHOT_QUALITY)
                b64_data = base64.b64encode(buf.getvalue()).decode("ascii")
                timestamp = datetime.now().isoformat()
                results.append((b64_data, timestamp, 0, 1))
        except Exception as e:
            print(f"[ScreenCapture] 截图失败: {e}")

        return results

    def capture_once(self) -> list[dict]:
        """执行一次截图（全屏），返回每屏的结构化数据列表（线程安全）"""
        with self._capture_lock:
            raw = self._capture_all()

        shots = []
        for b64_data, timestamp, mon_idx, mon_total in raw:
            shots.append({
                "timestamp": timestamp,
                "image_base64": b64_data,
                "format": "jpeg",
                "monitor_index": mon_idx,
                "monitor_total": mon_total,
            })
        return shots

    def _loop(self):
        """后台循环 — 每屏独立回调"""
        while self._running:
            shots = self.capture_once()
            for data in shots:
                for cb in self._listeners:
                    try:
                        cb(data)
                    except Exception as e:
                        print(f"[ScreenCapture] 回调异常: {e}")
            time.sleep(self.interval)

    def start(self):
        """启动后台截图"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[ScreenCapture] 已启动，间隔 {self.interval}s")

    def stop(self):
        """停止后台截图"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[ScreenCapture] 已停止")
