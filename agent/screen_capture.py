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
import queue
from ctypes import wintypes
from datetime import datetime
from PIL import Image, ImageGrab

IS_WINDOWS = sys.platform == "win32"

from config import (
    SCREENSHOT_QUALITY,
    SCREENSHOT_MAX_WIDTH,
    SCREENSHOT_UPLOAD_QUEUE_SIZE,
    SCREENSHOT_DROP_REPORT_INTERVAL,
)


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
    """定时屏幕截图采集器 — 全桌面捕获 + 逐屏裁切 + 异步上传"""

    def __init__(self, interval: int = 30):
        self.interval = interval
        self._running = False
        self._thread = None
        self._listeners = []
        self._diagnostic_listeners = []
        self._capture_lock = threading.Lock()
        self.monitor_count = 1
        self._virtual_bounds = None  # (left, top, width, height) 缓存
        # 可中断 sleep: 频率切换时立即唤醒
        self._wake = threading.Event()
        # 异步上传队列: 采集不阻塞于上传
        self._upload_queue = queue.Queue(maxsize=max(1, int(SCREENSHOT_UPLOAD_QUEUE_SIZE)))
        self._upload_thread = None
        self._dropped_frames = 0
        self._last_drop_report_at = 0.0
        self._queue_lock = threading.Lock()

    def add_listener(self, callback):
        self._listeners.append(callback)

    def add_diagnostic_listener(self, callback):
        self._diagnostic_listeners.append(callback)

    def set_interval(self, value: float):
        """设置截图间隔并唤醒采集循环，使频率切换立即生效"""
        self.interval = value
        self._wake.set()

    def _emit_diagnostic(self, category: str, level: str, message: str):
        """向外层上报采集诊断，避免队列问题只留在本地控制台。"""
        for cb in self._diagnostic_listeners:
            try:
                cb(category, level, message)
            except Exception as e:
                print(f"[ScreenCapture] 诊断回调异常: {e}")

    def _report_drop_if_needed(self, force: bool = False):
        """限频上报丢帧统计，避免网络抖动时刷爆诊断日志。"""
        if self._dropped_frames <= 0:
            return
        now = time.monotonic()
        if not force and (now - self._last_drop_report_at) < SCREENSHOT_DROP_REPORT_INTERVAL:
            return
        queue_size = self._upload_queue.qsize()
        message = (
            f"截图上传队列拥塞，最近丢弃 {self._dropped_frames} 帧；"
            f"当前队列 {queue_size}/{self._upload_queue.maxsize}，"
            f"当前截图间隔 {self.interval}s。已优先保留最新帧。"
        )
        self._emit_diagnostic("capture", "WARNING", message)
        self._last_drop_report_at = now
        self._dropped_frames = 0

    def _enqueue_frame(self, data: dict):
        """队列满时丢弃最旧帧，保留最新帧，避免 Live 长时间卡在旧画面。"""
        try:
            self._upload_queue.put_nowait(data)
            self._report_drop_if_needed()
            return
        except queue.Full:
            pass

        dropped_old = None
        with self._queue_lock:
            try:
                dropped_old = self._upload_queue.get_nowait()
                self._upload_queue.task_done()
            except queue.Empty:
                dropped_old = None

            try:
                self._upload_queue.put_nowait(data)
            except queue.Full:
                self._dropped_frames += 1
                self._report_drop_if_needed(force=True)
                return

        self._dropped_frames += 1
        self._report_drop_if_needed()

    def _upload_worker(self):
        """异步上传线程: 从队列取截图数据，串行调用 listeners"""
        while self._running or not self._upload_queue.empty():
            try:
                data = self._upload_queue.get(timeout=1)
            except queue.Empty:
                continue
            for cb in self._listeners:
                try:
                    cb(data)
                except Exception as e:
                    print(f"[ScreenUpload] 上传异常: {e}")
            self._upload_queue.task_done()

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
                "capture_interval": self.interval,
            }
            for b64, ts, idx, total in raw
        ]

    def _loop(self):
        """采集循环 — 时间补偿 + 可中断 sleep，不阻塞于上传"""
        next_time = time.monotonic()
        while self._running:
            # 采集 → 放入上传队列（非阻塞）
            for data in self.capture_once():
                self._enqueue_frame(data)

            # 从当前时间重新计算等待时间，避免从 600s/60s 空闲档切回高频时
            # 继续沿用旧的远期 next_time，导致 Live 显示 4fps 但实际长时间不更新。
            next_time = time.monotonic() + self.interval
            remaining = next_time - time.monotonic()
            if remaining < 0:
                # 已经超时，重置基准避免追赶
                next_time = time.monotonic()
                remaining = self.interval
            # 可中断 sleep: set_interval() 调用 _wake.set() 会立即唤醒
            self._wake.wait(timeout=remaining)
            self._wake.clear()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._upload_thread = threading.Thread(target=self._upload_worker, daemon=True)
        self._upload_thread.start()
        print(f"[ScreenCapture] 已启动，间隔 {self.interval}s (异步上传)")

    def stop(self):
        self._running = False
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._upload_thread:
            self._upload_thread.join(timeout=5)
        self._report_drop_if_needed(force=True)
        print("[ScreenCapture] 已停止")
