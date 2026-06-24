"""
FastAPI 路由定义
"""
import os
import zipfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from models import (
    init_db, upsert_agent, get_agents, delete_agent, rename_agent, get_db,
    save_screenshot, get_screenshots, get_latest_screenshot,
    get_screenshot_dates, get_screenshot_hours,
    delete_screenshot, delete_screenshots_batch,
    save_app_event, get_app_usage_summary,
    save_browser_history, get_browser_history,
    get_browser_history_with_screenshots,
    get_app_events, get_app_events_with_screenshots,
    get_dashboard_stats,
    get_storage_stats, cleanup_old_screenshots,
    save_diagnostic, query_diagnostics, get_diagnostic_categories,
    get_agent_by_ip, get_agent_by_machine_id,
)
from logger import log, format_log_entry

router = APIRouter(prefix="/api")

# 观察者心跳 - 记录 Dashboard 最后访问时间
_viewer_last_seen: dict[str, datetime] = {}

# Agent 上报的当前截图间隔
_agent_intervals: dict[str, float] = {}

# Live 最新帧缓存。它不入库，只服务实时画面；历史/网格仍读取 screenshots 表。
_latest_live_frames: dict[tuple[str, int], dict] = {}


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
    upsert_agent(agent_name, "online", ip=ip, machine_id=machine_id)
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
    upsert_agent(agent_name, status, message, machine_id=machine_id)
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

    _latest_live_frames[(agent_name, int(monitor_index or 0))] = {
        "id": f"live:{agent_name}:{monitor_index}:{timestamp}",
        "agent_name": agent_name,
        "timestamp": timestamp,
        "image_base64": image_b64,
        "format": data.get("format", "jpeg"),
        "monitor_index": monitor_index,
        "monitor_total": monitor_total,
        "capture_interval": capture_interval,
    }

    # 入库存储仍执行 2 秒节流；Live 画面读取上面的内存最新帧，不受节流影响。
    screenshot_id = save_screenshot(agent_name, timestamp, image_b64,
                                    monitor_index, monitor_total)
    return {"status": "ok", "id": screenshot_id}


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
async def latest_live_screenshot(agent: str = Query(...), monitor: Optional[int] = Query(None)):
    """获取 Agent 最近一次上传的实时帧，不受截图入库节流影响"""
    if monitor is not None:
        result = _latest_live_frames.get((agent, monitor))
        if result:
            return result
    else:
        candidates = [frame for (name, _), frame in _latest_live_frames.items() if name == agent]
        if candidates:
            return max(candidates, key=lambda item: item.get("timestamp", ""))
    raise HTTPException(status_code=404, detail="暂无实时截图")


@router.get("/screenshots/dates")
async def screenshot_dates(agent: str = Query(...)):
    """返回有截图的日期列表及每天数量"""
    return get_screenshot_dates(agent)


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
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    with_screenshots: bool = Query(False),
    monitor: Optional[int] = Query(None),
):
    """最近应用事件时间线 - 可选关联截图"""
    if with_screenshots:
        return get_app_events_with_screenshots(agent, limit, offset, monitor)
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
AGENT_EXE_PATH = os.path.join(AGENT_STATIC_DIR, "monitor-agent.exe")
AGENT_ZIP_PATH = os.path.join(AGENT_STATIC_DIR, "MonitorAgent.zip")
AGENT_INSTALLER_PATH = os.path.join(AGENT_STATIC_DIR, "install-agent.ps1")
AGENT_INSTALL_BAT_PATH = os.path.join(AGENT_STATIC_DIR, "install-agent.bat")
AGENT_UNINSTALL_BAT_PATH = os.path.join(AGENT_STATIC_DIR, "uninstall-agent.bat")


def _agent_package_sources():
    return [
        (AGENT_EXE_PATH, "monitor-agent.exe"),
        (AGENT_INSTALL_BAT_PATH, "install-agent.bat"),
        (AGENT_UNINSTALL_BAT_PATH, "uninstall-agent.bat"),
        (AGENT_INSTALLER_PATH, "install-agent.ps1"),
    ]


def _agent_package_is_fresh() -> bool:
    if not os.path.exists(AGENT_ZIP_PATH):
        return False
    expected_names = {archive_name for _, archive_name in _agent_package_sources()}
    try:
        with zipfile.ZipFile(AGENT_ZIP_PATH, "r") as zf:
            if expected_names - set(zf.namelist()):
                return False
    except zipfile.BadZipFile:
        return False
    package_mtime = os.path.getmtime(AGENT_ZIP_PATH)
    return all(os.path.getmtime(path) <= package_mtime for path, _ in _agent_package_sources())


def _build_agent_package():
    os.makedirs(os.path.dirname(AGENT_ZIP_PATH), exist_ok=True)
    with zipfile.ZipFile(AGENT_ZIP_PATH, "w", zipfile.ZIP_STORED) as zf:
        for path, archive_name in _agent_package_sources():
            zf.write(path, archive_name)


@router.get("/agent/download")
async def download_agent():
    """下载 Agent 安装包（zip）"""
    missing = [archive_name for path, archive_name in _agent_package_sources() if not os.path.exists(path)]
    if missing:
        raise HTTPException(status_code=404, detail=f"安装包文件缺失: {', '.join(missing)}")

    if not _agent_package_is_fresh():
        _build_agent_package()

    return FileResponse(
        path=AGENT_ZIP_PATH,
        filename="MonitorAgent.zip",
        media_type="application/zip",
    )
