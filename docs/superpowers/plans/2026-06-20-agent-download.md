# Agent 下载页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Dashboard Server 上提供独立的 Agent 下载页面，支持自动检测已安装状态，下载的 .exe 双击即可一键安装。

**Architecture:** Server 托管 .exe 文件 + 提供 detect/download API；独立 HTML 下载页（不走 Vue SPA）；Agent 心跳上报本机 IP + 首次运行自动注册 Windows 计划任务。

**Tech Stack:** FastAPI, SQLite, vanilla HTML/CSS/JS, Python subprocess (schtasks.exe)

## Global Constraints

- 所有中文注释和 UI 文本
- Server 端口 `14325`，数据目录 `server/data/`
- Agent 注册计划任务名: `MonitorAgent`
- .exe 托管路径: `server/static/agent/monitor-agent.exe`
- 不改动 Vue Dashboard 代码
- 不改动现有 Agent 采集功能
- 数据库迁移用 `ALTER TABLE ... ADD COLUMN` + `try/except` 幂等

---

### Task 1: Database — agents 表新增 ip 字段 + 查询函数

**Files:**
- Modify: `server/models.py:28-102` (init_db 迁移段)
- Modify: `server/models.py:169-191` (upsert_agent 函数)
- Modify: `server/models.py:193-198` (get_agents 函数后新增)

**Interfaces:**
- Produces: `upsert_agent(name, status, message, ip)` — 新增 `ip` 参数
- Produces: `get_agent_by_ip(ip: str) -> dict | None` — 按 IP 查询在线 Agent

- [ ] **Step 1: 在 init_db() 末尾添加 ip 字段迁移**

在 `server/models.py` 的 `init_db()` 函数末尾（第 161 行 `except sqlite3.OperationalError` 之后）添加：

```python
    # 向前兼容迁移: 为 agents 表添加 ip 列
    try:
        db.execute("ALTER TABLE agents ADD COLUMN ip TEXT DEFAULT ''")
        db.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在
```

- [ ] **Step 2: 修改 upsert_agent 支持 ip 参数**

将 `server/models.py` 的 `upsert_agent` 函数（第 169-190 行）改为：

```python
def upsert_agent(name: str, status: str = "online", message: str = "", ip: str = ""):
    name = name.strip()
    if not name:
        return
    db = get_db()
    try:
        db.execute(
            """INSERT INTO agents (name, status, last_seen, message, ip)
               VALUES (?, ?, datetime('now', 'localtime'), ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 status=excluded.status,
                 last_seen=excluded.last_seen,
                 message=excluded.message,
                 ip=excluded.ip""",
            (name, status, message, ip)
        )
    except sqlite3.IntegrityError:
        # 并发 INSERT 竞态兜底：另一个线程先 INSERT 成功，改为 UPDATE
        db.execute(
            "UPDATE agents SET status=?, last_seen=datetime('now','localtime'), message=?, ip=? WHERE name=?",
            (status, message, ip, name)
        )
    db.commit()
```

- [ ] **Step 3: 新增 get_agent_by_ip 函数**

在 `server/models.py` 的 `get_agents()` 函数之后（第 198 行后）添加：

```python
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
```

- [ ] **Step 4: 验证 — 重启 Server 检查迁移**

```bash
cd server && python main.py
```

Expected: 启动日志无报错，数据库自动添加 `ip` 列。

- [ ] **Step 5: Commit**

```bash
git add server/models.py
git commit -m "feat: agents 表新增 ip 字段 + get_agent_by_ip 查询"
```

---

### Task 2: Server API — detect + download 路由

**Files:**
- Modify: `server/routes.py` (末尾新增两个路由)
- Modify: `server/routes.py:91-100` (heartbeat 路由接收 ip)

**Interfaces:**
- Consumes: `upsert_agent(name, status, message, ip)` — 来自 Task 1
- Consumes: `get_agent_by_ip(ip)` — 来自 Task 1
- Produces: `POST /api/agent/detect` — 返回 `{found, agent_name, status}`
- Produces: `GET /api/agent/download` — 返回 FileResponse

- [ ] **Step 1: 修改 heartbeat 路由接收 ip 字段**

将 `server/routes.py` 的 heartbeat 路由（第 91-100 行）改为：

