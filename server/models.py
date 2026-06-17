"""
数据模型和数据库操作
使用 SQLite 存储结构化数据，文件系统存储截图
"""
import os
import sqlite3
import threading
from datetime import datetime

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
            display_name TEXT DEFAULT '',
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
            FOREIGN KEY (agent_name) REFERENCES agents(name),
            UNIQUE(agent_name, url, last_visit)
        );
        CREATE INDEX IF NOT EXISTS idx_browser_history_agent_time
            ON browser_history(agent_name, last_visit DESC);

        -- 诊断日志表 (Agent 上报 + Server 内部)
        CREATE TABLE IF NOT EXISTS diagnostic_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT DEFAULT '',
            category TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'INFO',
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (agent_name) REFERENCES agents(name)
        );
        CREATE INDEX IF NOT EXISTS idx_diag_time
            ON diagnostic_logs(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_diag_category
            ON diagnostic_logs(category, level);

    """)
    db.commit()

    # 向前兼容迁移: 为已存在的 app_events 表添加 display_name 列
    try:
        db.execute("ALTER TABLE app_events ADD COLUMN display_name TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 向前兼容迁移: 为已存在的 app_events 表添加 screenshot_timestamp 列
    try:
        db.execute("ALTER TABLE app_events ADD COLUMN screenshot_timestamp TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 向前兼容迁移: 为 screenshots 表添加 monitor_index / monitor_total
    try:
        db.execute("ALTER TABLE screenshots ADD COLUMN monitor_index INTEGER DEFAULT 0")
        db.commit()
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE screenshots ADD COLUMN monitor_total INTEGER DEFAULT 1")
        db.commit()
    except sqlite3.OperationalError:
        pass

    # 向前兼容迁移: 为 agents 表添加 display_name 列（Web 端自定义显示名）
    try:
        db.execute("ALTER TABLE agents ADD COLUMN display_name TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在


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


def delete_agent(name: str) -> dict | None:
    """删除 Agent 及其所有关联数据（截图文件+DB、应用事件、浏览器历史）

    返回: {"deleted": {...}} 成功时；None 表示 Agent 不存在
    """
    import re
    import shutil

    # 安全检查：拒绝含路径遍历字符的恶意 agent 名
    if not name or not re.match(r'^[a-zA-Z0-9_.\-]+$', name):
        print(f"[DB] 拒绝非法 agent 名称: {repr(name)}")
        return None

    db = get_db()

    # 检查 Agent 是否存在
    exists = db.execute("SELECT 1 FROM agents WHERE name = ?", (name,)).fetchone()
    if not exists:
        return None

    result = {"deleted": {"screenshots": 0, "app_events": 0, "browser_history": 0}}

    # 1. 删除截图文件（文件系统）
    agent_shot_dir = os.path.join(SCREENSHOT_DIR, name)
    if os.path.isdir(agent_shot_dir):
        try:
            shutil.rmtree(agent_shot_dir)
        except OSError as e:
            print(f"[DB] 删除截图目录失败 {agent_shot_dir}: {e}")

    # 2. 删除截图数据库记录（先于 agent 删除，因为有外键）
    cursor = db.execute("DELETE FROM screenshots WHERE agent_name = ?", (name,))
    result["deleted"]["screenshots"] = cursor.rowcount

    # 3. 删除应用事件
    cursor = db.execute("DELETE FROM app_events WHERE agent_name = ?", (name,))
    result["deleted"]["app_events"] = cursor.rowcount

    # 4. 删除浏览器历史
    cursor = db.execute("DELETE FROM browser_history WHERE agent_name = ?", (name,))
    result["deleted"]["browser_history"] = cursor.rowcount

    # 5. 删除 Agent 自身
    db.execute("DELETE FROM agents WHERE name = ?", (name,))
    db.commit()

    print(f"[DB] Agent 已删除: {name} — 截图:{result['deleted']['screenshots']} 事件:{result['deleted']['app_events']} 历史:{result['deleted']['browser_history']}")
    return result


def rename_agent(name: str, display_name: str) -> bool:
    """设置 Agent 显示名称（不影响 Agent 端上报的原始 name）"""
    if not name or not display_name:
        return False
    db = get_db()
    cursor = db.execute(
        "UPDATE agents SET display_name = ? WHERE name = ?",
        (display_name.strip(), name)
    )
    db.commit()
    return cursor.rowcount > 0


# ============================================
# 截图管理
# ============================================

def save_screenshot(agent_name: str, timestamp: str, image_b64: str,
                    monitor_index: int = 0, monitor_total: int = 1) -> int | None:
    """将截图保存到文件系统，索引写入数据库

    节流策略: 每屏 2 秒窗口内已有截图则跳过，保留最早一张 (4fps 采集 → ~0.5fps/屏 存储)
    """
    import base64
    from datetime import datetime, timedelta

    try:
        db = get_db()

        # 节流: 2 秒窗口内已有截图则跳过
        try:
            parsed = datetime.fromisoformat(timestamp)
            window_start = (parsed - timedelta(seconds=2)).isoformat()
        except ValueError:
            window_start = timestamp  # 解析失败则不做节流

        existing = db.execute(
            """SELECT id FROM screenshots
               WHERE agent_name = ? AND timestamp >= ? AND monitor_index = ?
               ORDER BY timestamp ASC LIMIT 1""",
            (agent_name, window_start, monitor_index)
        ).fetchone()
        if existing:
            return existing["id"]  # 已有截图，跳过保存

        # 生成文件路径: data/screenshots/{agent}/{date}/{timestamp}.jpg
        date_str = timestamp[:10]  # YYYY-MM-DD
        dir_path = os.path.join(SCREENSHOT_DIR, agent_name, date_str)
        os.makedirs(dir_path, exist_ok=True)

        ts_safe = timestamp.replace(":", "-").replace("T", "_")
        file_name = f"{ts_safe}_m{monitor_index}.jpg"
        file_path = os.path.join(dir_path, file_name)

        # 解码并写入
        image_data = base64.b64decode(image_b64)
        with open(file_path, "wb") as f:
            f.write(image_data)

        file_size = len(image_data)

        # 写入数据库索引
        cursor = db.execute(
            """INSERT INTO screenshots (agent_name, timestamp, file_path, file_size,
                       monitor_index, monitor_total)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (agent_name, timestamp, file_path, file_size, monitor_index, monitor_total)
        )
        db.commit()
        return cursor.lastrowid

    except Exception as e:
        print(f"[DB] 保存截图失败: {e}")
        return None


