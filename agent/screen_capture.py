"""
屏幕截图采集模块
使用 mss 库进行高效屏幕捕获，兼容多显示器
"""
import time
import io
import base64
import threading
from datetime import datetime
from PIL import Image

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False
    print("[WARN] mss 未安装，回退到 pyautogui。建议: pip install mss")

from config import SCREENSHOT_QUALITY, SCREENSHOT_MAX_WIDTH


class ScreenCapture:
    """定时屏幕截图采集器"""

    def __init__(self, interval: int = 30):
        self.interval = interval
        self._running = False
        self._thread = None
        self._last_screenshot = None
        self._listeners = []
        self._capture_lock = threading.Lock()

    def add_listener(self, callback):
        """添加截图回调 - callback(b64_data, timestamp)"""
        self._listeners.append(callback)

    def _capture(self) -> tuple[str, str] | None:
        """执行一次截图，返回 (base64_str, timestamp_iso)"""
        try:
            if HAS_MSS:
                with mss.mss() as sct:
                    # 捕获主显示器
                    monitor = sct.monitors[1]
                    img = sct.grab(monitor)
                    pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            else:
                import pyautogui
                pil_img = pyautogui.screenshot()

            # 缩放到最大宽度
            if pil_img.width > SCREENSHOT_MAX_WIDTH:
                ratio = SCREENSHOT_MAX_WIDTH / pil_img.width
                new_size = (SCREENSHOT_MAX_WIDTH, int(pil_img.height * ratio))
                pil_img = pil_img.resize(new_size, Image.LANCZOS)

            # 压缩为 JPEG base64
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=SCREENSHOT_QUALITY)
            b64_data = base64.b64encode(buf.getvalue()).decode("ascii")

            timestamp = datetime.now().isoformat()
            self._last_screenshot = (b64_data, timestamp)
            return b64_data, timestamp

        except Exception as e:
            print(f"[ScreenCapture] 截图失败: {e}")
            return None

    def capture_once(self) -> dict | None:
        """执行一次截图并返回结构化数据（线程安全）"""
        with self._capture_lock:
            result = self._capture()
        if result is None:
            return None
        b64_data, timestamp = result
        return {
            "timestamp": timestamp,
            "image_base64": b64_data,
            "format": "jpeg",
        }

    def _loop(self):
        """后台循环"""
        while self._running:
            data = self.capture_once()
            if data:
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
