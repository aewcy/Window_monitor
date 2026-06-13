"""
键盘 Enter 键监控模块
检测用户在聊天应用中按 Enter 键，触发截图和事件上报
隐私安全: 仅检测 Enter 键，不记录其他按键
"""
import time
import threading
from datetime import datetime

from config import KEYBOARD_MONITOR_ENABLED, KEYBOARD_MONITOR_COOLDOWN, CHAT_APPS
from app_tracker import get_active_window

HAS_PYNPUT = False
try:
    from pynput.keyboard import Key, Listener
    HAS_PYNPUT = True
except ImportError:
    print("[WARN] pynput 未安装，键盘监控不可用。安装: pip install pynput")

# 将 CHAT_APPS 键标准化为小写，实现不区分大小写的进程名匹配
_NORMALIZED_CHAT_APPS = {}
if CHAT_APPS:
    _NORMALIZED_CHAT_APPS = {k.lower(): v for k, v in CHAT_APPS.items()}


class KeyboardEnterMonitor:
    """检测聊天应用中 Enter 键按下的监听器"""

    def __init__(self, cooldown: float = None):
        self._cooldown = cooldown if cooldown is not None else KEYBOARD_MONITOR_COOLDOWN
        self._running = False
        self._listener = None
        self._listeners = []
        self._last_trigger = 0.0
        self._lock = threading.Lock()

    def add_listener(self, callback):
        """添加回调 — callback(event_dict)"""
        self._listeners.append(callback)

    def _on_press(self, key):
        """pynput 回调 — 只在 Enter 键按下时处理"""
        # 仅处理 Enter 键，其他键立即返回
        if key not in (Key.enter,):
            return

        # 先检查窗口是否属于聊天应用，再消耗冷却时间
        # 避免非聊天应用中的 Enter 键占用冷却窗口
        try:
            info = get_active_window()
            if not info:
                return
            process_name = info.get("process_name", "")
            if not process_name:
                return
            normalized = process_name.lower()
            if normalized not in _NORMALIZED_CHAT_APPS:
                return
            display_name = _NORMALIZED_CHAT_APPS[normalized]
        except Exception as e:
            print(f"[KeyboardMonitor] 检查窗口失败: {e}")
            return

        # 冷却检查 — 防止长按触发多次（仅在聊天应用中 Enter 键时消耗冷却时间）
        now = time.time()
        with self._lock:
            if now - self._last_trigger < self._cooldown:
                return
            self._last_trigger = now

        # 构建事件并通知监听器
        event = {
            "type": "chat_enter",
            "process_name": process_name,        # 原始进程名 (e.g. "WeChat.exe")
            "display_name": display_name,         # 可读名称 (e.g. "WeChat")
            "window_title": info.get("window_title", ""),
            "process_path": info.get("process_path", ""),
            "timestamp": datetime.now().isoformat(),
        }

        for cb in self._listeners:
            try:
                cb(event)
            except Exception as e:
                print(f"[KeyboardMonitor] 回调异常: {e}")

    def start(self):
        """启动键盘监听"""
        if not KEYBOARD_MONITOR_ENABLED:
            print("[KeyboardMonitor] 已禁用 (KEYBOARD_MONITOR_ENABLED=false)")
            return
        if not CHAT_APPS:
            print("[KeyboardMonitor] 无聊天应用配置，跳过")
            return
        if not HAS_PYNPUT:
            print("[KeyboardMonitor] pynput 未安装，跳过 (pip install pynput)")
            return
        if self._running:
            return
        self._running = True
        try:
            self._listener = Listener(on_press=self._on_press)
            self._listener.daemon = True
            self._listener.start()
            app_names = ", ".join(CHAT_APPS.values())
            print(f"[KeyboardMonitor] 已启动  冷却: {self._cooldown}s  覆盖: {app_names}")
        except PermissionError:
            print("[KeyboardMonitor] 权限不足，无法全局监听键盘 (需要 root/管理员)")
            self._running = False
        except Exception as e:
            print(f"[KeyboardMonitor] 启动失败: {e}")
            self._running = False

    def stop(self):
        """停止键盘监听"""
        if not self._running:
            return
        self._running = False
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
        print("[KeyboardMonitor] 已停止")
