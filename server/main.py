"""
服务端主程序 - 运行在监控机上
FastAPI + 静态文件服务 + 自动初始化
"""
import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import (
    HOST, PORT, DATA_DIR, SCREENSHOT_DIR, CORS_ORIGINS,
    SCREENSHOT_RETENTION_HOURS, SCREENSHOT_CLEANUP_INTERVAL_MINUTES,
)
from logger import log
from models import init_db, cleanup_old_screenshots
from routes import router

# 初始化目录
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


async def storage_cleanup_loop():
    """后台定时清理历史截图，避免磁盘无限增长。"""
    interval_seconds = max(60, SCREENSHOT_CLEANUP_INTERVAL_MINUTES * 60)
    while True:
        try:
            result = cleanup_old_screenshots(SCREENSHOT_RETENTION_HOURS)
            log.info(
                "自动清理完成: deleted=%s freed_bytes=%s cutoff=%s retention_hours=%s",
                result["deleted_count"],
                result["freed_bytes"],
                result["cutoff_time"],
                SCREENSHOT_RETENTION_HOURS,
                extra={"category": "storage"},
            )
        except Exception as exc:
            log.warning(
                "自动清理失败: %s",
                exc,
                extra={"category": "storage"},
            )
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    init_db()
    cleanup_task = None
    if SCREENSHOT_RETENTION_HOURS > 0 and SCREENSHOT_CLEANUP_INTERVAL_MINUTES > 0:
        cleanup_task = asyncio.create_task(storage_cleanup_loop())
    print("=" * 60)
    print(f"  Monitor Server started")
    print(f"  Listen: http://{HOST}:{PORT}")
    print(f"  API Docs: http://localhost:{PORT}/docs")
    print(f"  Dashboard: http://localhost:{PORT}/")
    print("=" * 60)
    try:
        yield
    finally:
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass


# 创建 FastAPI 应用
app = FastAPI(
    title="Monitor Server",
    description="Monitor System - Server",
    version="0.52",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 安全响应头中间件
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    # 禁止浏览器缓存 HTML，确保更新后立即生效
    if request.url.path in ("/", "/index.html", "/static/dashboard.html", "/static/dashboard-v0-raycast.html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# 注册 API 路由
app.include_router(router)

# 静态文件 - Dashboard
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """监控面板主页 — 优先 Vue dist，fallback 到旧 HTML"""
    # Vue 构建产物
    vue_dist = os.path.join(STATIC_DIR, "dist", "index.html")
    if os.path.exists(vue_dist):
        with open(vue_dist, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    # Fallback: 旧版单文件 Dashboard
    fallback = os.path.join(STATIC_DIR, "dashboard-v0-raycast.html")
    if os.path.exists(fallback):
        with open(fallback, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Dashboard not found</h1>")


@app.get("/download", response_class=HTMLResponse)
async def download_page():
    """Agent 下载页 — 独立 HTML，不走 Vue SPA"""
    html_path = os.path.join(STATIC_DIR, "download.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Download page not found</h1>", status_code=404)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc)},
    )


def main():
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
