"""
FastAPI 路由定义
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from models import (
    init_db, upsert_agent, get_agents, delete_agent, get_db,
    save_screenshot, get_screenshots, get_latest_screenshot,
    get_screenshot_dates, get_screenshot_hours,
    delete_screenshot, delete_screenshots_batch,
    save_app_event, get_app_usage_summary,
    save_browser_history, get_browser_history,
    get_browser_history_with_screenshots,
    get_app_events, get_app_events_with_screenshots,
    get_dashboard_stats,
)

router = APIRouter(prefix="/api")

# 观察者心跳 - 记录 Dashboard 最后访问时间
_viewer_last_seen: dict[str, datetime] = {}

# Agent 上报的当前截图间隔
_agent_intervals: dict[str, float] = {}


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

@router.post("/heartbeat")
async def heartbeat(data: dict):
    """接收 Agent 心跳"""
    agent_name = data.get("agent_name", "unknown")
    upsert_agent(agent_name, "online")
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
    upsert_agent(agent_name, status, message)
    return {"status": "ok"}


@router.post("/screenshot")
async def screenshot(data: dict):
    """接收截图"""
    agent_name = data.get("agent_name", "unknown")
    timestamp = data.get("timestamp", datetime.now().isoformat())
    image_b64 = data.get("image_base64", "")

    if not image_b64:
        raise HTTPException(status_code=400, detail="缺少截图数据")

    # 更新 agent 在线状态
    upsert_agent(agent_name, "online")

    # 保存截图
    screenshot_id = save_screenshot(agent_name, timestamp, image_b64)
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


@router.get("/agents")
async def list_agents():
    """Agent 列表，附带当前截图间隔"""
    agents = get_agents()
    for a in agents:
        a["screenshot_interval"] = _agent_intervals.get(a["name"], 0)
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


@router.get("/screenshots")
async def list_screenshots(
    agent: Optional[str] = Query(None),
    limit: int = Query(50, le=2000),
    offset: int = Query(0),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """截图列表，支持日期范围过滤"""
    return get_screenshots(agent, limit, offset, date_from, date_to)


@router.get("/screenshots/latest")
async def latest_screenshot(agent: str = Query(...)):
    """获取最新截图"""
    result = get_latest_screenshot(agent)
    if not result:
        raise HTTPException(status_code=404, detail="暂无截图")
    return result


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
    with_screenshots: bool = Query(False),
):
    """最近应用事件时间线 - 可选关联截图"""
    if with_screenshots:
        return get_app_events_with_screenshots(agent, limit)
    return get_app_events(agent, limit)


@router.get("/browser_history")
async def browser_history_list(
    agent: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    with_screenshots: bool = Query(False),
):
    """浏览器历史列表 - 可选关联截图"""
    if with_screenshots:
        return get_browser_history_with_screenshots(agent, limit, offset)
    return get_browser_history(agent, limit, offset)
