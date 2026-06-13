"""
FastAPI 路由定义
"""
import os
import base64
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from models import (
    init_db, upsert_agent, get_agents, get_db,
    save_screenshot, get_screenshots, get_latest_screenshot,
    save_app_event, get_app_usage_summary,
    save_browser_history, get_browser_history,
    get_dashboard_stats,
)

router = APIRouter(prefix="/api")


# ============================================
# 健康检查
# ============================================

@router.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


# ============================================
# 数据接收 (Agent -> Server)
# ============================================

@router.post("/heartbeat")
async def heartbeat(data: dict):
    """接收 Agent 心跳"""
    agent_name = data.get("agent_name", "unknown")
    upsert_agent(agent_name, "online")
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
    """Agent 列表"""
    return get_agents()


@router.get("/screenshots")
async def list_screenshots(
    agent: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    """截图列表"""
    return get_screenshots(agent, limit, offset)


@router.get("/screenshots/latest")
async def latest_screenshot(agent: str = Query(...)):
    """获取最新截图"""
    result = get_latest_screenshot(agent)
    if not result:
        raise HTTPException(status_code=404, detail="暂无截图")
    return result


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


@router.get("/app_usage")
async def app_usage(
    agent: str = Query(...),
    date: Optional[str] = Query(None),
):
    """应用使用汇总"""
    return get_app_usage_summary(agent, date)


@router.get("/browser_history")
async def browser_history_list(
    agent: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    """浏览器历史列表"""
    return get_browser_history(agent, limit, offset)
