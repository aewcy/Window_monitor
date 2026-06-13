"""
键盘 Enter 键监控模块
检测用户在聊天应用中按 Enter 键，触发截图和事件上报
"""
import time
import threading
import queue
from datetime import datetime

from config import KEYBOARD_MONITOR_ENABLED, KEYBOARD_MONITOR_COOLDOWN, CHAT_APPS
from app_tracker import get_active_window

HAS_PYNPUT = False
try:
    from pynput.keyboard import Key, KeyCode, Listener
    HAS_PYNPUT = True
except ImportError:
    print("[WARN] pynput 未安装，键盘监控不可用。安装: pip install pynput")

# 将 CHAT_APPS 键标准化为小写，实现不区分大小写的进程名匹配
_NORMALIZED_CHAT_APPS = {}
if CHAT_APPS:
    _NORMALIZED_CHAT_APPS = {k.lower(): v for k, v in CHAT_APPS.items()}


class KeyboardEnterMonitor:
    """检测聊天应用中 Enter 键按下的监听器

    架构说明:
    - pynput 全局钩子回调 (_on_press) 必须 <300ms 返回，否则 Windows 会静默移除钩子
    - _on_press 只做：按键规范化 → Enter 判断 → 入队 → 立即返回
    - 工作者线程 (_worker_loop) 处理：窗口检测 → 聊天应用匹配 → 回调分发
    """

    def __init__(self, cooldown: float = None):
        self._cooldown = cooldown if cooldown is not None else KEYBOARD_MONITOR_COOLDOWN
        self._running = False
        self._listener = None
        self._listeners = []
        self._last_trigger = 0.0
        self._lock = threading.Lock()
        # 有界队列防止内存泄漏 — 长按 Enter 超 256 次后丢弃最旧事件
        self._event_queue = queue.Queue(maxsize=256)
        self._worker_thread = None

    def add_listener(self, callback):
        """添加回调 — callback(event_dict)"""
        self._listeners.append(callback)

    def _on_press(self, key):
        """pynput 钩子回调 — 仅做轻量工作，立即返回避免钩子超时"""
        # Canonical 规范化: KeyCode(vk=13) → Key.enter
        # 某些键盘布局/IME 可能以 KeyCode 形式上报 Enter 键
        try:
            canonical = self._listener.canonical(key)
        except Exception:
            canonical = key

        # 匹配 Enter 键: Key.enter 或 vk=13 (VK_RETURN) 的 KeyCode
        if canonical != Key.enter and getattr(canonical, 'vk', None) != 13:
            return

        # 轻量冷却 — 在钩子回调中快速执行，防止长按导致队列溢出
        now = time.time()
        with self._lock:
            if now - self._last_trigger < self._cooldown:
                return
            self._last_trigger = now

        # 入队后立即返回 — 所有耗时操作由工作者线程处理
        try:
            self._event_queue.put_nowait(now)
        except queue.Full:
            pass  # 队列满时静默丢弃，防止内存泄漏

    def _worker_loop(self):
        """工作者线程 — 执行可能耗时的窗口检测和回调分发"""
        while self._running:
            try:
                trigger_time = self._event_queue.get(timeout=1)
            except queue.Empty:
                continue

            # 检查活动窗口是否属于聊天应用
            try:
                info = get_active_window()
                if not info:
                    continue
                process_name = info.get("process_name", "")
                if not process_name:
                    continue
                normalized = process_name.lower()
                if normalized not in _NORMALIZED_CHAT_APPS:
                    continue
                display_name = _NORMALIZED_CHAT_APPS[normalized]
            except Exception as e:
                print(f"[KeyboardMonitor] 检查窗口失败: {e}")
                continue

            # 构建事件并通知监听器
            event = {
                "type": "chat_enter",
                "process_name": process_name,
                "display_name": display_name,
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

        # 先启动工作者线程（确保消费者在生产者之前就绪）
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="kb-worker"
        )
        self._worker_thread.start()

        try:
            self._listener = Listener(on_press=self._on_press)
            self._listener.daemon = True
            self._listener.start()

            # 健康检查 — 等待钩子线程完成初始化后验证状态
            time.sleep(0.3)
            if not self._listener.is_alive():
                print("[KeyboardMonitor] ✗ 钩子线程未存活 — 可能被安全软件或权限限制拦截")
                print("[KeyboardMonitor]   请尝试: 以管理员身份运行 或 检查杀毒软件设置")
                self._running = False
                return
            if not self._listener.running:
                print("[KeyboardMonitor] ✗ 监听器未就绪 (running=False)")
                self._running = False
                return

            app_names = ", ".join(CHAT_APPS.values())
            print(f"[KeyboardMonitor] 已启动  冷却: {self._cooldown}s  覆盖: {app_names}")
        except PermissionError:
            print("[KeyboardMonitor] ✗ 权限不足，无法全局监听键盘")
            print("[KeyboardMonitor]   请以管理员身份运行此程序")
            self._running = False
        except Exception as e:
            print(f"[KeyboardMonitor] ✗ 启动失败: {e}")
            self._running = False

    def stop(self):
        """停止键盘监听"""
        if not self._running:
            return
        self._running = False
        if self._listener:
            try:
                self._listener.stop()
            except Exception as e:
                print(f"[KeyboardMonitor] 停止监听器时异常: {e}")
        if self._worker_thread:
            self._worker_thread.join(timeout=3)
        print("[KeyboardMonitor] 已停止")