```python
@router.post("/heartbeat")
async def heartbeat(data: dict):
    """接收 Agent 心跳"""
    agent_name = data.get("agent_name", "unknown")
    ip = data.get("ip", "")
    upsert_agent(agent_name, "online", ip=ip)
    # 记录 Agent 当前截图间隔
    interval = data.get("screenshot_interval", 0)
    if interval:
        _agent_intervals[agent_name] = interval
    return {"status": "ok"}
```

- [ ] **Step 2: 在 routes.py 顶部导入新函数**

在 `server/routes.py` 的 import 段（第 9 行）修改：

```python
from models import (
    save_screenshot, get_screenshots, get_screenshot_dates, get_screenshot_hours,
    get_agents, upsert_agent, delete_agent, rename_agent,
    save_app_event, get_app_usage_summary, get_app_events, get_app_events_with_screenshots,
    save_browser_history, get_browser_history, get_browser_history_with_screenshots,
    get_dashboard_stats, get_storage_stats, cleanup_old_screenshots,
    save_diagnostic, query_diagnostics, get_diagnostic_categories,
    get_agent_by_ip,
)
```

- [ ] **Step 3: 在 routes.py 末尾新增 detect 和 download 路由**

在 `server/routes.py` 文件末尾（`router` 定义结束后）添加：

```python
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


AGENT_EXE_PATH = os.path.join(os.path.dirname(__file__), "static", "agent", "monitor-agent.exe")


@router.get("/agent/download")
async def download_agent():
    """下载 Agent 安装包 (.exe)"""
    if not os.path.exists(AGENT_EXE_PATH):
        raise HTTPException(status_code=404, detail="安装包未上传，请联系管理员")
    return FileResponse(
        path=AGENT_EXE_PATH,
        filename="MonitorAgent.exe",
        media_type="application/octet-stream",
    )
```

- [ ] **Step 4: 验证 — 重启 Server 测试 API**

```bash
cd server && python main.py
# 另一个终端:
curl -X POST http://localhost:14325/api/agent/detect
# Expected: {"found": false}
curl -I http://localhost:14325/api/agent/download
# Expected: 404 (因为 .exe 还没放到 static/agent/ 目录)
```

- [ ] **Step 5: Commit**

```bash
git add server/routes.py
git commit -m "feat: /api/agent/detect 和 /api/agent/download 路由"
```

---

### Task 3: Server — /download 页面路由 + download.html

**Files:**
- Modify: `server/main.py:90-103` (dashboard 路由后新增)
- Create: `server/static/download.html`

**Interfaces:**
- Consumes: `POST /api/agent/detect` — 来自 Task 2
- Consumes: `GET /api/agent/download` — 来自 Task 2
- Produces: `GET /download` — 返回独立 HTML 页面

- [ ] **Step 1: 在 main.py 新增 /download 路由**

在 `server/main.py` 的 dashboard 路由之后（第 103 行后）添加：

```python
@app.get("/download", response_class=HTMLResponse)
async def download_page():
    """Agent 下载页 — 独立 HTML，不走 Vue SPA"""
    html_path = os.path.join(STATIC_DIR, "download.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Download page not found</h1>", status_code=404)
```

- [ ] **Step 2: 创建 download.html**

