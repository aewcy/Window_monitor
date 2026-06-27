"""
Agent 配置文件 - 运行在试验机（被监控机器）上
跨平台支持: Windows / Linux
"""
import os
import sys
import socket

# ============================================
# 平台检测
# ============================================
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

# ============================================
# 服务端地址 - 监控机的地址
# ============================================
SERVER_HOST = os.environ.get("MONITOR_SERVER_HOST", "108.187.15.71")
SERVER_PORT = int(os.environ.get("MONITOR_SERVER_PORT", "8899"))
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# ============================================
# Agent 标识 — 默认用主机名，天然唯一
# ============================================
def _get_default_agent_name():
    """基于主机名生成默认 Agent 名称"""
    hostname = socket.gethostname()
    return hostname.split('.')[0]  # 去掉域名后缀

AGENT_NAME = os.environ.get("AGENT_NAME", _get_default_agent_name())


# ============================================
# 硬件唯一标识 — 同一台机器始终相同，重启/升级 .exe 不变
# ============================================
def get_machine_id() -> str:
    """获取本机硬件唯一标识码（Windows MachineGuid）"""
    if IS_WINDOWS:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography"
            )
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            if guid:
                return guid
        except Exception:
            pass
    # 回退: 用主机名（跨平台兜底）
    return socket.gethostname()

# ============================================
# 采集间隔配置（秒）
# ============================================
SCREENSHOT_INTERVAL = int(os.environ.get("SCREENSHOT_INTERVAL", "30"))
APP_TRACK_INTERVAL = int(os.environ.get("APP_TRACK_INTERVAL", "5"))
BROWSER_HISTORY_INTERVAL = int(os.environ.get("BROWSER_HISTORY_INTERVAL", "60"))

# ============================================
# 截图配置
# ============================================
SCREENSHOT_QUALITY = int(os.environ.get("SCREENSHOT_QUALITY", "60"))
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

# ============================================
# 键盘监控配置 — 前台白名单 Enter 键检测
# ============================================
KEYBOARD_MONITOR_ENABLED = os.environ.get("KEYBOARD_MONITOR_ENABLED", "true").lower() in ("true", "1", "yes")
KEYBOARD_MONITOR_COOLDOWN = float(os.environ.get("KEYBOARD_MONITOR_COOLDOWN", "0.5"))

# 前台白名单: 当前台窗口进程名命中此名单时，Enter 键触发截图
# 格式: process_name → display_name
if IS_WINDOWS:
    FOREGROUND_WHITELIST = {
        "WeChat.exe": "WeChat",
        "Weixin.exe": "WeChat",
        "QQ.exe": "QQ",
        "TIM.exe": "QQ",
        "DingTalk.exe": "DingTalk",
        "DingTalkLauncher.exe": "DingTalk",
        "Telegram.exe": "Telegram",
        "slack.exe": "Slack",
        "Teams.exe": "Microsoft Teams",
        "Discord.exe": "Discord",
        "Skype.exe": "Skype",
        "WhatsApp.exe": "WhatsApp",
        "Line.exe": "Line",
        "Viber.exe": "Viber",
        "Lark.exe": "Lark",
        "LarkRt.exe": "Lark",
        "Feishu.exe": "Feishu",
        "FeishuRt.exe": "Feishu",
    }
elif IS_LINUX:
    FOREGROUND_WHITELIST = {
        "telegram-desktop": "Telegram",
        "slack": "Slack",
        "discord": "Discord",
        "teams": "Microsoft Teams",
        "whatsapp-nativefier": "WhatsApp",
        "wechat": "WeChat",
        "electronic-wechat": "WeChat",
        "qq": "QQ",
    }
else:
    FOREGROUND_WHITELIST = {}


def get_local_ip() -> str:
    """获取本机所有非回环网卡 IP，逗号分隔"""
    import socket
    import subprocess

    ips = []
    try:
        # 方法1: 通过 socket 连接外部地址获取主 IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    # 方法2: 通过 ipconfig 获取所有网卡 IP（Windows）
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["ipconfig"], capture_output=True, text=True, timeout=3,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            import re
            for line in result.stdout.splitlines():
                m = re.search(r"IPv4[^:]*:\s*([\d.]+)", line)
                if m and m.group(1) not in ips:
                    ips.append(m.group(1))
        except Exception:
            pass

    return ",".join(ips) if ips else ""