def get_screenshots(agent_name: str = None, limit: int = 50, offset: int = 0,
                    date_from: str = None, date_to: str = None,
                    monitor_index: int = None) -> list[dict]:
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
    if monitor_index is not None:
        conditions.append("monitor_index = ?")
        params.append(monitor_index)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""SELECT * FROM screenshots {where}
              ORDER BY timestamp DESC LIMIT ? OFFSET ?"""
    params.extend([limit, offset])

    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def delete_screenshot(screenshot_id: int) -> bool:
    """删除单张截图（文件 + DB 索引）"""
    db = get_db()
    row = db.execute("SELECT file_path FROM screenshots WHERE id = ?", (screenshot_id,)).fetchone()
    if not row:
        return False
    # 删除文件
    try:
        if os.path.exists(row["file_path"]):
            os.remove(row["file_path"])
    except OSError:
        pass
    # 删除索引
    db.execute("DELETE FROM screenshots WHERE id = ?", (screenshot_id,))
    db.commit()
    return True


def delete_screenshots_batch(ids: list[int]) -> int:
    """批量删除截图，返回成功删除数量"""
    count = 0
    for sid in ids:
        if delete_screenshot(sid):
            count += 1
    return count


def get_latest_screenshot(agent_name: str, monitor_index: int = None) -> dict | None:
    """获取最新截图，可选指定显示器"""
    db = get_db()
    if monitor_index is not None:
        row = db.execute(
            "SELECT * FROM screenshots WHERE agent_name = ? AND monitor_index = ? ORDER BY timestamp DESC LIMIT 1",
            (agent_name, monitor_index)
        ).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM screenshots WHERE agent_name = ? ORDER BY timestamp DESC LIMIT 1",
            (agent_name,)
        ).fetchone()
    return dict(row) if row else None


def get_screenshot_dates(agent_name: str) -> list[dict]:
    """返回指定 Agent 有截图的日期列表及每天数量，供日历组件使用"""
    db = get_db()
    rows = db.execute(
        """SELECT substr(timestamp, 1, 10) as date,
                  COUNT(*) as count
           FROM screenshots
           WHERE agent_name = ?
           GROUP BY date
           ORDER BY date ASC""",
        (agent_name,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_screenshot_hours(agent_name: str, date_str: str) -> list[dict]:
    """返回指定日期内有截图的小时列表及每小时数量"""
    db = get_db()
    rows = db.execute(
        """SELECT substr(timestamp, 12, 2) as hour,
                  COUNT(*) as count
           FROM screenshots
           WHERE agent_name = ?
             AND timestamp >= ?
             AND timestamp <= ?
           GROUP BY hour
           ORDER BY hour ASC""",
        (agent_name, date_str, date_str + "T23:59:59")
    ).fetchall()
    return [dict(r) for r in rows]


# ============================================
# 应用事件
# ============================================

def save_app_event(agent_name: str, data: dict):
    db = get_db()
    db.execute(
        """INSERT INTO app_events
           (agent_name, event_type, window_title, process_name, process_path,
            display_name, timestamp, duration_seconds, screenshot_timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            agent_name,
            data.get("type", "unknown"),
            data.get("window_title", ""),
            data.get("process_name", ""),
            data.get("process_path", ""),
            data.get("display_name", ""),
            data.get("timestamp", datetime.now().isoformat()),
            data.get("duration_seconds", 0),
            data.get("screenshot_timestamp", ""),
        )
    )
    db.commit()