创建 `server/static/download.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Monitor Agent 下载</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }
  .container {
    max-width: 480px;
    width: 100%;
  }
  .header {
    text-align: center;
    margin-bottom: 32px;
  }
  .header h1 {
    font-size: 24px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 8px;
  }
  .header .icon {
    font-size: 48px;
    margin-bottom: 12px;
  }
  .card {
    background: #16213e;
    border: 1px solid #0f3460;
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 16px;
    transition: all 0.3s ease;
  }
  .card.detected {
    border-color: #00b894;
    background: #16213e;
  }
  .card.detected .status-icon { color: #00b894; }
  .card.offline {
    border-color: #fdcb6e;
    background: #16213e;
  }
  .card.offline .status-icon { color: #fdcb6e; }
  .status-icon {
    font-size: 20px;
    margin-right: 8px;
  }
  .status-line {
    display: flex;
    align-items: center;
    margin-bottom: 8px;
    font-size: 16px;
    font-weight: 600;
  }
  .status-detail {
    color: #8899aa;
    font-size: 13px;
    margin-bottom: 16px;
  }
  .btn {
    display: inline-block;
    padding: 12px 24px;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 600;
    text-decoration: none;
    cursor: pointer;
    border: none;
    transition: all 0.2s ease;
    text-align: center;
  }
  .btn-primary {
    background: linear-gradient(135deg, #0984e3, #6c5ce7);
    color: #fff;
    width: 100%;
  }
  .btn-primary:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(9, 132, 227, 0.4);
  }
  .btn-secondary {
    background: transparent;
    color: #0984e3;
    border: 1px solid #0984e3;
    width: 100%;
    margin-top: 8px;
  }
  .btn-secondary:hover {
    background: rgba(9, 132, 227, 0.1);
  }
  .size-info {
    color: #8899aa;
    font-size: 13px;
    margin-top: 8px;
    text-align: center;
  }
  .divider {
    text-align: center;
    color: #556677;
    font-size: 13px;
    margin: 16px 0;
  }
  .instructions {
    background: #16213e;
    border: 1px solid #0f3460;
    border-radius: 12px;
    padding: 20px;
    margin-top: 24px;
  }
  .instructions h3 {
    font-size: 14px;
    color: #8899aa;
    margin-bottom: 12px;
    font-weight: 500;
  }
  .instructions ol {
    padding-left: 20px;
    color: #b0b0b0;
    font-size: 14px;
    line-height: 1.8;
  }
  .warning {
    margin-top: 16px;
    padding: 12px;
    background: rgba(253, 203, 110, 0.1);
    border: 1px solid rgba(253, 203, 110, 0.3);
    border-radius: 8px;
    color: #fdcb6e;
    font-size: 13px;
  }
  .hidden { display: none; }
  .loading {
    text-align: center;
    color: #556677;
    padding: 40px;
  }
  .loading .spinner {
    display: inline-block;
    width: 24px;
    height: 24px;
    border: 3px solid #334455;
    border-top-color: #0984e3;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-bottom: 12px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .error-toast {
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: #d63031;
    color: #fff;
    padding: 12px 24px;
    border-radius: 8px;
    font-size: 14px;
    z-index: 100;
    opacity: 0;
    transition: opacity 0.3s;
  }
  .error-toast.show { opacity: 1; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="icon">🖥️</div>
    <h1>Monitor Agent 下载</h1>
  </div>

  <!-- 加载中 -->
  <div id="loading" class="loading">
    <div class="spinner"></div>
    <div>正在检测本机状态...</div>
  </div>

  <!-- 检测结果: 已安装 -->
  <div id="detected" class="card detected hidden">
    <div class="status-line">
      <span class="status-icon">✅</span>
      <span>Agent 已安装并运行中</span>
    </div>
    <div class="status-detail" id="detected-info"></div>
    <button class="btn btn-secondary" onclick="startDownload()">重新下载</button>
  </div>

  <!-- 检测结果: 已安装但离线 -->
  <div id="offline" class="card offline hidden">
    <div class="status-line">
      <span class="status-icon">⚠️</span>
      <span>Agent 已安装但离线</span>
    </div>
    <div class="status-detail" id="offline-info"></div>
    <button class="btn btn-primary" onclick="startDownload()">重新下载</button>
  </div>

  <!-- 未安装: 下载 -->
  <div id="download" class="card hidden">
    <button class="btn btn-primary" onclick="startDownload()">
      ⬇️ 下载 Agent
    </button>
    <div class="size-info">Windows 10/11 · 约 61 MB</div>
  </div>

  <!-- 安装说明 -->
  <div class="instructions">
    <h3>安装说明</h3>
    <ol>
      <li>下载完成后双击运行 MonitorAgent.exe</li>
      <li>程序自动注册为开机启动（需管理员权限确认）</li>
      <li>无需手动配置，安装即用</li>
    </ol>
    <div class="warning">
      ⚠️ 如被杀毒软件拦截，请将 MonitorAgent.exe 添加到信任列表
    </div>
  </div>
</div>

<div id="error-toast" class="error-toast"></div>

<script>
  function showError(msg) {
    const t = document.getElementById('error-toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 3000);
  }

  function startDownload() {
    window.location.href = '/api/agent/download';
  }

  async function detect() {
    try {
      const resp = await fetch('/api/agent/detect', { method: 'POST' });
      if (!resp.ok) throw new Error('检测请求失败');
      const data = await resp.json();

      document.getElementById('loading').classList.add('hidden');

      if (data.found) {
        if (data.status === 'online') {
          document.getElementById('detected').classList.remove('hidden');
          document.getElementById('detected-info').textContent =
            '机器名: ' + data.agent_name + ' · 状态: 在线';
        } else {
          document.getElementById('offline').classList.remove('hidden');
          document.getElementById('offline-info').textContent =
            '机器名: ' + data.agent_name + ' · 状态: 离线';
        }
      } else {
        document.getElementById('download').classList.remove('hidden');
      }
    } catch (e) {
      // 检测失败，降级显示下载按钮
      document.getElementById('loading').classList.add('hidden');
      document.getElementById('download').classList.remove('hidden');
    }
  }

  detect();
</script>
</body>
</html>
```

