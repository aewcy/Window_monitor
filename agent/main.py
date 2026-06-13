"""
Agent 主程序 - 精简版
协调采集模块，数据上报服务端
"""
import sys
import time
import json
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
            except Exception as e:
                print(f"  [!] 异常: {e}")
            if i < RETRY_TIMES - 1:
                time.sleep(RETRY_DELAY)
        return False

    def screenshot(self, data: dict):
        ok = self._post("screenshot", {
            "agent_name": self.agent,
            "type": "screenshot",
            "timestamp": data["timestamp"],
            "image_base64": data["image_base64"],
            "format": data.get("format", "jpeg"),
        })
        if ok:
            print(f"  [OK] 截图 {data['timestamp']}")

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

    def heartbeat(self):
        self._post("heartbeat", {"agent_name": self.agent})


# ============================================
# Agent 主控
# ============================================

# ============================================
# 自适应截图频率 — 全局状态
# ============================================
_last_activity_time = time.time()          # 最后一次用户活动时间
_server_interval = SCREENSHOT_INTERVAL       # 服务端下发的截图间隔


def record_activity():
    """记录用户活动时间戳，供自适应频率控制器使用"""
    global _last_activity_time
    _last_activity_time = time.time()


def main():
    global _server_interval
    platform = "Windows" if IS_WINDOWS else ("Linux" if IS_LINUX else "?")
    reporter = Reporter(SERVER_URL, AGENT_NAME)

    print("=" * 50)
    print(f"  Monitor Agent - 精简版")
    print(f"  平台: {platform}")
    print(f"  名称: {AGENT_NAME}")
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
        if input("  继续? (y/n): ").lower() != 'y':
            return

    # 上报上线
    reporter._post("status", {
        "agent_name": AGENT_NAME,
        "status": "online",
        "message": f"Agent started ({platform})",
    })

    # 启动采集模块
    screenshot = ScreenCapture(interval=SCREENSHOT_INTERVAL)
    screenshot.add_listener(reporter.screenshot)

    window = AppTracker(interval=APP_TRACK_INTERVAL)

    def on_app_switch_with_screenshot(info):
        """窗口切换时立即触发一次截图，确保有时间戳接近的截图"""
        shot_data = screenshot.capture_once()
        if shot_data:
            reporter.screenshot(shot_data)
            info["screenshot_timestamp"] = shot_data["timestamp"]
        reporter.window(info)
        record_activity()  # 窗口切换也视为活动

    window.add_listener(on_app_switch_with_screenshot)

    browser = BrowserHistoryCollector(interval=BROWSER_HISTORY_INTERVAL)
    browser.add_listener(reporter.browser)

    # 键盘 Enter 监控 — 聊天应用发送消息时触发截图
    keyboard_monitor = KeyboardEnterMonitor()

    def on_chat_enter(info):
        """Enter 键在聊天应用中按下 → 立即截图 + 上报事件"""
        shot_data = screenshot.capture_once()
        if shot_data:
            reporter.screenshot(shot_data)
            # 嵌入截图时间戳，供服务端精确关联事件与截图
            info["screenshot_timestamp"] = shot_data["timestamp"]
        reporter.chat_enter(info)
        record_activity()  # 标记活动，触发高频截图

    keyboard_monitor.add_listener(on_chat_enter)

    screenshot.start()
    window.start()
    browser.start()
    keyboard_monitor.start()

    # 心跳线程
    def heartbeat_loop():
        while True:
            reporter.heartbeat()
            time.sleep(HEARTBEAT_INTERVAL)

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    # 服务端配置轮询 — 只更新 _server_interval，最终由频率控制器裁决
    def config_poller():
        global _server_interval
        while True:
            try:
                r = requests.get(
                    f"{SERVER_URL}/api/config?agent={AGENT_NAME}",
                    timeout=5
                )
                if r.status_code == 200:
                    cfg = r.json()
                    new_interval = cfg.get("screenshot_interval", SCREENSHOT_INTERVAL)
                    if new_interval != _server_interval:
                        _server_interval = new_interval
                        status = "LIVE" if new_interval <= 1.5 else "IDLE"
                        print(f"  [>>] 观察状态: {status}  服务端间隔: {new_interval}s")
            except Exception:
                pass
            time.sleep(3)

    threading.Thread(target=config_poller, daemon=True).start()

    # 自适应截图频率控制器 — 本地活动优先于服务端配置
    def screenshot_frequency_controller():
        global _server_interval
        ACTIVE_INTERVAL = 0.25    # 活跃 → 每秒 4 次
        IDLE_INTERVAL = 5.0        # 空闲 → 每 5 秒 1 次
        IDLE_THRESHOLD = 60.0      # 1 分钟无活动视为空闲
        last_interval = None

        while True:
            idle_sec = time.time() - _last_activity_time
            is_active = idle_sec < IDLE_THRESHOLD

            if is_active:
                target = ACTIVE_INTERVAL
            elif _server_interval <= 1.5:
                target = _server_interval  # 观察者正在查看 → 1s
            else:
                target = IDLE_INTERVAL

            if target != last_interval:
                screenshot.interval = target
                if is_active:
                    mode = f"ACTIVE ({idle_sec:.0f}s 空闲)"
                elif target <= 1.5:
                    mode = "VIEWER"
                else:
                    mode = "IDLE"
                print(f"  [Adaptive] {mode}  截图间隔: {target}s")
                last_interval = target

            time.sleep(1)

    threading.Thread(target=screenshot_frequency_controller, daemon=True).start()

    print("\n  Agent 运行中, Ctrl+C 停止\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  正在停止...")
        reporter._post("status", {
            "agent_name": AGENT_NAME,
            "status": "offline",
            "message": "Agent stopped",
        })
        screenshot.stop()
        window.stop()
        browser.stop()
        keyboard_monitor.stop()
        print("  Agent 已停止")


if __name__ == "__main__":
    main()
