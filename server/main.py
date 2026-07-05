"""
服务端主程序 - 运行在监控机上
FastAPI + 静态文件服务 + 自动初始化
"""
import asyncio
import hashlib
import hmac
import os
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    HOST, PORT, DATA_DIR, SCREENSHOT_DIR, CORS_ORIGINS,
    SCREENSHOT_RETENTION_HOURS, SCREENSHOT_CLEANUP_INTERVAL_MINUTES,
    AGENT_API_PORT, WEB_PUBLIC_PORT, WEB_AUTH_USER, WEB_AUTH_PASSWORD, WEB_AUTH_SECRET,
)
from logger import log
from models import init_db, cleanup_old_screenshots
from routes import router

# 初始化目录
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

SESSION_COOKIE = "crkrd_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60


LOGIN_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CRKRD</title>
<style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#111113;color:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}.login{width:min(360px,calc(100vw - 32px));padding:24px;border:1px solid #34343c;border-radius:8px;background:#1b1b1f;box-shadow:0 24px 70px rgba(0,0,0,.42)}h1{margin:0 0 18px;font-size:24px;letter-spacing:0}.field{display:flex;flex-direction:column;gap:7px;margin-bottom:12px}label{font-size:12px;color:#a1a1aa}input{height:40px;border:1px solid #34343c;border-radius:6px;background:#111113;color:#f4f4f5;padding:0 11px;font-size:14px;outline:none}input:focus{border-color:#2f81d7}button{width:100%;height:42px;margin-top:8px;border:0;border-radius:6px;background:#2f81d7;color:#fff;font-size:14px;font-weight:700;cursor:pointer}button:disabled{opacity:.65;cursor:default}.error{min-height:18px;margin-top:12px;color:#ef4444;font-size:12px}
</style>
</head>
<body>
<main class="login">
  <h1>CRKRD</h1>
  <form id="login-form">
    <div class="field"><label>账户</label><input id="username" autocomplete="username" value="admin"></div>
    <div class="field"><label>密码</label><input id="password" type="password" autocomplete="current-password" autofocus></div>
    <button id="submit" type="submit">登录</button>
    <div id="error" class="error"></div>
  </form>
</main>
<script>
const form=document.getElementById("login-form");
const btn=document.getElementById("submit");
const err=document.getElementById("error");
form.addEventListener("submit",async(e)=>{
  e.preventDefault();
  err.textContent="";
  btn.disabled=true;
  try{
    const resp=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:document.getElementById("username").value,password:document.getElementById("password").value})});
    if(!resp.ok) throw new Error("login");
    window.location.reload();
  }catch{
    err.textContent="账户或密码错误";
  }finally{
    btn.disabled=false;
  }
});
</script>
</body>
</html>"""


def _session_signature(username: str, expires_at: int) -> str:
    payload = f"{username}:{expires_at}".encode("utf-8")
    return hmac.new(WEB_AUTH_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _make_session_token(username: str) -> str:
    expires_at = int(time.time()) + SESSION_MAX_AGE_SECONDS
    return f"{username}:{expires_at}:{_session_signature(username, expires_at)}"


def _valid_session_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        username, expires_raw, signature = token.split(":", 2)
        expires_at = int(expires_raw)
    except (ValueError, TypeError):
        return False
    if username != WEB_AUTH_USER or expires_at < int(time.time()):
        return False
    expected = _session_signature(username, expires_at)
    return hmac.compare_digest(signature, expected)


def _is_authenticated(request: Request) -> bool:
    return _valid_session_token(request.cookies.get(SESSION_COOKIE))


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
    version="0.57",
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


class LoginPayload(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
async def login(payload: LoginPayload):
    if not (
        hmac.compare_digest(payload.username, WEB_AUTH_USER)
        and hmac.compare_digest(payload.password, WEB_AUTH_PASSWORD)
    ):
        return Response(status_code=401)
    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        SESSION_COOKIE,
        _make_session_token(payload.username),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


def _request_port(request: Request) -> int | None:
    """从 Host 头解析外部访问端口。"""
    if request.url.port:
        return request.url.port
    host = request.headers.get("host", "")
    if ":" not in host:
        return None
    try:
        return int(host.rsplit(":", 1)[1])
    except ValueError:
        return None


@app.middleware("http")
async def port_and_auth_middleware(request: Request, call_next):
    """8899 只给 Agent/API 使用；14325 的 Web 页面与 Web API 需要登录。"""
    path = request.url.path
    port = _request_port(request)
    if port == AGENT_API_PORT and not path.startswith("/api/"):
        return Response(status_code=503)
    if port == WEB_PUBLIC_PORT and path != "/api/auth/login":
        if not _is_authenticated(request):
            if path.startswith("/api/"):
                return Response(status_code=401)
            return HTMLResponse(LOGIN_HTML, status_code=200)
    return await call_next(request)


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

# 截图派生图静态直出；原图查看仍优先走 API id 路由。
if os.path.exists(SCREENSHOT_DIR):
    app.mount("/media/screenshots", StaticFiles(directory=SCREENSHOT_DIR), name="screenshots-media")


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