def get_app_usage_summary(agent_name: str, date: str = None) -> list[dict]:
    """获取应用使用汇总（按进程聚合时长）"""
    db = get_db()
    conditions = ["agent_name = ?"]
    params = [agent_name]
    if date:
        conditions.append("date(timestamp) = ?")
        params.append(date)
    where = " AND ".join(conditions)
    sql = f"""SELECT process_name,
                     COUNT(*) as switch_count,
                     SUM(duration_seconds) as total_seconds,
                     MAX(window_title) as last_window_title
              FROM app_events
              WHERE {where}
              GROUP BY process_name
              ORDER BY total_seconds DESC
              LIMIT 20"""
    rows = db.execute(sql, params).fetchall()
    return [{**dict(r), "total_minutes": round(dict(r)["total_seconds"] / 60, 1)} for r in rows]


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


def get_app_events_with_screenshots(agent_name: str, limit: int = 50) -> list[dict]:
    """最近应用事件时间线，每条关联最近时间的截图

    匹配策略 (按优先级):
    1. 精确匹配 — 事件携带 screenshot_timestamp 时直接关联 (Enter/窗口切换触发的即时截图)
    2. 事后兜底 — 事件后任意时间的最近截图
    3. 事前兜底 — 事件前最近的截图
    """
    db = get_db()
    rows = db.execute("""
        SELECT ae.*,
            COALESCE(
                (SELECT s.id FROM screenshots s
                 WHERE s.agent_name = ae.agent_name
                   AND ae.screenshot_timestamp != ''
                   AND s.timestamp = ae.screenshot_timestamp
                 LIMIT 1),
                (SELECT s.id FROM screenshots s
                 WHERE s.agent_name = ae.agent_name AND s.timestamp >= ae.timestamp
                 ORDER BY s.timestamp ASC LIMIT 1),
                (SELECT s.id FROM screenshots s
                 WHERE s.agent_name = ae.agent_name AND s.timestamp <= ae.timestamp
                 ORDER BY s.timestamp DESC LIMIT 1)
            ) as screenshot_id,
            COALESCE(
                (SELECT s.timestamp FROM screenshots s
                 WHERE s.agent_name = ae.agent_name
                   AND ae.screenshot_timestamp != ''
                   AND s.timestamp = ae.screenshot_timestamp
                 LIMIT 1),
                (SELECT s.timestamp FROM screenshots s
                 WHERE s.agent_name = ae.agent_name AND s.timestamp >= ae.timestamp
                 ORDER BY s.timestamp ASC LIMIT 1),
                (SELECT s.timestamp FROM screenshots s
                 WHERE s.agent_name = ae.agent_name AND s.timestamp <= ae.timestamp
                 ORDER BY s.timestamp DESC LIMIT 1)
            ) as screenshot_time
        FROM app_events ae
        WHERE ae.agent_name = ?
        ORDER BY ae.timestamp DESC
        LIMIT ?
    """, (agent_name, limit)).fetchall()
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


