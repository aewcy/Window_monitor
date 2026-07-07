"""
数据模型和数据库操作
使用 SQLite 存储结构化数据，文件系统存储截图
"""
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote

from config import DB_PATH, SCREENSHOT_DIR


# 线程本地存储，每个线程使用自己的连接
_local = threading.local()
AGENT_ONLINE_TIMEOUT_SECONDS = 60
SCREENSHOT_THUMB_WIDTH = 220
SCREENSHOT_THUMB_QUALITY = 38
SCREENSHOT_PREVIEW_WIDTH = 1280
SCREENSHOT_PREVIEW_QUALITY = 65
UPDATE_ACTIVE_STATUSES = (
    "claimed",
    "downloading",
    "downloaded",
    "installing",
    "restarting",
    "waiting_login",
    "verifying",
)
UPDATE_TERMINAL_STATUSES = (
    "verified",
    "failed",
    "rolled_back_verified",
    "rolled_back_unverified",
    "stale",
    "canceled",
)
UPDATE_STALE_SECONDS = {
    "claimed": 120,
    "downloading": 20 * 60,
    "downloaded": 5 * 60,
    "installing": 180,
    "restarting": 120,
    "verifying": 180,
}


def _parse_db_datetime(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _is_agent_online(row: dict, now: datetime | None = None) -> bool:
    if row.get("status") != "online":
        return False
    last_seen = _parse_db_datetime(row.get("last_seen", ""))
    if not last_seen:
        return False
    now = now or datetime.now()
    return now - last_seen <= timedelta(seconds=AGENT_ONLINE_TIMEOUT_SECONDS)


def _derived_screenshot_path(file_path: str, variant: str) -> str:
    base_dir = os.path.dirname(file_path)
    stem, _ext = os.path.splitext(os.path.basename(file_path))
    if variant == "thumb":
        return os.path.join(base_dir, "_derived", f"{stem}_thumb_w{SCREENSHOT_THUMB_WIDTH}_q{SCREENSHOT_THUMB_QUALITY}.jpg")
    return os.path.join(base_dir, "_derived", f"{stem}_{variant}.jpg")


def _media_url_for_path(file_path: str) -> str | None:
    try:
        rel_path = os.path.relpath(file_path, SCREENSHOT_DIR)
    except ValueError:
        return None
    if rel_path.startswith("..") or os.path.isabs(rel_path):
        return None
    parts = rel_path.replace("\\", "/").split("/")
    return "/media/screenshots/" + "/".join(quote(part) for part in parts)


def screenshot_thumb_url(screenshot_id: int, file_path: str) -> str:
    thumb_path = _derived_screenshot_path(file_path, "thumb")
    if os.path.exists(thumb_path):
        return _media_url_for_path(thumb_path) or f"/api/screenshots/thumb/{screenshot_id}"
    return f"/api/screenshots/thumb/{screenshot_id}"


def enrich_screenshot_urls(row: dict) -> dict:
    row["thumb_url"] = screenshot_thumb_url(row["id"], row["file_path"])
    row["image_url"] = f"/api/screenshots/image/{row['id']}"
    return row


def _remove_screenshot_files(file_path: str) -> int:
    """删除原图及派生图，返回实际释放字节数"""
    freed_bytes = 0
    paths = [file_path, _derived_screenshot_path(file_path, "thumb"), _derived_screenshot_path(file_path, "preview")]
    derived_dir = os.path.join(os.path.dirname(file_path), "_derived")
    stem, _ext = os.path.splitext(os.path.basename(file_path))
    if os.path.isdir(derived_dir):
        for name in os.listdir(derived_dir):
            if name.startswith(f"{stem}_thumb") or name.startswith(f"{stem}_preview"):
                paths.append(os.path.join(derived_dir, name))
    for path in set(paths):
        try:
            if os.path.exists(path):
                freed_bytes += os.path.getsize(path)
                os.remove(path)
        except OSError:
            pass
    return freed_bytes


def ensure_screenshot_variant(file_path: str, variant: str) -> str:
    """确保缩略图/预览图存在；生成失败时回退原图"""
    if variant not in ("thumb", "preview"):
        return file_path
    if not os.path.exists(file_path):
        return file_path

    derived_path = _derived_screenshot_path(file_path, variant)
    if os.path.exists(derived_path):
        return derived_path

    width = SCREENSHOT_THUMB_WIDTH if variant == "thumb" else SCREENSHOT_PREVIEW_WIDTH
    quality = SCREENSHOT_THUMB_QUALITY if variant == "thumb" else SCREENSHOT_PREVIEW_QUALITY
    try:
        from PIL import Image

        os.makedirs(os.path.dirname(derived_path), exist_ok=True)
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            if img.width > width:
                ratio = width / img.width
                height = max(1, int(img.height * ratio))
                img = img.resize((width, height), Image.Resampling.LANCZOS)
            img.save(derived_path, "JPEG", quality=quality, optimize=True, progressive=True)
        return derived_path
    except Exception as e:
        print(f"[DB] 生成截图{variant}失败: {e}")
        return file_path


def generate_screenshot_variants(file_path: str) -> None:
    """生成网格缩略图；失败不影响原图入库"""
    ensure_screenshot_variant(file_path, "thumb")


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

        CREATE TABLE IF NOT EXISTS screenshot_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type TEXT NOT NULL,
            pattern TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_screenshot_rules_enabled
            ON screenshot_rules(enabled, rule_type, id DESC);

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

        -- Web 下发给 Agent 的控制命令
        CREATE TABLE IF NOT EXISTS agent_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            command TEXT NOT NULL,
            payload TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            result TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            claimed_at TEXT DEFAULT '',
            finished_at TEXT DEFAULT '',
            FOREIGN KEY (agent_name) REFERENCES agents(name)
        );
        CREATE INDEX IF NOT EXISTS idx_agent_commands_agent_status
            ON agent_commands(agent_name, status, id);

        -- Agent 版本表
        CREATE TABLE IF NOT EXISTS agent_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT UNIQUE NOT NULL,
            channel TEXT DEFAULT 'stable',
            exe_path TEXT DEFAULT '',
            setup_path TEXT DEFAULT '',
            exe_sha256 TEXT DEFAULT '',
            setup_sha256 TEXT DEFAULT '',
            exe_size_bytes INTEGER DEFAULT 0,
            setup_size_bytes INTEGER DEFAULT 0,
            updater_version TEXT DEFAULT '',
            release_notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            is_active INTEGER DEFAULT 1
        );

        -- Agent 更新任务表
        CREATE TABLE IF NOT EXISTS agent_update_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            install_id TEXT DEFAULT '',
            machine_id TEXT DEFAULT '',
            agent_name TEXT NOT NULL,
            from_version TEXT DEFAULT '',
            target_version TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            progress_bytes INTEGER DEFAULT 0,
            total_bytes INTEGER DEFAULT 0,
            attempt_count INTEGER DEFAULT 0,
            last_error TEXT DEFAULT '',
            last_log TEXT DEFAULT '',
            claimed_at TEXT DEFAULT '',
            verifying_started_at TEXT DEFAULT '',
            rollback_started_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            finished_at TEXT DEFAULT '',
            FOREIGN KEY (agent_name) REFERENCES agents(name)
        );
        CREATE INDEX IF NOT EXISTS idx_update_jobs_agent_status
            ON agent_update_jobs(agent_name, status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_update_jobs_machine_status
            ON agent_update_jobs(machine_id, install_id, status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_update_jobs_status
            ON agent_update_jobs(status, updated_at);

        -- Agent 更新事件表
        CREATE TABLE IF NOT EXISTS agent_update_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            agent_name TEXT DEFAULT '',
            level TEXT DEFAULT 'INFO',
            stage TEXT DEFAULT '',
            message TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_update_events_job
            ON agent_update_events(job_id, id DESC);

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
    try:
        db.execute("ALTER TABLE screenshots ADD COLUMN foreground_process_name TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE screenshots ADD COLUMN foreground_window_title TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE screenshots ADD COLUMN foreground_url TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE screenshots ADD COLUMN matched_rule_type TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE screenshots ADD COLUMN matched_rule_pattern TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE screenshots ADD COLUMN save_policy_phase TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass

    # 向前兼容迁移: 为 agents 表添加 display_name 列（Web 端自定义显示名）
    try:
        db.execute("ALTER TABLE agents ADD COLUMN display_name TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 向前兼容迁移: 清理 agents 表重复记录 + 确保 UNIQUE 约束
    # 旧数据库可能在添加 UNIQUE 约束前创建，导致 ON CONFLICT 失效
    try:
        dupes = db.execute(
            "SELECT name, COUNT(*) as cnt FROM agents GROUP BY name HAVING cnt > 1"
        ).fetchall()
        if dupes:
            print(f"[DB] 发现 {len(dupes)} 个重复 Agent 名称，正在清理...")
            for row in dupes:
                agent_name = row["name"]
                # 保留 id 最小的（最早的记录），删除其余
                keep = db.execute(
                    "SELECT MIN(id) FROM agents WHERE name = ?", (agent_name,)
                ).fetchone()[0]
                deleted = db.execute(
                    "DELETE FROM agents WHERE name = ? AND id != ?",
                    (agent_name, keep)
                ).rowcount
                print(f"  [DB] Agent '{agent_name}': 保留 id={keep}, 删除 {deleted} 条重复")
            db.commit()
        # 尝试创建唯一索引（如果不存在）
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_name ON agents(name)")
        db.commit()
    except sqlite3.OperationalError as e:
        print(f"[DB] Agent 去重迁移异常: {e}")

    # 向前兼容迁移: 为 agents 表添加 ip 列
    try:
        db.execute("ALTER TABLE agents ADD COLUMN ip TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 向前兼容迁移: 为 agents 表添加 machine_id 列（硬件唯一标识，防重复注册）
    try:
        db.execute("ALTER TABLE agents ADD COLUMN machine_id TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在

    # 向前兼容迁移: Agent 后台更新状态
    for column, ddl in [
        ("agent_version", "ALTER TABLE agents ADD COLUMN agent_version TEXT DEFAULT ''"),
        ("control_status", "ALTER TABLE agents ADD COLUMN control_status TEXT DEFAULT 'running'"),
        ("control_updated_at", "ALTER TABLE agents ADD COLUMN control_updated_at TEXT DEFAULT ''"),
        ("update_status", "ALTER TABLE agents ADD COLUMN update_status TEXT DEFAULT 'idle'"),
        ("update_target_version", "ALTER TABLE agents ADD COLUMN update_target_version TEXT DEFAULT ''"),
        ("update_error", "ALTER TABLE agents ADD COLUMN update_error TEXT DEFAULT ''"),
        ("update_checked_at", "ALTER TABLE agents ADD COLUMN update_checked_at TEXT DEFAULT ''"),
        ("update_allowed_version", "ALTER TABLE agents ADD COLUMN update_allowed_version TEXT DEFAULT ''"),
        ("update_allowed_at", "ALTER TABLE agents ADD COLUMN update_allowed_at TEXT DEFAULT ''"),
        ("install_id", "ALTER TABLE agents ADD COLUMN install_id TEXT DEFAULT ''"),
        ("updater_version", "ALTER TABLE agents ADD COLUMN updater_version TEXT DEFAULT ''"),
        ("update_job_id", "ALTER TABLE agents ADD COLUMN update_job_id TEXT DEFAULT ''"),
    ]:
        try:
            db.execute(ddl)
            db.commit()
        except sqlite3.OperationalError:
            pass  # 列已存在


# ============================================
# Agent 管理
# ============================================

def upsert_agent(name: str, status: str = "online", message: str = "", ip: str = "",
                 machine_id: str = "", agent_version: str = "", update_status: str = "",
                 update_target_version: str = "", update_error: str = "", control_status: str = "",
                 install_id: str = "", updater_version: str = "", update_job_id: str = ""):
    name = name.strip()
    if not name:
        return
    db = get_db()
    try:
        db.execute(
            """INSERT INTO agents (
                    name, status, last_seen, message, ip, machine_id,
                    agent_version, control_status, control_updated_at,
                    update_status, update_target_version, update_error, update_checked_at,
                    install_id, updater_version, update_job_id
                  )
               VALUES (?, ?, datetime('now', 'localtime'), ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, ?, ?, datetime('now', 'localtime'), ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 status=excluded.status,
                 last_seen=excluded.last_seen,
                 message=excluded.message,
                 ip=CASE WHEN excluded.ip != '' THEN excluded.ip ELSE agents.ip END,
                 machine_id=CASE WHEN excluded.machine_id != '' THEN excluded.machine_id ELSE agents.machine_id END,
                 install_id=CASE WHEN excluded.install_id != '' THEN excluded.install_id ELSE agents.install_id END,
                 updater_version=CASE WHEN excluded.updater_version != '' THEN excluded.updater_version ELSE agents.updater_version END,
                 update_job_id=CASE WHEN excluded.update_job_id != '' THEN excluded.update_job_id ELSE agents.update_job_id END,
                 agent_version=CASE WHEN excluded.agent_version != '' THEN excluded.agent_version ELSE agents.agent_version END,
                 control_status=CASE WHEN excluded.control_status != '' THEN excluded.control_status ELSE agents.control_status END,
                 control_updated_at=CASE WHEN excluded.control_status != '' THEN excluded.control_updated_at ELSE agents.control_updated_at END,
                 update_status=CASE WHEN excluded.update_status != '' THEN excluded.update_status ELSE agents.update_status END,
                 update_target_version=CASE WHEN excluded.update_target_version != '' THEN excluded.update_target_version ELSE agents.update_target_version END,
                 update_error=CASE
                   WHEN excluded.update_status IN ('idle', 'updated') THEN ''
                   WHEN excluded.update_error != '' THEN excluded.update_error
                   ELSE agents.update_error
                 END,
                 update_checked_at=CASE WHEN excluded.agent_version != '' OR excluded.update_status != '' THEN excluded.update_checked_at ELSE agents.update_checked_at END,
                 update_allowed_version=CASE
                   WHEN excluded.agent_version != '' AND excluded.agent_version = agents.update_allowed_version THEN ''
                   WHEN excluded.update_status IN ('updated', 'rolled_back') THEN ''
                   ELSE agents.update_allowed_version
                 END""",
            (name, status, message, ip, machine_id, agent_version, control_status, update_status, update_target_version, update_error, install_id, updater_version, update_job_id)
        )
    except sqlite3.IntegrityError:
        # 并发 INSERT 竞态兜底：另一个线程先 INSERT 成功，改为 UPDATE
        db.execute(
            """UPDATE agents SET
                 status=?,
                 last_seen=datetime('now','localtime'),
                 message=?,
                 ip=CASE WHEN ? != '' THEN ? ELSE ip END,
                 machine_id=CASE WHEN ? != '' THEN ? ELSE machine_id END,
                 install_id=CASE WHEN ? != '' THEN ? ELSE install_id END,
                 updater_version=CASE WHEN ? != '' THEN ? ELSE updater_version END,
                 update_job_id=CASE WHEN ? != '' THEN ? ELSE update_job_id END,
                 agent_version=CASE WHEN ? != '' THEN ? ELSE agent_version END,
                 control_status=CASE WHEN ? != '' THEN ? ELSE control_status END,
                 control_updated_at=CASE WHEN ? != '' THEN datetime('now','localtime') ELSE control_updated_at END,
                 update_status=CASE WHEN ? != '' THEN ? ELSE update_status END,
                 update_target_version=CASE WHEN ? != '' THEN ? ELSE update_target_version END,
                 update_error=CASE
                   WHEN ? IN ('idle', 'updated') THEN ''
                   WHEN ? != '' THEN ?
                   ELSE update_error
                 END,
                 update_checked_at=CASE WHEN ? != '' OR ? != '' THEN datetime('now','localtime') ELSE update_checked_at END,
                 update_allowed_version=CASE
                   WHEN ? != '' AND ? = update_allowed_version THEN ''
                   WHEN ? IN ('updated', 'rolled_back') THEN ''
                   ELSE update_allowed_version
                 END
               WHERE name=?""",
            (
                status, message, ip, ip, machine_id, machine_id, install_id, install_id,
                updater_version, updater_version, update_job_id, update_job_id,
                agent_version, agent_version, control_status, control_status, control_status,
                update_status, update_status,
                update_target_version, update_target_version, update_status, update_error, update_error,
                agent_version, update_status, agent_version, agent_version, update_status, name,
            )
        )
    if machine_id:
        _merge_duplicate_agents_by_machine_id(db, machine_id)
    _verify_update_job_from_agent(db, name, machine_id, install_id, agent_version, update_job_id)
    db.commit()


def _dict_or_none(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def _add_update_event(db: sqlite3.Connection, job_id: str, agent_name: str, level: str, stage: str, message: str):
    db.execute(
        """INSERT INTO agent_update_events (job_id, agent_name, level, stage, message)
           VALUES (?, ?, ?, ?, ?)""",
        (job_id, agent_name or "", level or "INFO", stage or "", message or ""),
    )


def _row_is_active_update(row: sqlite3.Row | dict | None) -> bool:
    return bool(row and row["status"] in UPDATE_ACTIVE_STATUSES)


def _active_status_placeholders() -> str:
    return ",".join("?" for _ in UPDATE_ACTIVE_STATUSES)


def register_agent_version(version: str, exe_path: str = "", setup_path: str = "", exe_sha256: str = "",
                           setup_sha256: str = "", exe_size_bytes: int = 0, setup_size_bytes: int = 0,
                           updater_version: str = "", release_notes: str = "", channel: str = "stable",
                           is_active: bool = False) -> dict:
    """登记一个可下载 Agent 版本，保持版本元数据可查询。"""
    db = get_db()
    if is_active:
        db.execute("UPDATE agent_versions SET is_active = 0")
    db.execute(
        """INSERT INTO agent_versions (
             version, channel, exe_path, setup_path, exe_sha256, setup_sha256,
             exe_size_bytes, setup_size_bytes, updater_version, release_notes, is_active
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(version) DO UPDATE SET
             channel=excluded.channel,
             exe_path=excluded.exe_path,
             setup_path=excluded.setup_path,
             exe_sha256=excluded.exe_sha256,
             setup_sha256=excluded.setup_sha256,
             exe_size_bytes=excluded.exe_size_bytes,
             setup_size_bytes=excluded.setup_size_bytes,
             updater_version=excluded.updater_version,
             release_notes=excluded.release_notes,
             is_active=CASE WHEN excluded.is_active = 1 THEN 1 ELSE agent_versions.is_active END""",
        (
            version, channel, exe_path, setup_path, exe_sha256, setup_sha256,
            exe_size_bytes, setup_size_bytes, updater_version, release_notes,
            1 if is_active else 0,
        ),
    )
    db.commit()
    return get_agent_version(version) or {}


def get_agent_version(version: str) -> dict | None:
    row = get_db().execute("SELECT * FROM agent_versions WHERE version = ?", (version,)).fetchone()
    return _dict_or_none(row)


def list_agent_versions() -> list[dict]:
    rows = get_db().execute("SELECT * FROM agent_versions ORDER BY is_active DESC, created_at DESC, id DESC").fetchall()
    return [dict(row) for row in rows]


def get_active_agent_version() -> dict | None:
    db = get_db()
    row = db.execute(
        """SELECT * FROM agent_versions
           WHERE is_active = 1
           ORDER BY created_at DESC, id DESC
           LIMIT 1"""
    ).fetchone()
    if row:
        return dict(row)
    row = db.execute(
        """SELECT * FROM agent_versions
           ORDER BY created_at DESC, id DESC
           LIMIT 1"""
    ).fetchone()
    return dict(row) if row else None


def set_active_agent_version(version: str) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM agent_versions WHERE version = ?", (version,)).fetchone()
    if not row:
        return None
    db.execute("UPDATE agent_versions SET is_active = 0")
    db.execute("UPDATE agent_versions SET is_active = 1 WHERE version = ?", (version,))
    db.commit()
    return get_agent_version(version)


def create_agent_update_job(agent_name: str, target_version: str, from_version: str = "") -> dict | None:
    """创建单机更新任务；同一时间只允许一个 active job。"""
    db = get_db()
    placeholders = _active_status_placeholders()
    try:
        db.execute("BEGIN IMMEDIATE")
        agent = db.execute("SELECT * FROM agents WHERE name = ?", (agent_name,)).fetchone()
        if not agent:
            db.rollback()
            return None

        existing = db.execute(
            f"""SELECT * FROM agent_update_jobs
                WHERE agent_name = ?
                  AND status IN ('pending', {placeholders})
                ORDER BY id DESC LIMIT 1""",
            (agent_name, *UPDATE_ACTIVE_STATUSES),
        ).fetchone()
        if existing:
            db.commit()
            return dict(existing)

        active = db.execute(
            f"""SELECT * FROM agent_update_jobs
                WHERE status IN ({placeholders})
                ORDER BY updated_at DESC LIMIT 1""",
            UPDATE_ACTIVE_STATUSES,
        ).fetchone()
        agent_status = dict(agent).get("status") or ""
        # 离线机器只创建 pending，不占用 active；在线机器如果已有 active job 则拒绝。
        if active and agent_status == "online":
            db.rollback()
            raise RuntimeError(f"已有机器正在更新: {active['agent_name']} {active['status']}")

        job_id = uuid.uuid4().hex
        effective_from = from_version or (agent["agent_version"] or "")
        db.execute(
            """INSERT INTO agent_update_jobs (
                 job_id, install_id, machine_id, agent_name, from_version, target_version,
                 status, total_bytes, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, datetime('now', 'localtime'))""",
            (job_id, agent["install_id"] if "install_id" in agent.keys() else "", agent["machine_id"] or "", agent_name, effective_from, target_version),
        )
        _add_update_event(db, job_id, agent_name, "INFO", "pending", f"创建更新任务到 v{target_version}")
        db.commit()
        return get_update_job(job_id)
    except Exception:
        try:
            db.rollback()
        except sqlite3.Error:
            pass
        raise


def get_update_job(job_id: str) -> dict | None:
    row = get_db().execute("SELECT * FROM agent_update_jobs WHERE job_id = ?", (job_id,)).fetchone()
    return _dict_or_none(row)


def get_latest_update_job(agent_name: str) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM agent_update_jobs WHERE agent_name = ? ORDER BY id DESC LIMIT 1",
        (agent_name,),
    ).fetchone()
    return _dict_or_none(row)


def list_update_events(job_id: str, limit: int = 10) -> list[dict]:
    rows = get_db().execute(
        """SELECT * FROM agent_update_events
           WHERE job_id = ?
           ORDER BY id DESC LIMIT ?""",
        (job_id, max(1, min(int(limit or 10), 100))),
    ).fetchall()
    return [dict(row) for row in rows]


def claim_next_update_job(install_id: str = "", machine_id: str = "", updater_version: str = "") -> dict | None:
    """Updater 领取属于本机的下一个任务。"""
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        conditions = ["status = 'pending'"]
        params: list[str] = []
        if install_id:
            conditions.append("(install_id = ? OR install_id = '')")
            params.append(install_id)
        if machine_id:
            conditions.append("machine_id = ?")
            params.append(machine_id)
        if not install_id and not machine_id:
            db.rollback()
            return None
        row = db.execute(
            f"""SELECT * FROM agent_update_jobs
                WHERE {' AND '.join(conditions)}
                ORDER BY id ASC LIMIT 1""",
            params,
        ).fetchone()
        if not row:
            db.commit()
            return None

        db.execute(
            """UPDATE agent_update_jobs
               SET status='claimed',
                   install_id=CASE WHEN install_id = '' THEN ? ELSE install_id END,
                   claimed_at=datetime('now', 'localtime'),
                   updated_at=datetime('now', 'localtime'),
                   last_log=?
               WHERE job_id = ? AND status='pending'""",
            (install_id or row["install_id"] or "", f"Updater {updater_version or 'unknown'} 已领取任务", row["job_id"]),
        )
        _add_update_event(db, row["job_id"], row["agent_name"], "INFO", "claimed", f"Updater {updater_version or 'unknown'} 已领取任务")
        db.commit()
        return get_update_job(row["job_id"])
    except Exception:
        try:
            db.rollback()
        except sqlite3.Error:
            pass
        raise


def update_job_heartbeat(job_id: str, status: str = "", progress_bytes: int | None = None,
                         total_bytes: int | None = None, message: str = "", error: str = "") -> dict | None:
    db = get_db()
    job = get_update_job(job_id)
    if not job:
        return None
    next_status = status or job["status"]
    progress = job["progress_bytes"] if progress_bytes is None else max(0, int(progress_bytes))
    total = job["total_bytes"] if total_bytes is None else max(0, int(total_bytes))
    verifying_started_at = job.get("verifying_started_at") or ""
    rollback_started_at = job.get("rollback_started_at") or ""
    finished_at = job.get("finished_at") or ""
    if next_status == "verifying" and not verifying_started_at:
        verifying_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if next_status in ("rolled_back_verified", "rolled_back_unverified") and not rollback_started_at:
        rollback_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if next_status in UPDATE_TERMINAL_STATUSES and not finished_at:
        finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        """UPDATE agent_update_jobs
           SET status=?,
               progress_bytes=?,
               total_bytes=?,
               last_error=CASE WHEN ? != '' THEN ? ELSE last_error END,
               last_log=CASE WHEN ? != '' THEN ? ELSE last_log END,
               verifying_started_at=?,
               rollback_started_at=?,
               finished_at=?,
               updated_at=datetime('now', 'localtime')
           WHERE job_id=?""",
        (next_status, progress, total, error or "", error or "", message or "", message or "", verifying_started_at, rollback_started_at, finished_at, job_id),
    )
    if message or error or status:
        _add_update_event(db, job_id, job["agent_name"], "ERROR" if error else "INFO", next_status, error or message or f"status={next_status}")
    db.commit()
    return get_update_job(job_id)


def finish_update_job(job_id: str, status: str, message: str = "", error: str = "") -> dict | None:
    if status == "rolled_back":
        status = "rolled_back_unverified"
    return update_job_heartbeat(job_id, status=status, message=message, error=error)


def cancel_update_job(job_id: str) -> dict | None:
    job = get_update_job(job_id)
    if not job or job["status"] not in ("pending", "claimed", "downloaded"):
        return None
    return finish_update_job(job_id, "canceled", "更新任务已取消")


def retry_update_job(job_id: str) -> dict | None:
    job = get_update_job(job_id)
    if not job or job["status"] not in UPDATE_TERMINAL_STATUSES:
        return None
    return create_agent_update_job(job["agent_name"], job["target_version"], job["from_version"])


def reap_stale_update_jobs() -> int:
    """把长时间未推进的更新任务标记为 stale，避免 Web 无限显示安装中。"""
    db = get_db()
    changed = 0
    now = datetime.now()
    rows = db.execute(
        f"""SELECT * FROM agent_update_jobs
            WHERE status IN ({_active_status_placeholders()})""",
        UPDATE_ACTIVE_STATUSES,
    ).fetchall()
    for row in rows:
        status = row["status"]
        if status == "waiting_login":
            continue
        timeout = UPDATE_STALE_SECONDS.get(status)
        updated_at = _parse_db_datetime(row["updated_at"] or "")
        if not timeout or not updated_at or now - updated_at <= timedelta(seconds=timeout):
            continue
        db.execute(
            """UPDATE agent_update_jobs
               SET status='stale',
                   last_error=?,
                   finished_at=datetime('now', 'localtime'),
                   updated_at=datetime('now', 'localtime')
               WHERE job_id=?""",
            (f"{status} 阶段超过 {timeout} 秒未推进", row["job_id"]),
        )
        _add_update_event(db, row["job_id"], row["agent_name"], "ERROR", "stale", f"{status} 阶段超时")
        changed += 1
    if changed:
        db.commit()
    return changed


def _verify_update_job_from_agent(db: sqlite3.Connection, agent_name: str, machine_id: str, install_id: str,
                                  agent_version: str, update_job_id: str = ""):
    if not agent_version:
        return
    params: list[str] = []
    conditions = [
        "agent_name = ?",
        "status IN ('verifying', 'restarting', 'waiting_login')",
    ]
    params.append(agent_name)
    if machine_id:
        conditions.append("machine_id = ?")
        params.append(machine_id)
    if install_id:
        conditions.append("(install_id = ? OR install_id = '')")
        params.append(install_id)
    if update_job_id:
        conditions.append("job_id = ?")
        params.append(update_job_id)
    row = db.execute(
        f"""SELECT * FROM agent_update_jobs
            WHERE {' AND '.join(conditions)}
            ORDER BY id DESC LIMIT 1""",
        params,
    ).fetchone()
    if not row or row["target_version"] != agent_version:
        return
    verify_start = _parse_db_datetime(row["verifying_started_at"] or row["updated_at"] or "")
    if verify_start and datetime.now() + timedelta(seconds=2) < verify_start:
        return
    db.execute(
        """UPDATE agent_update_jobs
           SET status='verified',
               install_id=CASE WHEN install_id = '' THEN ? ELSE install_id END,
               last_log='目标版本心跳验证成功',
               finished_at=datetime('now', 'localtime'),
               updated_at=datetime('now', 'localtime')
           WHERE job_id=?""",
        (install_id or "", row["job_id"]),
    )
    _add_update_event(db, row["job_id"], agent_name, "INFO", "verified", "目标版本心跳验证成功")


def set_agent_update_permission(name: str, target_version: str = "") -> bool:
    """允许单台 Agent 更新到指定版本。"""
    db = get_db()
    cursor = db.execute(
        """UPDATE agents
           SET update_allowed_version = ?,
               update_allowed_at = datetime('now', 'localtime'),
               update_target_version = ?,
               update_status = CASE WHEN update_status = '' THEN 'idle' ELSE update_status END,
               update_error = ''
           WHERE name = ?""",
        (target_version, target_version, name),
    )
    db.commit()
    return cursor.rowcount > 0


def clear_agent_update_permission(name: str) -> bool:
    """暂停/清除单台 Agent 的更新许可。"""
    db = get_db()
    cursor = db.execute(
        """UPDATE agents
           SET update_allowed_version = '',
               update_allowed_at = '',
               update_target_version = '',
               update_status = CASE WHEN update_status IN ('downloading', 'installing') THEN 'idle' ELSE update_status END
           WHERE name = ?""",
        (name,),
    )
    db.commit()
    return cursor.rowcount > 0


def create_agent_command(agent_name: str, command: str, payload: str = "{}") -> dict | None:
    """Web 创建一条待 Agent 拉取的控制命令。"""
    db = get_db()
    agent = db.execute("SELECT name FROM agents WHERE name = ?", (agent_name,)).fetchone()
    if not agent:
        return None
    cursor = db.execute(
        """INSERT INTO agent_commands (agent_name, command, payload, status)
           VALUES (?, ?, ?, 'pending')""",
        (agent_name, command, payload or "{}"),
    )
    db.commit()
    return get_agent_command(cursor.lastrowid)


def get_agent_command(command_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM agent_commands WHERE id = ?", (command_id,)).fetchone()
    return dict(row) if row else None


def claim_next_agent_command(agent_name: str) -> dict | None:
    """Agent 拉取并占用一条待执行命令。"""
    db = get_db()
    row = db.execute(
        """SELECT * FROM agent_commands
           WHERE agent_name = ? AND status = 'pending'
           ORDER BY id ASC LIMIT 1""",
        (agent_name,),
    ).fetchone()
    if not row:
        return None
    db.execute(
        """UPDATE agent_commands
           SET status = 'claimed', claimed_at = datetime('now', 'localtime')
           WHERE id = ? AND status = 'pending'""",
        (row["id"],),
    )
    db.commit()
    return get_agent_command(row["id"])


def finish_agent_command(command_id: int, status: str, result: str = "") -> bool:
    """Agent 回报命令执行结果。"""
    if status not in ("done", "failed"):
        status = "failed"
    db = get_db()
    cursor = db.execute(
        """UPDATE agent_commands
           SET status = ?, result = ?, finished_at = datetime('now', 'localtime')
           WHERE id = ?""",
        (status, result or "", command_id),
    )
    db.commit()
    return cursor.rowcount > 0


def _merge_duplicate_agents_by_machine_id(db: sqlite3.Connection, machine_id: str):
    rows = db.execute(
        """SELECT name FROM agents
           WHERE machine_id = ?
           ORDER BY last_seen DESC, id DESC""",
        (machine_id,),
    ).fetchall()
    if len(rows) <= 1:
        return
    keep = rows[0]["name"]
    duplicates = [row["name"] for row in rows[1:]]
    for duplicate in duplicates:
        db.execute("UPDATE screenshots SET agent_name = ? WHERE agent_name = ?", (keep, duplicate))
        db.execute("UPDATE app_events SET agent_name = ? WHERE agent_name = ?", (keep, duplicate))
        db.execute(
            """DELETE FROM browser_history
               WHERE agent_name = ?
                 AND EXISTS (
                   SELECT 1 FROM browser_history kept
                   WHERE kept.agent_name = ?
                     AND kept.url = browser_history.url
                     AND kept.last_visit = browser_history.last_visit
                 )""",
            (duplicate, keep),
        )
        db.execute("UPDATE browser_history SET agent_name = ? WHERE agent_name = ?", (keep, duplicate))
        db.execute("UPDATE diagnostic_logs SET agent_name = ? WHERE agent_name = ?", (keep, duplicate))
        db.execute("UPDATE agent_commands SET agent_name = ? WHERE agent_name = ?", (keep, duplicate))
        db.execute("DELETE FROM agents WHERE name = ?", (duplicate,))


def get_agents() -> list[dict]:
    db = get_db()
    reap_stale_update_jobs()
    rows = db.execute(
        "SELECT * FROM agents ORDER BY last_seen DESC"
    ).fetchall()
    now = datetime.now()
    agents = []
    for row in rows:
        item = dict(row)
        if item.get("status") == "online" and not _is_agent_online(item, now):
            item["status"] = "offline"
            item["message"] = item.get("message") or "heartbeat timeout"
        job = db.execute(
            "SELECT * FROM agent_update_jobs WHERE agent_name = ? ORDER BY id DESC LIMIT 1",
            (item["name"],),
        ).fetchone()
        if job:
            job_dict = dict(job)
            item["update_job"] = job_dict
            item["update_job_id"] = job_dict.get("job_id", "")
            item["update_status"] = job_dict.get("status") or item.get("update_status", "")
            item["update_target_version"] = job_dict.get("target_version") or item.get("update_target_version", "")
            item["update_error"] = job_dict.get("last_error") or item.get("update_error", "")
            item["update_progress_bytes"] = job_dict.get("progress_bytes", 0)
            item["update_total_bytes"] = job_dict.get("total_bytes", 0)
        agents.append(item)
    return agents


def get_agent_by_ip(ip: str) -> dict | None:
    """按客户端 IP 查询在线 Agent（匹配 agent 上报的 ip 字段，逗号分隔多 IP）"""
    if not ip:
        return None
    db = get_db()
    row = db.execute(
        "SELECT * FROM agents WHERE ip LIKE ? ORDER BY last_seen DESC LIMIT 1",
        (f"%{ip}%",)
    ).fetchone()
    return dict(row) if row else None


def get_agent_by_machine_id(machine_id: str) -> dict | None:
    """按硬件设备码查询 Agent（同一台机器始终返回同一条记录）"""
    if not machine_id:
        return None
    db = get_db()
    row = db.execute(
        "SELECT * FROM agents WHERE machine_id = ? ORDER BY last_seen DESC LIMIT 1",
        (machine_id,)
    ).fetchone()
    return dict(row) if row else None


def delete_agent(name: str) -> dict | None:
    """删除 Agent 及其所有关联数据（截图文件+DB、应用事件、浏览器历史）

    返回: {"deleted": {...}} 成功时；None 表示 Agent 不存在
    """
    import re
    import shutil

    # 安全检查：拒绝含路径遍历字符的恶意 agent 名
    # 允许中文、英文、数字、下划线、点、连字符、空格
    if not name or not re.match(r'^[a-zA-Z0-9_.\-一-鿿\s]+$', name):
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

    # 5. 删除诊断日志（外键约束，必须在删除 Agent 之前）
    db.execute("DELETE FROM diagnostic_logs WHERE agent_name = ?", (name,))

    # 6. 删除 Agent 自身
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

def list_screenshot_rules(enabled_only: bool = False) -> list[dict]:
    db = get_db()
    if enabled_only:
        rows = db.execute(
            """SELECT * FROM screenshot_rules
               WHERE enabled = 1
               ORDER BY rule_type ASC, id DESC"""
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT * FROM screenshot_rules
               ORDER BY enabled DESC, rule_type ASC, id DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_foreground_event(agent_name: str, timestamp: str, max_age_seconds: int = 30) -> dict | None:
    """取截图时间附近最近一次前台窗口事件，供服务端历史保存策略兜底使用。"""
    db = get_db()
    try:
        shot_time = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        shot_time = datetime.now()
    start = (shot_time - timedelta(seconds=max_age_seconds)).isoformat()
    end = (shot_time + timedelta(seconds=max_age_seconds)).isoformat()
    row = db.execute(
        """SELECT * FROM app_events
           WHERE agent_name = ?
             AND event_type = 'app_switch'
             AND timestamp >= ?
             AND timestamp <= ?
           ORDER BY ABS((julianday(timestamp) - julianday(?)) * 86400.0) ASC, id DESC
           LIMIT 1""",
        (agent_name, start, end, timestamp),
    ).fetchone()
    return dict(row) if row else None


def get_recent_browser_record(agent_name: str, timestamp: str, max_age_seconds: int = 120) -> dict | None:
    """取截图时间附近最近一次浏览器历史记录，作为旧 Agent 网页 URL 规则的弱兜底。"""
    db = get_db()
    try:
        shot_time = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        shot_time = datetime.now()
    start = (shot_time - timedelta(seconds=max_age_seconds)).isoformat()
    end = (shot_time + timedelta(seconds=max_age_seconds)).isoformat()
    row = db.execute(
        """SELECT * FROM browser_history
           WHERE agent_name = ?
             AND last_visit >= ?
             AND last_visit <= ?
           ORDER BY ABS((julianday(last_visit) - julianday(?)) * 86400.0) ASC, id DESC
           LIMIT 1""",
        (agent_name, start, end, timestamp),
    ).fetchone()
    return dict(row) if row else None


def create_screenshot_rule(rule_type: str, pattern: str, enabled: bool = True) -> dict:
    db = get_db()
    now = datetime.now().isoformat()
    cursor = db.execute(
        """INSERT INTO screenshot_rules (rule_type, pattern, enabled, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (rule_type, pattern, 1 if enabled else 0, now, now),
    )
    db.commit()
    row = db.execute("SELECT * FROM screenshot_rules WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def update_screenshot_rule(rule_id: int, rule_type: str | None = None, pattern: str | None = None,
                           enabled: bool | None = None) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM screenshot_rules WHERE id = ?", (rule_id,)).fetchone()
    if not row:
        return None

    current = dict(row)
    new_rule_type = rule_type if rule_type is not None else current["rule_type"]
    new_pattern = pattern if pattern is not None else current["pattern"]
    new_enabled = (1 if enabled else 0) if enabled is not None else current["enabled"]
    db.execute(
        """UPDATE screenshot_rules
           SET rule_type = ?, pattern = ?, enabled = ?, updated_at = ?
           WHERE id = ?""",
        (new_rule_type, new_pattern, new_enabled, datetime.now().isoformat(), rule_id),
    )
    db.commit()
    updated = db.execute("SELECT * FROM screenshot_rules WHERE id = ?", (rule_id,)).fetchone()
    return dict(updated) if updated else None


def delete_screenshot_rule(rule_id: int) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM screenshot_rules WHERE id = ?", (rule_id,))
    db.commit()
    return cursor.rowcount > 0


def save_screenshot(agent_name: str, timestamp: str, image_b64: str,
                    monitor_index: int = 0, monitor_total: int = 1,
                    metadata: dict | None = None) -> int | None:
    """将截图保存到文件系统，索引写入数据库

    节流策略: 每屏 2 秒窗口内已有截图则跳过，保留最早一张 (4fps 采集 → ~0.5fps/屏 存储)
    """
    import base64
    from datetime import datetime, timedelta

    try:
        db = get_db()

        # 节流: 仅检查“当前帧之前 2 秒内”的已存截图，避免乱序上传时误保留后到的较新帧
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            parsed = None

        if parsed is not None:
            window_start = (parsed - timedelta(seconds=2)).isoformat()
            existing = db.execute(
                """SELECT id FROM screenshots
                   WHERE agent_name = ?
                     AND monitor_index = ?
                     AND timestamp >= ?
                     AND timestamp <= ?
                   ORDER BY timestamp ASC LIMIT 1""",
                (agent_name, monitor_index, window_start, timestamp)
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
        generate_screenshot_variants(file_path)

        # 写入数据库索引
        meta = metadata or {}
        cursor = db.execute(
            """INSERT INTO screenshots (agent_name, timestamp, file_path, file_size,
                       monitor_index, monitor_total, foreground_process_name,
                       foreground_window_title, foreground_url, matched_rule_type,
                       matched_rule_pattern, save_policy_phase)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_name, timestamp, file_path, file_size, monitor_index, monitor_total,
                meta.get("foreground_process_name", ""),
                meta.get("foreground_window_title", ""),
                meta.get("foreground_url", ""),
                meta.get("matched_rule_type", ""),
                meta.get("matched_rule_pattern", ""),
                meta.get("save_policy_phase", ""),
            )
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
    return [enrich_screenshot_urls(dict(r)) for r in rows]


def delete_screenshot(screenshot_id: int) -> bool:
    """删除单张截图（文件 + DB 索引）"""
    db = get_db()
    row = db.execute("SELECT file_path FROM screenshots WHERE id = ?", (screenshot_id,)).fetchone()
    if not row:
        return False
    _remove_screenshot_files(row["file_path"])
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


def delete_screenshots_range(agent_name: str, date_from: str, date_to: str,
                             monitor_index: int = None) -> dict:
    """按时间范围删除截图（文件 + DB 索引）"""
    db = get_db()
    conditions = ["agent_name = ?", "timestamp >= ?", "timestamp <= ?"]
    params = [agent_name, date_from, date_to]
    if monitor_index is not None:
        conditions.append("monitor_index = ?")
        params.append(monitor_index)

    where = " AND ".join(conditions)
    rows = db.execute(
        f"SELECT id, file_path, file_size FROM screenshots WHERE {where}",
        params,
    ).fetchall()

    deleted_count = 0
    freed_bytes = 0
    for row in rows:
        actual_freed = _remove_screenshot_files(row["file_path"])
        db.execute("DELETE FROM screenshots WHERE id = ?", (row["id"],))
        deleted_count += 1
        freed_bytes += actual_freed or row["file_size"] or 0

    db.commit()
    return {"deleted_count": deleted_count, "freed_bytes": freed_bytes}


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
    return enrich_screenshot_urls(dict(row)) if row else None


def get_screenshot_dates(agent_name: str, date_from: str = "", date_to: str = "") -> list[dict]:
    """返回指定 Agent 有截图的日期列表及每天数量，供日历组件使用"""
    db = get_db()
    params = [agent_name]
    where = ["agent_name = ?"]
    if date_from:
        where.append("timestamp >= ?")
        params.append(date_from)
    if date_to:
        where.append("timestamp <= ?")
        params.append(date_to)
    rows = db.execute(
        f"""SELECT substr(timestamp, 1, 10) as date,
                   COUNT(*) as count
            FROM screenshots
            WHERE {' AND '.join(where)}
            GROUP BY date
            ORDER BY date ASC""",
        params,
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
    today = datetime.now().strftime("%Y-%m-%d")
    end_time = datetime.now().isoformat(timespec="seconds")
    conditions = ["agent_name = ?", "event_type = 'app_switch'"]
    params = [agent_name]
    if date:
        conditions.append("date(timestamp) = ?")
        params.append(date)
        if date != today:
            end_time = f"{date}T23:59:59"
    where = " AND ".join(conditions)
    sql = f"""
        WITH ordered AS (
            SELECT
                process_name,
                window_title,
                timestamp,
                LEAD(timestamp) OVER (ORDER BY timestamp ASC) AS next_timestamp
            FROM app_events
            WHERE {where}
        ),
        durations AS (
            SELECT
                process_name,
                window_title,
                MAX(0, (julianday(COALESCE(next_timestamp, ?)) - julianday(timestamp)) * 86400.0) AS seconds
            FROM ordered
        )
        SELECT process_name,
               COUNT(*) as switch_count,
               COALESCE(SUM(seconds), 0) as total_seconds,
               MAX(window_title) as last_window_title
        FROM durations
        GROUP BY process_name
        ORDER BY total_seconds DESC
        LIMIT 20"""
    rows = db.execute(sql, [*params, end_time]).fetchall()
    return [
        {**dict(r), "total_minutes": round((dict(r)["total_seconds"] or 0) / 60, 1)}
        for r in rows
    ]


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


def get_app_events_with_screenshots(agent_name: str, limit: int = 50, offset: int = 0,
                                    monitor_index: int = None,
                                    date_from: str = None,
                                    date_to: str = None) -> list[dict]:
    """最近应用事件时间线，每条关联最近时间的截图

    匹配策略 (按优先级):
    1. 精确匹配 — 事件携带 screenshot_timestamp 时直接关联 (Enter/窗口切换触发的即时截图)
    2. 事后兜底 — 事件后任意时间的最近截图
    3. 事前兜底 — 事件前最近的截图
    """
    db = get_db()
    where_parts = ["ae.agent_name = ?"]
    where_params = [agent_name]
    if date_from:
        where_parts.append("ae.timestamp >= ?")
        where_params.append(date_from)
    if date_to:
        where_parts.append("ae.timestamp <= ?")
        where_params.append(date_to)
    where_sql = " AND ".join(where_parts)

    rows = db.execute(f"""
        SELECT ae.*,
            COALESCE(
                (SELECT s.id FROM screenshots s
                 WHERE s.agent_name = ae.agent_name
                    AND (? IS NULL OR s.monitor_index = ?)
                    AND ae.screenshot_timestamp != ''
                    AND s.timestamp = ae.screenshot_timestamp
                  LIMIT 1),
                 (SELECT s.id FROM screenshots s
                  WHERE s.agent_name = ae.agent_name
                    AND (? IS NULL OR s.monitor_index = ?)
                    AND s.timestamp >= ae.timestamp
                  ORDER BY s.timestamp ASC LIMIT 1),
                 (SELECT s.id FROM screenshots s
                  WHERE s.agent_name = ae.agent_name
                    AND (? IS NULL OR s.monitor_index = ?)
                    AND s.timestamp <= ae.timestamp
                  ORDER BY s.timestamp DESC LIMIT 1)
            ) as screenshot_id,
            COALESCE(
                (SELECT s.timestamp FROM screenshots s
                 WHERE s.agent_name = ae.agent_name
                    AND (? IS NULL OR s.monitor_index = ?)
                    AND ae.screenshot_timestamp != ''
                    AND s.timestamp = ae.screenshot_timestamp
                  LIMIT 1),
                 (SELECT s.timestamp FROM screenshots s
                  WHERE s.agent_name = ae.agent_name
                    AND (? IS NULL OR s.monitor_index = ?)
                    AND s.timestamp >= ae.timestamp
                  ORDER BY s.timestamp ASC LIMIT 1),
                 (SELECT s.timestamp FROM screenshots s
                  WHERE s.agent_name = ae.agent_name
                    AND (? IS NULL OR s.monitor_index = ?)
                    AND s.timestamp <= ae.timestamp
                  ORDER BY s.timestamp DESC LIMIT 1)
            ) as screenshot_time
        FROM app_events ae
        WHERE {where_sql}
        ORDER BY ae.timestamp DESC
        LIMIT ? OFFSET ?
    """, (
        monitor_index, monitor_index,
        monitor_index, monitor_index,
        monitor_index, monitor_index,
        monitor_index, monitor_index,
        monitor_index, monitor_index,
        monitor_index, monitor_index,
        *where_params, limit, offset,
    )).fetchall()
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
                                          offset: int = 0,
                                          monitor_index: int = None) -> list[dict]:
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
                       AND (? IS NULL OR s.monitor_index = ?)
                       AND s.timestamp <= bh.last_visit
                     ORDER BY s.timestamp DESC LIMIT 1),
                    (SELECT s.id FROM screenshots s
                     WHERE s.agent_name = bh.agent_name
                       AND (? IS NULL OR s.monitor_index = ?)
                       AND s.timestamp >= bh.last_visit
                     ORDER BY s.timestamp ASC LIMIT 1)
               ) as screenshot_id,
               COALESCE(
                    (SELECT s.timestamp FROM screenshots s
                     WHERE s.agent_name = bh.agent_name
                       AND (? IS NULL OR s.monitor_index = ?)
                       AND s.timestamp <= bh.last_visit
                     ORDER BY s.timestamp DESC LIMIT 1),
                    (SELECT s.timestamp FROM screenshots s
                     WHERE s.agent_name = bh.agent_name
                       AND (? IS NULL OR s.monitor_index = ?)
                       AND s.timestamp >= bh.last_visit
                     ORDER BY s.timestamp ASC LIMIT 1)
               ) as screenshot_time
            FROM browser_history bh
            WHERE bh.agent_name = ?
            ORDER BY bh.last_visit DESC LIMIT ? OFFSET ?""",
            (
                monitor_index, monitor_index,
                monitor_index, monitor_index,
                monitor_index, monitor_index,
                monitor_index, monitor_index,
                agent_name, limit, offset,
            )
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT bh.*,
               COALESCE(
                   (SELECT s.id FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND (? IS NULL OR s.monitor_index = ?)
                      AND s.timestamp <= bh.last_visit
                    ORDER BY s.timestamp DESC LIMIT 1),
                   (SELECT s.id FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND (? IS NULL OR s.monitor_index = ?)
                      AND s.timestamp >= bh.last_visit
                    ORDER BY s.timestamp ASC LIMIT 1)
               ) as screenshot_id,
               COALESCE(
                   (SELECT s.timestamp FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND (? IS NULL OR s.monitor_index = ?)
                      AND s.timestamp <= bh.last_visit
                    ORDER BY s.timestamp DESC LIMIT 1),
                   (SELECT s.timestamp FROM screenshots s
                    WHERE s.agent_name = bh.agent_name
                      AND (? IS NULL OR s.monitor_index = ?)
                      AND s.timestamp >= bh.last_visit
                    ORDER BY s.timestamp ASC LIMIT 1)
               ) as screenshot_time
            FROM browser_history bh
            ORDER BY bh.last_visit DESC LIMIT ? OFFSET ?""",
            (
                monitor_index, monitor_index,
                monitor_index, monitor_index,
                monitor_index, monitor_index,
                monitor_index, monitor_index,
                limit, offset,
            )
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
    cutoff = (datetime.now() - timedelta(seconds=AGENT_ONLINE_TIMEOUT_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "total_screenshots": _count(db, "screenshots", agent_name),
        "today_app_events": _count(db, "app_events", agent_name, "date(timestamp) = ?", [today]),
        "total_browser_records": _count(db, "browser_history", agent_name),
        "online_agents": db.execute(
            "SELECT COUNT(*) FROM agents WHERE status = 'online' AND last_seen >= ?",
            (cutoff,),
        ).fetchone()[0],
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
        actual_freed = _remove_screenshot_files(row["file_path"])
        db.execute("DELETE FROM screenshots WHERE id = ?", (row["id"],))
        deleted_count += 1
        freed_bytes += actual_freed or row["file_size"] or 0

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
