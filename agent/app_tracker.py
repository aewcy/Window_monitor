"""
应用窗口追踪模块 - 精简版
只做一件事：定时获取当前活动窗口并上报
"""
import time
import threading
import subprocess
from datetime import datetime

import psutil

from config import IS_WINDOWS, IS_LINUX


def get_active_window() -> dict | None:
    """跨平台获取当前活动窗口，一行搞定"""

    # --- Linux: xdotool ---
    if IS_LINUX:
        try:
            wid = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True, text=True, timeout=2
            ).stdout.strip()
            if not wid:
                return None

            title = subprocess.run(
                ["xdotool", "getwindowname", wid],
                capture_output=True, text=True, timeout=2
            ).stdout.strip()
            if not title:
                return None

            pid_str = subprocess.run(
                ["xdotool", "getwindowpid", wid],
                capture_output=True, text=True, timeout=2
            ).stdout.strip()
            pid = int(pid_str) if pid_str else 0

            proc_name, proc_path = "unknown", ""
            if pid > 0:
                try:
                    p = psutil.Process(pid)
                    proc_name = p.name()
                    proc_path = p.exe() if callable(p.exe) else ""
                except Exception:
                    proc_name = f"PID:{pid}"

            return {
                "window_title": title,
                "process_name": proc_name,
                "process_path": proc_path,
                "timestamp": datetime.now().isoformat(),
            }
        except FileNotFoundError:
            # xdotool 未安装 — 仅首次输出警告
            if not getattr(get_active_window, '_xdotool_warned', False):
                print("[AppTracker] xdotool 未安装，Linux 窗口追踪不可用")
                print("[AppTracker] 安装: sudo apt install xdotool")
                get_active_window._xdotool_warned = True
            return None
        except Exception as e:
            if not getattr(get_active_window, '_linux_error_warned', False):
                print(f"[AppTracker] Linux 窗口检测失败: {e}")
                get_active_window._linux_error_warned = True
            return None

    # --- Windows: win32gui ---
    if IS_WINDOWS:
        try:
            import win32gui
            import win32process

            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            if not title or not title.strip():
                return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                p = psutil.Process(pid)
                proc_name = p.name()
                proc_path = p.exe() if callable(p.exe) else ""
            except Exception:
                proc_name, proc_path = f"PID:{pid}", ""

            return {
                "window_title": title,
                "process_name": proc_name,
                "process_path": proc_path,
                "timestamp": datetime.now().isoformat(),
            }
        except ImportError as e:
            if not getattr(get_active_window, '_pywin32_warned', False):
                print(f"[AppTracker] pywin32 未安装，窗口检测不可用: {e}")
                print("[AppTracker] 安装: pip install pywin32")
                get_active_window._pywin32_warned = True
        except Exception as e:
            if not getattr(get_active_window, '_error_warned', False):
                print(f"[AppTracker] 获取活动窗口失败: {e}")
                get_active_window._error_warned = True

    return None

class AppTracker:
    """活动窗口追踪器 - 精简版，定时轮询"""

    def __init__(self, interval: int = 5):
        self.interval = interval
        self._running = False
        self._thread = None
        self._listeners = []
        self._last_title = None

    def add_listener(self, callback):
        """callback(window_info: dict)"""
        self._listeners.append(callback)

    def _notify(self, info: dict):
        for cb in self._listeners:
            try:
                cb(info)
            except Exception as e:
                print(f"[AppTracker] 回调异常: {e}")

    def _loop(self):
        while self._running:
            info = get_active_window()
            if info:
                title = info["window_title"]
                # 只在窗口切换时上报，避免重复数据
                if title != self._last_title:
                    self._last_title = title
                    self._notify(info)
            time.sleep(self.interval)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        if IS_LINUX:
            if subprocess.run(["which", "xdotool"], capture_output=True).returncode != 0:
                print("[AppTracker] WARN: xdotool 未安装, 窗口追踪不可用")
                print("[AppTracker] 安装: sudo yum install xdotool")
        print(f"[AppTracker] started, interval={self.interval}s")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
