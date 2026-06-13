"""
数据模型和数据库操作
使用 SQLite 存储结构化数据，文件系统存储截图
"""
import os
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Optional

from config import DB_PATH, SCREENSHOT_DIR


# 线程本地存储，每个线程使用自己的连接
_local = threading.local()


def get_db() -> sqlite3.Connection:
    """获取当前线程的数据库连接"""
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    """初始化数据库表"""
    db = get_db()
    db.executescript("""
        -- Agent 状态表
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'offline',
            last_seen TEXT,
            first_seen TEXT DEFAULT (datetime('now', 'localtime')),
            message TEXT DEFAULT ''
        );

        -- 截图索引表 (图片文件存文件系统)
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            FOREIGN KEY (agent_name) REFERENCES agents(name)
        );
        CREATE INDEX IF NOT EXISTS idx_screenshots_agent_time
            ON screenshots(agent_name, timestamp DESC);

        -- 应用使用事件表
        CREATE TABLE IF NOT EXISTS app_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            window_title TEXT DEFAULT '',
            process_name TEXT DEFAULT '',
            process_path TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            duration_seconds REAL DEFAULT 0,
            FOREIGN KEY (agent_name) REFERENCES agents(name)
        );
        CREATE INDEX IF NOT EXISTS idx_app_events_agent_time
            ON app_events(agent_name, timestamp DESC);

        -- 浏览器历史记录表
        CREATE TABLE IF NOT EXISTS browser_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT DEFAULT '',
            visit_count INTEGER DEFAULT 1,
            last_visit TEXT NOT NULL,
            browser TEXT DEFAULT 'unknown',
            reported_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (agent_name) REFERENCES agents(name)
        );
        CREATE INDEX IF NOT EXISTS idx_browser_history_agent_time
            ON browser_history(agent_name, last_visit DESC);

        -- 系统事件日志
        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT DEFAULT '',
            timestamp TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_event_log_agent_time
            ON event_log(agent_name, timestamp DESC);
    """)
    db.commit()


# ============================================
# Agent 管理
# ============================================

def upsert_agent(name: str, status: str = "online", message: str = ""):
    db = get_db()
    db.execute(
        """INSERT INTO agents (name, status, last_seen, message)
           VALUES (?, ?, datetime('now', 'localtime'), ?)
           ON CONFLICT(name) DO UPDATE SET
             status=excluded.status,
             last_seen=excluded.last_seen,
             message=excluded.message""",
        (name, status, message)
    )
    db.commit()


def get_agents() -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM agents ORDER BY last_seen DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ============================================
# 截图管理
# ============================================

def save_screenshot(agent_name: str, timestamp: str, image_b64: str) -> int | None:
    """将截图保存到文件系统，索引写入数据库"""
    import base64

    try:
        # 生成文件路径: data/screenshots/{agent}/{date}/{timestamp}.jpg
        date_str = timestamp[:10]  # YYYY-MM-DD
        dir_path = os.path.join(SCREENSHOT_DIR, agent_name, date_str)
        os.makedirs(dir_path, exist_ok=True)

        ts_safe = timestamp.replace(":", "-").replace("T", "_")
        file_name = f"{ts_safe}.jpg"
        file_path = os.path.join(dir_path, file_name)

        # 解码并写入
        image_data = base64.b64decode(image_b64)
        with open(file_path, "wb") as f:
            f.write(image_data)

        file_size = len(image_data)

        # 写入数据库索引
        db = get_db()
        cursor = db.execute(
            """INSERT INTO screenshots (agent_name, timestamp, file_path, file_size)
               VALUES (?, ?, ?, ?)""",
            (agent_name, timestamp, file_path, file_size)
        )
        db.commit()
        return cursor.lastrowid

    except Exception as e:
        print(f"[DB] 保存截图失败: {e}")
        return None


def get_screenshots(agent_name: str = None, limit: int = 50, offset: int = 0,
                    date_from: str = None, date_to: str = None) -> list[dict]:
    """查询截图列表"""
    db = get_db()
    conditions = []
    params = []

    if agent_name:
        conditions.append("agent_name = ?")
        params.append(agent_name)
    if date_from:
        conditions.append("timestamp >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("timestamp <= ?")
        params.append(date_to)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""SELECT * FROM screenshots {where}
              ORDER BY timestamp DESC LIMIT ? OFFSET ?"""
    params.extend([limit, offset])

    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_latest_screenshot(agent_name: str) -> dict | None:
    """获取最新截图"""
    db = get_db()
    row = db.execute(
        "SELECT * FROM screenshots WHERE agent_name = ? ORDER BY timestamp DESC LIMIT 1",
        (agent_name,)
    ).fetchone()
    return dict(row) if row else None


# ============================================
# 应用事件
# ============================================

def save_app_event(agent_name: str, data: dict):
    db = get_db()
    db.execute(
        """INSERT INTO app_events
           (agent_name, event_type, window_title, process_name, process_path,
            timestamp, duration_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            agent_name,
            data.get("type", "unknown"),
            data.get("window_title", ""),
            data.get("process_name", ""),
            data.get("process_path", ""),
            data.get("timestamp", datetime.now().isoformat()),
            data.get("duration_seconds", 0),
        )
    )
    db.commit()


