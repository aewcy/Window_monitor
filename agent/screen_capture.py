"""
屏幕截图采集模块
Windows: Win32 GDI 直接捕获（处理负坐标/非标准布局）
其他平台: mss / pyautogui 回退
多显示器: 每屏独立截图 → 分别缩放 → 逐张上报 (Dashboard 可选屏)
"""
import sys
import time
import io
import base64
import ctypes
import threading
from ctypes import wintypes
from datetime import datetime
from PIL import Image

IS_WINDOWS = sys.platform == "win32"

from config import SCREENSHOT_QUALITY, SCREENSHOT_MAX_WIDTH


# ============================================
# Windows: Win32 GDI 捕获 — 无负坐标问题
# ============================================

def _get_monitors_win32() -> list[dict]:
    """EnumDisplayMonitors — 获取所有物理显示器矩形"""
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


def _capture_rect_win32(left: int, top: int, width: int, height: int) -> Image.Image:
    """BitBlt 捕获指定屏幕矩形 → PIL Image (RGB)"""
    import win32gui
    import win32ui
    import win32con

    hdesktop = win32gui.GetDesktopWindow()
    desktop_dc = win32gui.GetWindowDC(hdesktop)
    img_dc = win32ui.CreateDCFromHandle(desktop_dc)
    mem_dc = img_dc.CreateCompatibleDC()

    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(img_dc, width, height)
    mem_dc.SelectObject(bitmap)
    mem_dc.BitBlt((0, 0), (width, height), img_dc, (left, top), win32con.SRCCOPY)

    bmpinfo = bitmap.GetInfo()
    bmpbits = bitmap.GetBitmapBits(True)
    img = Image.frombuffer(
        'RGB',
        (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
        bmpbits, 'raw', 'BGRX', 0, 1,
    )

    # 清理
    mem_dc.DeleteDC()
    img_dc.DeleteDC()
    win32gui.ReleaseDC(hdesktop, desktop_dc)
    win32gui.DeleteObject(bitmap.GetHandle())

    return img


# ============================================
# ScreenCapture
# ============================================

class ScreenCapture:
    """定时屏幕截图采集器 — 多屏独立捕获"""

    def __init__(self, interval: int = 30):
        self.interval = interval
        self._running = False
        self._thread = None
        self._listeners = []
        self._capture_lock = threading.Lock()
        self.monitor_count = 1

    def add_listener(self, callback):
        """添加截图回调 - callback(data_dict) 每屏调用一次"""
        self._listeners.append(callback)

    def _capture_all(self) -> list:
        """捕获所有显示器，返回 [(b64, timestamp, mon_idx, mon_total), ...]"""
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
                    pil_img = pyautogui.screenshot()
                    return self._encode_fallback(pil_img)

            if not monitors:
                return results

            # 去重: 坐标相同的只算一个
            seen = set()
            unique = []
            for m in monitors:
                key = (m['left'], m['top'], m['width'], m['height'])
                if key not in seen:
                    seen.add(key)
                    unique.append(m)
            if len(unique) < len(monitors):
                print(f"[ScreenCapture] 报告 {len(monitors)} 屏, 去重后 {len(unique)} 屏")

            # 首次打印布局
            if not hasattr(self, '_layout_printed'):
                for i, m in enumerate(unique):
                    print(f"  [ScreenCapture] 屏{i+1}: {m['width']}x{m['height']} at ({m['left']},{m['top']})")
                self._layout_printed = True

            total = len(unique)
            self.monitor_count = max(total, 1)
            timestamp = datetime.now().isoformat()

            for idx, mon in enumerate(unique):
                try:
                    if IS_WINDOWS:
                        frame = _capture_rect_win32(
                            mon['left'], mon['top'],
                            mon['width'], mon['height'],
                        )
                    else:
                        import mss as mss_lib
                        with mss_lib.mss() as sct:
                            img = sct.grab(mon)
                            frame = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

                    # 缩放
                    if frame.width > SCREENSHOT_MAX_WIDTH:
                        ratio = SCREENSHOT_MAX_WIDTH / frame.width
                        frame = frame.resize(
                            (SCREENSHOT_MAX_WIDTH, int(frame.height * ratio)),
                            Image.LANCZOS,
                        )

                    # JPEG 压缩
                    buf = io.BytesIO()
                    frame.save(buf, format="JPEG", quality=SCREENSHOT_QUALITY)
                    b64_data = base64.b64encode(buf.getvalue()).decode("ascii")
                    results.append((b64_data, timestamp, idx, total))

                except Exception as e:
                    print(f"[ScreenCapture] 屏{idx+1} 捕获失败: {e}")

        except Exception as e:
            print(f"[ScreenCapture] 截图失败: {e}")

        return results

    def _encode_fallback(self, pil_img: Image.Image) -> list:
        """pyautogui 单屏回退"""
        if pil_img.width > SCREENSHOT_MAX_WIDTH:
            ratio = SCREENSHOT_MAX_WIDTH / pil_img.width
            pil_img = pil_img.resize(
                (SCREENSHOT_MAX_WIDTH, int(pil_img.height * ratio)),
                Image.LANCZOS,
            )
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=SCREENSHOT_QUALITY)
        b64_data = base64.b64encode(buf.getvalue()).decode("ascii")
        timestamp = datetime.now().isoformat()
        return [(b64_data, timestamp, 0, 1)]

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
