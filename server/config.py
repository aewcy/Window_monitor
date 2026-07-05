"""
服务端配置
"""
import os


def _get_int_env(name: str, default: int) -> int:
    """读取整数环境变量，非法值回退默认值。"""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# 服务监听
HOST = os.environ.get("SERVER_HOST", "0.0.0.0")  # 绑定所有网卡
PORT = _get_int_env("SERVER_PORT", 8899)
AGENT_API_PORT = _get_int_env("AGENT_API_PORT", 8899)
WEB_PUBLIC_PORT = _get_int_env("WEB_PUBLIC_PORT", 14325)

# 数据存储目录
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
DB_PATH = os.path.join(DATA_DIR, "monitor.db")

# 截图保留与清理策略
SCREENSHOT_RETENTION_HOURS = _get_int_env("SCREENSHOT_RETENTION_HOURS", 168)
SCREENSHOT_CLEANUP_INTERVAL_MINUTES = _get_int_env("SCREENSHOT_CLEANUP_INTERVAL_MINUTES", 30)

# CORS - 允许 Dashboard 跨域访问
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