- [ ] **Step 3: 验证 — 浏览器访问下载页**

```bash
cd server && python main.py
```

打开浏览器访问 `http://localhost:14325/download`：
- 页面应显示加载动画，然后显示「下载」按钮（因为没有 Agent 运行）
- 点击下载按钮应返回 404（.exe 还没放到 static 目录）

- [ ] **Step 4: Commit**

```bash
git add server/main.py server/static/download.html
git commit -m "feat: /download 页面路由 + 独立下载页 HTML"
```

---

### Task 4: Agent — get_local_ip 工具函数

**Files:**
- Modify: `agent/config.py` (末尾新增函数)

**Interfaces:**
- Produces: `get_local_ip() -> str` — 返回逗号分隔的所有非回环网卡 IP

- [ ] **Step 1: 在 config.py 末尾新增 get_local_ip 函数**

在 `agent/config.py` 末尾添加：

```python
def get_local_ip() -> str:
    """获取本机所有非回环网卡 IP，逗号分隔"""
    import socket
    import subprocess

    ips = []
    try:
        # 方法1: 通过 socket 连接外部地址获取主 IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    # 方法2: 通过 ipconfig 获取所有网卡 IP（Windows）
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["ipconfig"], capture_output=True, text=True, timeout=3,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            import re
            for line in result.stdout.splitlines():
                m = re.search(r"IPv4[^:]*:\s*([\d.]+)", line)
                if m and m.group(1) not in ips:
                    ips.append(m.group(1))
        except Exception:
            pass

    return ",".join(ips) if ips else ""
```

- [ ] **Step 2: 验证 — 在本机运行测试**

```bash
cd agent && python -c "from config import get_local_ip; print(get_local_ip())"
```

Expected: 输出类似 `192.168.1.100` 或 `192.168.1.100,10.0.0.5`

- [ ] **Step 3: Commit**

```bash
git add agent/config.py
git commit -m "feat: get_local_ip 工具函数 — 获取本机所有网卡 IP"
```

---

### Task 5: Agent — 心跳上报 IP + 自动注册计划任务

**Files:**
- Modify: `agent/main.py:27-30` (Reporter 类 import)
- Modify: `agent/main.py:125-129` (heartbeat 方法)
- Modify: `agent/main.py:221-246` (main 函数开头)
- Modify: `agent/main.py:301-306` (heartbeat_loop)

**Interfaces:**
- Consumes: `get_local_ip() -> str` — 来自 Task 4
- Produces: 心跳 POST 增加 `ip` 字段
- Produces: 首次运行自动注册 `MonitorAgent` 计划任务

- [ ] **Step 1: Reporter.heartbeat 传递 ip 参数**

将 `agent/main.py` 的 `heartbeat` 方法（第 125-129 行）改为：

```python
    def heartbeat(self, screenshot_interval: float = 0, ip: str = ""):
        data = {
            "agent_name": self.agent,
            "screenshot_interval": screenshot_interval,
        }
        if ip:
            data["ip"] = ip
        self._post("heartbeat", data)
```

- [ ] **Step 2: main() 中获取 IP 并传入心跳循环**

在 `agent/main.py` 的 `main()` 函数中，在 `_resolve_agent_name` 之后（约第 236 行后）添加：

```python
    # 获取本机 IP（启动时获取一次，心跳时复用）
    from config import get_local_ip
    local_ip = get_local_ip()
    if local_ip:
        print(f"  [✓] 本机 IP: {local_ip}")
    else:
        print("  [!] 无法获取本机 IP")
```

修改 `heartbeat_loop` 函数（第 301-304 行）为：

```python
    # 心跳线程
    def heartbeat_loop():
        while True:
            reporter.heartbeat(screenshot.interval, local_ip)
            time.sleep(HEARTBEAT_INTERVAL)
```

- [ ] **Step 3: 新增 ensure_scheduled_task 函数**

在 `agent/main.py` 的 `main()` 函数之前（约第 220 行前）添加：

