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
        })

    def browser(self, records: list):
        ok = self._post("browser_history", {
            "agent_name": self.agent,
            "records": records,
        })
        if ok:
            print(f"  [OK] 浏览器 {len(records)} 条")

    def heartbeat(self):
        self._post("heartbeat", {"agent_name": self.agent})


# ============================================
# Agent 主控
# ============================================

def main():
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
    window.add_listener(reporter.window)

    browser = BrowserHistoryCollector(interval=BROWSER_HISTORY_INTERVAL)
    browser.add_listener(reporter.browser)

    screenshot.start()
    window.start()
    browser.start()

    # 心跳线程
    def heartbeat_loop():
        while True:
            reporter.heartbeat()
            time.sleep(HEARTBEAT_INTERVAL)

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    # 动态配置轮询 - 根据 Dashboard 是否有人观察调整截图频率
    def config_poller():
        while True:
            try:
                r = requests.get(
                    f"{SERVER_URL}/api/config?agent={AGENT_NAME}",
                    timeout=5
                )
                if r.status_code == 200:
                    cfg = r.json()
                    new_interval = cfg.get("screenshot_interval", SCREENSHOT_INTERVAL)
                    # 只在变化时更新，减少日志噪音
                    if new_interval != screenshot.interval:
                        screenshot.interval = new_interval
                        status = "LIVE" if new_interval == 1 else "IDLE"
                        print(f"  [>>] 观察状态: {status}  截图间隔: {new_interval}s")
            except Exception:
                pass
            time.sleep(3)  # 每3秒检查一次

    threading.Thread(target=config_poller, daemon=True).start()

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
        print("  Agent 已停止")


if __name__ == "__main__":
    main()