def get_app_usage_summary(agent_name: str, date: str = None) -> list[dict]:
    """获取应用使用汇总（按进程聚合时长）"""
    db = get_db()
    if date:
        sql = """SELECT process_name,
                        COUNT(*) as switch_count,
                        SUM(duration_seconds) as total_seconds,
                        MAX(window_title) as last_window_title
                 FROM app_events
                 WHERE agent_name = ? AND date(timestamp) = ?
                   AND event_type IN ('app_heartbeat', 'app_start')
                 GROUP BY process_name
                 ORDER BY total_seconds DESC
                 LIMIT 20"""
        rows = db.execute(sql, (agent_name, date)).fetchall()
    else:
        sql = """SELECT process_name,
                        COUNT(*) as switch_count,
                        SUM(duration_seconds) as total_seconds,
                        MAX(window_title) as last_window_title
                 FROM app_events
                 WHERE agent_name = ?
                   AND event_type IN ('app_heartbeat', 'app_start')
                 GROUP BY process_name
                 ORDER BY total_seconds DESC
                 LIMIT 20"""
        rows = db.execute(sql, (agent_name,)).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["total_minutes"] = round(d["total_seconds"] / 60, 1)
        results.append(d)
    return results


def get_app_events(agent_name: str, limit: int = 50) -> list[dict]:
    """最近应用事件时间线"""
    db = get_db()
    rows = db.execute(
        """SELECT * FROM app_events
           WHERE agent_name = ?
           ORDER BY timestamp DESC LIMIT ?""",
        (agent_name, limit)
    ).fetchall()
    return [dict(r) for r in rows]


# ============================================
# 浏览器历史
# ============================================

def save_browser_history(agent_name: str, records: list[dict]):
    """批量保存浏览器历史"""
    db = get_db()
    data = [
        (
            agent_name,
            rec.get("url", ""),
            rec.get("title", ""),
            rec.get("visit_count", 1),
            rec.get("last_visit", datetime.now().isoformat()),
            rec.get("browser", "unknown"),
        )
        for rec in records
    ]
    db.executemany(
        """INSERT OR IGNORE INTO browser_history
           (agent_name, url, title, visit_count, last_visit, browser)
           VALUES (?, ?, ?, ?, ?, ?)""",
        data
    )
    db.commit()


def get_browser_history(agent_name: str = None, limit: int = 100,
                        offset: int = 0) -> list[dict]:
    """查询浏览器历史"""
    db = get_db()
    if agent_name:
        rows = db.execute(
            """SELECT * FROM browser_history
               WHERE agent_name = ?
               ORDER BY last_visit DESC LIMIT ? OFFSET ?""",
            (agent_name, limit, offset)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM browser_history ORDER BY last_visit DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows]


# ============================================
# 统计
# ============================================

def get_dashboard_stats(agent_name: str = None) -> dict:
    """获取仪表盘统计数据"""
    db = get_db()

    stats = {}

    # 截图总数
    if agent_name:
        stats["total_screenshots"] = db.execute(
            "SELECT COUNT(*) FROM screenshots WHERE agent_name = ?", (agent_name,)
        ).fetchone()[0]
    else:
        stats["total_screenshots"] = db.execute(
            "SELECT COUNT(*) FROM screenshots"
        ).fetchone()[0]

    # 今日应用事件数
    today = datetime.now().strftime("%Y-%m-%d")
    if agent_name:
        stats["today_app_events"] = db.execute(
            "SELECT COUNT(*) FROM app_events WHERE agent_name = ? AND date(timestamp) = ?",
            (agent_name, today)
        ).fetchone()[0]
    else:
        stats["today_app_events"] = db.execute(
            "SELECT COUNT(*) FROM app_events WHERE date(timestamp) = ?", (today,)
        ).fetchone()[0]

    # 浏览器记录总数
    if agent_name:
        stats["total_browser_records"] = db.execute(
            "SELECT COUNT(*) FROM browser_history WHERE agent_name = ?", (agent_name,)
        ).fetchone()[0]
    else:
        stats["total_browser_records"] = db.execute(
            "SELECT COUNT(*) FROM browser_history"
        ).fetchone()[0]

    # 在线 agent 数
    stats["online_agents"] = db.execute(
        "SELECT COUNT(*) FROM agents WHERE status = 'online'"
    ).fetchone()[0]

    return stats
