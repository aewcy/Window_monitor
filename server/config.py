"""
服务端配置
"""
import os

# 服务监听
HOST = os.environ.get("SERVER_HOST", "0.0.0.0")  # 绑定所有网卡
PORT = int(os.environ.get("SERVER_PORT", "8899"))

# 数据存储目录
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")
DB_PATH = os.path.join(DATA_DIR, "monitor.db")

# 认证 - TODO: 后续版本实现
# AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "false").lower() == "true"
# ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
# ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

# 数据清理 - TODO: 后续版本实现自动清理
# MAX_SCREENSHOT_AGE_DAYS = int(os.environ.get("MAX_SCREENSHOT_AGE_DAYS", "7"))
# MAX_HISTORY_DAYS = int(os.environ.get("MAX_HISTORY_DAYS", "30"))

# CORS - 开发时允许所有来源
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
