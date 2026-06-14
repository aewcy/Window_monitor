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

# CORS - 允许 Dashboard 跨域访问
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
