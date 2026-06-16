"""
Server 日志模块 — 文件日志 + 控制台输出
支持按天轮转，自动清理旧日志
"""
import os
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from config import DATA_DIR

LOG_DIR = Path(DATA_DIR) / "logs"

# 日志分类 → 中文标签
CATEGORIES = {
    "network": "网络问题",
    "storage": "存储问题",
    "capture": "采集异常",
    "system": "系统状态",
    "security": "安全警告",
    "server": "服务端",
}

LEVELS = ["INFO", "WARNING", "ERROR"]

# 日志格式: [时间] [分类] LEVEL 消息
LOG_FORMAT = "%(asctime)s [%(category)s] %(levelname)s %(message)s"
DATE_FORMAT = "%H:%M:%S"


class CategoryFormatter(logging.Formatter):
    """支持 category 字段的自定义格式化器"""

    def format(self, record):
        if not hasattr(record, "category"):
            record.category = "server"
        return super().format(record)


def _get_logger() -> logging.Logger:
    """获取 Server 日志器（单例）"""
    logger = logging.getLogger("monitor-server")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    os.makedirs(LOG_DIR, exist_ok=True)

    formatter = CategoryFormatter(LOG_FORMAT, DATE_FORMAT)

    # 控制台
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    # 文件 — 按天轮转，保留 30 天
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "server.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    # 每天轮转时重命名为 server-YYYY-MM-DD.log
    file_handler.suffix = "%Y-%m-%d"
    logger.addHandler(file_handler)

    return logger


# 模块级 logger，其他模块 `from logger import log` 即可用
log = _get_logger()


def format_log_entry(category: str, level: str, message: str) -> str:
    """生成与文件日志一致的格式化字符串（供 DB 存储/前端展示）"""
    now = datetime.now().strftime("%H:%M:%S")
    cat_cn = CATEGORIES.get(category, category)
    return f"[{now}] [{cat_cn}] {level} {message}"
