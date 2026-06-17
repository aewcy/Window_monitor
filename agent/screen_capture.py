"""
屏幕截图采集模块
多显示器: 全虚拟桌面一次捕获(PIL all_screens=True) → 逐屏裁切 → 分别缩放上报
all_screens=True 是 Pillow 官方推荐的多屏方案, 正确处理负坐标
"""
import sys
import time
import io
import base64
import ctypes
import threading
from ctypes import wintypes
from datetime import datetime
from PIL import Image, ImageGrab

IS_WINDOWS = sys.platform == "win32"

from config import SCREENSHOT_QUALITY, SCREENSHOT_MAX_WIDTH


def _get_monitors_win32() -> list[dict]:
    """EnumDisplayMonitors — 获取所有物理显示器矩形（屏幕坐标）"""
    if not IS_WINDOWS:
        return []
    monitors = []

    class RECT(ctypes.Structure):
        _fields_ = [
            ('left',   ctypes.c_long),
            ('top',    ctypes.c_long),
            ('right',  ctypes.c_long),
            ('bottom', ctypes.c_long),
        ]

    class MONITORINFOEX(ctypes.Structure):
        _fields_ = [
            ('cbSize',    wintypes.DWORD),
            ('rcMonitor', RECT),
            ('rcWork',    RECT),
            ('dwFlags',   wintypes.DWORD),
            ('szDevice',  wintypes.WCHAR * 32),
        ]

    def _callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
        info = MONITORINFOEX()
        info.cbSize = ctypes.sizeof(MONITORINFOEX)
        ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info))
        r = info.rcMonitor
        monitors.append({
            'left':   r.left,
            'top':    r.top,
            'width':  r.right - r.left,
            'height': r.bottom - r.top,
        })
        return True

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(RECT), wintypes.LPARAM,
    )
    ctypes.windll.user32.EnumDisplayMonitors(
        None, None, MonitorEnumProc(_callback), 0,
    )
    return monitors


class ScreenCapture:
    """定时屏幕截图采集器 — 全桌面捕获 + 逐屏裁切"""

    def __init__(self, interval: int = 30):
        self.interval = interval
        self._running = False
        self._thread = None
        self._listeners = []
        self._capture_lock = threading.Lock()
        self.monitor_count = 1
        self._virtual_bounds = None  # (left, top, width, height) 缓存

    def add_listener(self, callback):
        self._listeners.append(callback)

    def _capture_all(self) -> list:
        """全虚拟桌面一次捕获 → 按显示器矩形裁切 → 返回每屏数据"""
        results = []
        try:
            if IS_WINDOWS:
                monitors = _get_monitors_win32()
            else:
                try:
                    import mss
                    with mss.mss() as sct:
                        monitors = [
                            {'left': m['left'], 'top': m['top'],
                             'width': m['width'], 'height': m['height']}
                            for m in sct.monitors[1:]
                        ]
                except Exception:
                    import pyautogui
                    return self._fallback_single(pyautogui.screenshot())

            if not monitors:
                return results

            # 去重
            seen, unique = set(), []
            for m in monitors:
                k = (m['left'], m['top'], m['width'], m['height'])
                if k not in seen:
                    seen.add(k)
                    unique.append(m)

            # 首次打印布局
            if not hasattr(self, '_layout_printed'):
                for i, m in enumerate(unique):
                    print(f"  [ScreenCapture] 屏{i+1}: {m['width']}x{m['height']} at ({m['left']},{m['top']})")
                self._layout_printed = True

            total = len(unique)
            self.monitor_count = max(total, 1)
            timestamp = datetime.now().isoformat()

            if total == 1:
                # 单屏: 直接抓
                m = unique[0]
                bbox = (m['left'], m['top'], m['left'] + m['width'], m['top'] + m['height'])
                if IS_WINDOWS:
                    full = ImageGrab.grab(bbox=bbox, all_screens=True)
                else:
                    import mss as mss_lib
                    with mss_lib.mss() as sct:
                        img = sct.grab(m)
                        full = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                frame = self._scale(full)
                b64_data = self._encode(frame)
                results.append((b64_data, timestamp, 0, 1))
            else:
                # 多屏: 全桌面一次捕获 → 裁切
                min_left  = min(m['left'] for m in unique)
                min_top   = min(m['top'] for m in unique)
                max_right = max(m['left'] + m['width'] for m in unique)
                max_bottom = max(m['top'] + m['height'] for m in unique)

                full_bbox = (min_left, min_top, max_right, max_bottom)
                if IS_WINDOWS:
                    full = ImageGrab.grab(bbox=full_bbox, all_screens=True)
                else:
                    import mss as mss_lib
                    with mss_lib.mss() as sct:
                        img = sct.grab({'left': min_left, 'top': min_top,
                                        'width': max_right - min_left,
                                        'height': max_bottom - min_top})
                        full = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

                for idx, m in enumerate(unique):
                    try:
                        # 裁切坐标 = 屏幕坐标 - 全桌面原点
                        crop_l = m['left'] - min_left
                        crop_t = m['top'] - min_top
                        crop_r = crop_l + m['width']
                        crop_b = crop_t + m['height']
                        frame = full.crop((crop_l, crop_t, crop_r, crop_b))
                        frame = self._scale(frame)
                        b64_data = self._encode(frame)
                        results.append((b64_data, timestamp, idx, total))
                    except Exception as e:
                        print(f"[ScreenCapture] 屏{idx+1} 裁切失败: {e}")

        except Exception as e:
            print(f"[ScreenCapture] 截图失败: {e}")

        return results

    def _scale(self, img: Image.Image) -> Image.Image:
        if img.width > SCREENSHOT_MAX_WIDTH:
            ratio = SCREENSHOT_MAX_WIDTH / img.width
            return img.resize((SCREENSHOT_MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)
        return img

    def _encode(self, img: Image.Image) -> str:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=SCREENSHOT_QUALITY)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _fallback_single(self, img: Image.Image) -> list:
        img = self._scale(img)
        b64 = self._encode(img)
        return [(b64, datetime.now().isoformat(), 0, 1)]

    def capture_once(self) -> list[dict]:
        with self._capture_lock:
            raw = self._capture_all()
        return [
            {
                "timestamp": ts,
                "image_base64": b64,
                "format": "jpeg",
                "monitor_index": idx,
                "monitor_total": total,
            }
            for b64, ts, idx, total in raw
        ]

    def _loop(self):
        while self._running:
            for data in self.capture_once():
                for cb in self._listeners:
                    try:
                        cb(data)
                    except Exception as e:
                        print(f"[ScreenCapture] 回调异常: {e}")
            time.sleep(self.interval)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[ScreenCapture] 已启动，间隔 {self.interval}s")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("[ScreenCapture] 已停止")
