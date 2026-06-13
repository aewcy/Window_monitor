"""
服务端主程序 - 运行在监控机上
FastAPI + 静态文件服务 + 自动初始化
"""
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import HOST, PORT, DATA_DIR, SCREENSHOT_DIR, CORS_ORIGINS
from models import init_db
from routes import router

# 初始化目录
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    init_db()
    print("=" * 60)
    print(f"  Monitor Server started")
    print(f"  Listen: http://{HOST}:{PORT}")
    print(f"  API Docs: http://localhost:{PORT}/docs")
    print(f"  Dashboard: http://localhost:{PORT}/")
    print("=" * 60)
    yield


# 创建 FastAPI 应用
app = FastAPI(
    title="Monitor Server",
    description="Monitor System - Server",
    version="0.1.0-demo",
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

# 注册 API 路由
app.include_router(router)

# 静态文件 - Dashboard
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """监控面板主页"""
    index_path = os.path.join(STATIC_DIR, "dashboard.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Dashboard not found</h1>")


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