def get_browser_history_with_screenshots(agent_name: str = None, limit: int = 100,
                                          offset: int = 0) -> list[dict]:
    """查询浏览器历史，每条记录关联最近时间的截图

    匹配策略: 优先访前截图 → 兜底访后截图
    """
    db = get_db()
    if agent_name:
        rows = db.execute(
            """SELECT bh.*,
               COALESCE(
                   (SELECT s.id FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND s.timestamp <= bh.last_visit
                    ORDER BY s.timestamp DESC LIMIT 1),
                   (SELECT s.id FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND s.timestamp >= bh.last_visit
                    ORDER BY s.timestamp ASC LIMIT 1)
               ) as screenshot_id,
               COALESCE(
                   (SELECT s.timestamp FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND s.timestamp <= bh.last_visit
                    ORDER BY s.timestamp DESC LIMIT 1),
                   (SELECT s.timestamp FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND s.timestamp >= bh.last_visit
                    ORDER BY s.timestamp ASC LIMIT 1)
               ) as screenshot_time
            FROM browser_history bh
            WHERE bh.agent_name = ?
            ORDER BY bh.last_visit DESC LIMIT ? OFFSET ?""",
            (agent_name, limit, offset)
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT bh.*,
               COALESCE(
                   (SELECT s.id FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND s.timestamp <= bh.last_visit
                    ORDER BY s.timestamp DESC LIMIT 1),
                   (SELECT s.id FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND s.timestamp >= bh.last_visit
                    ORDER BY s.timestamp ASC LIMIT 1)
               ) as screenshot_id,
               COALESCE(
                   (SELECT s.timestamp FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND s.timestamp <= bh.last_visit
                    ORDER BY s.timestamp DESC LIMIT 1),
                   (SELECT s.timestamp FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND s.timestamp >= bh.last_visit
                    ORDER BY s.timestamp ASC LIMIT 1)
               ) as screenshot_time
            FROM browser_history bh
            ORDER BY bh.last_visit DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows]


# ============================================
# 统计
# ============================================

def _count(db, table: str, agent_name: str = None, extra_where: str = "", extra_params: list = None) -> int:
    """通用计数辅助函数"""
    conditions = []
    params = []
    if agent_name:
        conditions.append("agent_name = ?")
        params.append(agent_name)
    if extra_where:
        conditions.append(extra_where)
        if extra_params:
            params.extend(extra_params)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return db.execute(f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()[0]


def get_dashboard_stats(agent_name: str = None) -> dict:
    """获取仪表盘统计数据"""
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "total_screenshots": _count(db, "screenshots", agent_name),
        "today_app_events": _count(db, "app_events", agent_name, "date(timestamp) = ?", [today]),
        "total_browser_records": _count(db, "browser_history", agent_name),
        "online_agents": db.execute("SELECT COUNT(*) FROM agents WHERE status = 'online'").fetchone()[0],
    }


# ============================================
# 存储管理
# ============================================

def get_storage_stats() -> dict:
    """获取存储使用统计 — 总量、Agent 明细、最早截图时间"""
    db = get_db()
    total_size = db.execute(
        "SELECT COALESCE(SUM(file_size), 0) FROM screenshots"
    ).fetchone()[0]
    total_count = db.execute(
        "SELECT COUNT(*) FROM screenshots"
    ).fetchone()[0]
    earliest = db.execute(
        "SELECT timestamp FROM screenshots ORDER BY timestamp ASC LIMIT 1"
    ).fetchone()

    # 按 Agent 分组统计
    agent_rows = db.execute(
        """SELECT agent_name,
                  COUNT(*) as count,
                  COALESCE(SUM(file_size), 0) as total_size,
                  MIN(timestamp) as oldest,
                  MAX(timestamp) as newest
           FROM screenshots
           GROUP BY agent_name
           ORDER BY total_size DESC"""
    ).fetchall()

    return {
        "total_size_bytes": total_size,
        "total_count": total_count,
        "earliest_screenshot": earliest["timestamp"] if earliest else None,
        "agents": [dict(r) for r in agent_rows],
    }


