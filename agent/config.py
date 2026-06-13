"""
Agent 配置文件 - 运行在试验机（被监控机器）上
跨平台支持: Windows / Linux
"""
import os
import sys

# ============================================
# 平台检测
# ============================================
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

# ============================================
# 服务端地址 - 监控机的地址
# ============================================
SERVER_HOST = os.environ.get("MONITOR_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("MONITOR_SERVER_PORT", "8899"))
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# ============================================
# Agent 标识
# ============================================
AGENT_NAME = os.environ.get("AGENT_NAME", "试验机-01")

# ============================================
# 采集间隔配置（秒）
# ============================================
SCREENSHOT_INTERVAL = int(os.environ.get("SCREENSHOT_INTERVAL", "30"))
APP_TRACK_INTERVAL = int(os.environ.get("APP_TRACK_INTERVAL", "5"))
BROWSER_HISTORY_INTERVAL = int(os.environ.get("BROWSER_HISTORY_INTERVAL", "60"))

# ============================================
# 截图配置
# ============================================
SCREENSHOT_QUALITY = int(os.environ.get("SCREENSHOT_QUALITY", "40"))
SCREENSHOT_MAX_WIDTH = int(os.environ.get("SCREENSHOT_MAX_WIDTH", "1280"))

# ============================================
# 浏览器历史配置
# ============================================
if IS_WINDOWS:
    BROWSER_PATHS = {
        "chrome": os.path.expandvars(
            r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\History"
        ),
        "edge": os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History"
        ),
        "firefox": os.path.expandvars(
            r"%APPDATA%\Mozilla\Firefox\Profiles"
        ),
    }
elif IS_LINUX:
    BROWSER_PATHS = {
        "chrome": os.path.expanduser("~/.config/google-chrome/Default/History"),
        "chromium": os.path.expanduser("~/.config/chromium/Default/History"),
        "edge": os.path.expanduser("~/.config/microsoft-edge/Default/History"),
        "brave": os.path.expanduser("~/.config/BraveSoftware/Brave-Browser/Default/History"),
        "firefox": os.path.expanduser("~/.mozilla/firefox"),
    }
else:
    BROWSER_PATHS = {}

# ============================================
# 心跳配置
# ============================================
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "15"))

# ============================================
# 数据上传重试配置
# ============================================
RETRY_TIMES = int(os.environ.get("RETRY_TIMES", "3"))
RETRY_DELAY = int(os.environ.get("RETRY_DELAY", "5"))