```python
def ensure_scheduled_task():
    """检查并注册 Windows 计划任务（开机自启）"""
    if not IS_WINDOWS:
        return

    task_name = "MonitorAgent"

    # 检查是否已存在
    try:
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", task_name],
            capture_output=True, text=True,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            return  # 已注册，跳过
    except FileNotFoundError:
        return  # schtasks.exe 不存在

    # 获取当前 exe 路径
    if getattr(sys, 'frozen', False):
        exe_path = sys.executable
    else:
        exe_path = os.path.abspath(__file__)

    exe_dir = os.path.dirname(exe_path)
    vbs_path = os.path.join(exe_dir, "run-hidden.vbs")

    # 创建 run-hidden.vbs（如果不存在）
    if not os.path.exists(vbs_path):
        try:
            with open(vbs_path, 'w', encoding='utf-8') as f:
                f.write('Set WshShell = CreateObject("WScript.Shell")\n')
                f.write(f'WshShell.Run """{exe_path}""", 0, False\n')
        except OSError:
            pass

    # 注册计划任务（需要管理员权限）
    try:
        result = subprocess.run(
            [
                "schtasks.exe", "/Create",
                "/TN", task_name,
                "/TR", f'wscript.exe "{vbs_path}"',
                "/SC", "ONLOGON",
                "/RL", "HIGHEST",
                "/F",
            ],
            capture_output=True, text=True,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            print(f"  [✓] 已注册计划任务: {task_name}")
        else:
            print(f"  [!] 注册计划任务失败（可能需要管理员权限）: {result.stderr.strip()}")
            print(f"  [!] 提示: 右键以管理员身份运行可完成注册")
    except Exception as e:
        print(f"  [!] 注册计划任务异常: {e}")
```

- [ ] **Step 4: 在 main() 开头调用 ensure_scheduled_task**

在 `agent/main.py` 的 `main()` 函数中，`stop_event` 参数处理之后、平台检测之前添加：

```python
    # 自动注册计划任务（首次运行）
    try:
        ensure_scheduled_task()
    except Exception as e:
        print(f"  [!] 计划任务注册跳过: {e}")
```

- [ ] **Step 5: 添加 subprocess 和 os import**

确认 `agent/main.py` 顶部有 `import subprocess` 和 `import os`（如果没有则添加）。检查现有 import 段。

- [ ] **Step 6: 验证 — 运行 Agent 检查心跳**

```bash
cd agent && python main.py
```

Expected:
- 启动时输出 `本机 IP: x.x.x.x`
- 启动时尝试注册计划任务（可能因权限失败，不影响运行）
- 心跳发送包含 `ip` 字段

- [ ] **Step 7: Commit**

```bash
git add agent/main.py
git commit -m "feat: Agent 心跳上报 IP + 首次运行自动注册计划任务"
```

---

### Task 6: 端到端验证

**Files:** 无新增/修改（验证所有改动协同工作）

- [ ] **Step 1: 部署 .exe 到 Server 静态目录**

```bash
mkdir -p server/static/agent
cp agent/dist/monitor-agent.exe server/static/agent/monitor-agent.exe
```

- [ ] **Step 2: 启动 Server**

```bash
cd server && python main.py
```

- [ ] **Step 3: 启动 Agent**

```bash
cd agent && python main.py
```

Expected: Agent 输出 `本机 IP: x.x.x.x`，心跳正常。

- [ ] **Step 4: 浏览器访问下载页**

打开 `http://localhost:14325/download`：
- 页面显示加载动画
- 自动检测到 Agent 在线
- 显示「✅ Agent 已安装并运行中」+ 机器名

- [ ] **Step 5: 测试下载**

点击「重新下载」按钮，浏览器应开始下载 MonitorAgent.exe（~61MB）。

- [ ] **Step 6: 测试未安装场景**

停止 Agent，刷新下载页：
- 应显示「⬇️ 下载 Agent」按钮

- [ ] **Step 7: 最终 Commit**

```bash
git add -A
git commit -m "feat: Agent 下载页功能完成 — 端到端验证通过"
```

---

## 部署备忘

1. 开发机运行 `agent/build.bat` → 产出 `agent/dist/monitor-agent.exe`
2. 复制 .exe 到 `server/static/agent/monitor-agent.exe`
3. 重启 Server
4. 告诉被控机用户：「打开 http://server:14325/download 下载安装」