def cleanup_old_screenshots(older_than_hours: int, agent_name: str = None) -> dict:
    """删除超过指定小时数的截图（文件 + DB 索引）

    older_than_hours: 删除 timestamp 早于该小时数的截图
    agent_name: 可选，限制清理范围到指定 Agent

    返回: {"deleted_count": N, "freed_bytes": N}
    """
    from datetime import datetime, timedelta

    db = get_db()
    cutoff = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()

    # 先查出要删的文件路径和大小（用于统计和文件删除）
    conditions = ["timestamp < ?"]
    params = [cutoff]
    if agent_name:
        conditions.append("agent_name = ?")
        params.append(agent_name)

    where = " AND ".join(conditions)
    rows = db.execute(
        f"SELECT id, file_path, file_size FROM screenshots WHERE {where}",
        params
    ).fetchall()

    deleted_count = 0
    freed_bytes = 0
    for row in rows:
        try:
            if os.path.exists(row["file_path"]):
                os.remove(row["file_path"])
        except OSError:
            pass
        db.execute("DELETE FROM screenshots WHERE id = ?", (row["id"],))
        deleted_count += 1
        freed_bytes += row["file_size"] or 0

    db.commit()

    if deleted_count:
        print(f"[DB] 清理完成: {deleted_count} 张截图, 释放 {freed_bytes / 1024 / 1024:.1f} MB")

    return {
        "deleted_count": deleted_count,
        "freed_bytes": freed_bytes,
        "cutoff_time": cutoff,
        "older_than_hours": older_than_hours,
    }


# ============================================
# 诊断日志
# ============================================

_CATEGORIES = ["network", "storage", "capture", "system", "security", "server"]
_LEVELS = ["INFO", "WARNING", "ERROR"]


def save_diagnostic(agent_name: str, category: str, level: str, message: str) -> int | None:
    """保存诊断日志 — Agent 上报或 Server 内部记录

    category: network|storage|capture|system|security|server
    level: INFO|WARNING|ERROR
    """
    if category not in _CATEGORIES:
        category = "system"
    if level not in _LEVELS:
        level = "INFO"

    db = get_db()
    cursor = db.execute(
        """INSERT INTO diagnostic_logs (agent_name, category, level, message)
           VALUES (?, ?, ?, ?)""",
        (agent_name, category, level, message)
    )
    db.commit()
    return cursor.lastrowid


def query_diagnostics(
    category: str = None,
    level: str = None,
    agent_name: str = None,
    pattern: str = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """查询诊断日志 — 支持分类/级别/Agent/正则筛选"""
    db = get_db()
    conditions = []
    params = []

    if agent_name:
        conditions.append("agent_name = ?")
        params.append(agent_name)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if level:
        conditions.append("level = ?")
        params.append(level)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"""SELECT * FROM diagnostic_logs {where}
              ORDER BY timestamp DESC LIMIT ? OFFSET ?"""
    params.extend([limit, offset])

    rows = db.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]

    # 正则筛选（SQLite 不支持，Python 侧过滤，小数据集足够）
    if pattern:
        import re
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            results = [r for r in results if regex.search(r["message"])]
        except re.error:
            return [{"error": f"无效正则: {pattern}"}]

    return results


def get_diagnostic_categories() -> list[dict]:
    """返回各类别的计数（用于前端筛选芯片）"""
    db = get_db()
    rows = db.execute(
        """SELECT category, level, COUNT(*) as count
           FROM diagnostic_logs
           GROUP BY category, level
           ORDER BY category, level"""
    ).fetchall()
    return [dict(r) for r in rows]
