# Agent 下载页设计文档

> 日期: 2026-06-20
> 状态: 已确认

## 1. 背景与目标

当前 Agent 分发完全依赖手动复制 .exe 文件，没有 Web 下载入口，无法检测被控机是否已安装 Agent。

**目标**：
- Dashboard Server 提供 Web 下载页面，被控机用户通过浏览器即可下载
- 自动检测当前机器是否已安装 Agent，避免重复下载
- 下载的 .exe 双击即可一键安装（自动注册计划任务 + 启动）

## 2. 架构

```
被控机浏览器 ──→ http://server:14325/download
                    │
                    ├─ 1. 加载下载页 (独立 HTML，不走 Vue SPA)
                    ├─ 2. JS 自动检测本机 Agent 状态
                    │     └─ POST /api/agent/detect
                    ├─ 3. 点击下载
                    │     └─ GET /api/agent/download → 流式返回 .exe
                    └─ 4. 双击 .exe → 自动注册计划任务 + 启动
```

### 新增文件

| 文件 | 作用 |
|------|------|
| `server/static/download.html` | 独立下载页（深色风格，自带 CSS） |
| `server/static/agent/monitor-agent.exe` | 托管的 Agent 安装包 |

### 改动文件

| 文件 | 改动 |
|------|------|
| `server/routes.py` | 新增 `/api/agent/download`、`/api/agent/detect` 两个路由 |
| `server/models.py` | agents 表新增 `ip` 字段；新增 `get_agent_by_ip()` 函数 |
| `server/main.py` | 新增 `/download` 路由指向 download.html |
| `agent/main.py` | 心跳上报本机 IP；首次运行自动注册计划任务 |
| `agent/config.py` | 新增 `get_local_ip()` 工具函数 |

### 不改动

- Vue Dashboard 代码不动
- 现有 Agent 采集功能不动

## 3. 下载页设计

### 页面路径

`http://server:14325/download` — 独立 HTML 页面，不走 Vue SPA 构建。

### UI 布局

```
┌─────────────────────────────────────┐
│  🖥️ Monitor Agent 下载              │
│                                     │
│  ┌───────────────────────────────┐  │
│  │ ✅ Agent 已安装并运行中        │  │  ← 检测到已安装时显示
│  │ 机器名: 试验机-01             │  │
│  │ 状态: 在线                    │  │
│  │ [重新下载]                    │  │
│  └───────────────────────────────┘  │
│                                     │
│  ── 或 ──                           │
│                                     │
│  ┌───────────────────────────────┐  │
│  │ ⬇️ 下载 Agent (61 MB)         │  │  ← 未安装时显示
│  │ Windows 10/11 · v1.0          │  │
│  │ [下载 .exe]                   │  │
│  └───────────────────────────────┘  │
│                                     │
│  安装说明:                          │
│  1. 下载后双击运行                  │
│  2. 程序自动注册为开机启动          │
│  3. 无需手动配置                    │
│                                     │
│  ⚠️ 如被杀毒软件拦截，请添加信任    │
└─────────────────────────────────────┘
```

### 状态显示逻辑

| 检测结果 | 显示 |
|----------|------|
| found=true, status=online | ✅ Agent 已安装并运行中 + 机器名 |
| found=true, status=offline | ⚠️ Agent 已安装但离线 + 重新下载按钮 |
| found=false | ⬇️ 下载按钮 |
| 检测失败（网络错误等） | ⬇️ 下载按钮（降级，不阻断） |

### 风格

- 深色背景（与 Dashboard 统一：`#1a1a2e`）
- 圆角卡片，渐变按钮
- 响应式布局，手机也能用
- 自带 CSS，不依赖外部资源

## 4. API 设计

### GET /api/agent/download

下载 Agent 安装包。

- 返回 `FileResponse`，路径 `server/static/agent/monitor-agent.exe`
- Header: `Content-Disposition: attachment; filename="MonitorAgent.exe"`
- Header: `Content-Length` 让浏览器显示进度

### POST /api/agent/detect

检测当前客户端是否已安装 Agent。

**请求体**：无（从 `request.client.host` 获取客户端 IP）

**响应**：
```json
{
  "found": true,
  "agent_name": "试验机-01",
  "status": "online"
}
```

**逻辑**：
1. 从 `request.client.host` 获取客户端 IP
2. 查询 agents 表：`WHERE ip LIKE '%客户端IP%' AND status='online'`
3. 找到 → 返回 found=true + agent 信息
4. 未找到 → 返回 found=false

## 5. Agent 改造

### 5.1 心跳上报 IP

Agent 心跳 POST `/api/heartbeat` 新增 `ip` 字段：

```python
data = {
    "agent_name": agent_name,
    "status": "online",
    "ip": get_local_ip()  # 新增
}
```

`get_local_ip()` 获取本机所有非回环网卡 IP，拼为逗号分隔字符串。

### 5.2 一键安装（自动注册计划任务）

改造 Agent 启动逻辑，在 `main()` 入口处新增：

```python
def ensure_scheduled_task():
    """检查并注册 Windows 计划任务（开机自启）"""
    task_name = "MonitorAgent"
    # 检查是否已存在
    result = subprocess.run(
        ["schtasks.exe", "/Query", "/TN", task_name],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return  # 已注册，跳过

    # 获取当前 exe 路径
    exe_path = sys.executable if getattr(sys, 'frozen', False) else __file__
    vbs_path = os.path.join(os.path.dirname(exe_path), "run-hidden.vbs")

    # 创建 run-hidden.vbs（如果不存在）
    if not os.path.exists(vbs_path):
        with open(vbs_path, 'w') as f:
            f.write(f'Set WshShell = CreateObject("WScript.Shell")\n')
            f.write(f'WshShell.Run """{exe_path}""", 0, False')

    # 注册计划任务（需要管理员权限）
    subprocess.run([
        "schtasks.exe", "/Create",
        "/TN", task_name,
        "/TR", f'wscript.exe "{vbs_path}"',
        "/SC", "ONLOGON",
        "/RL", "HIGHEST",
        "/F"
    ], check=True)
```

**权限处理**：
- 注册计划任务需要管理员权限
- 双击 .exe 时如果权限不足，`schtasks.exe` 会失败
- 此时 Agent 正常运行（只是不注册自启动），控制台输出提示
- 用户可以右键「以管理员身份运行」来完成注册

**UAC 行为**：
- 如果 .exe 的 manifest 请求 `requireAdministrator`，每次启动都会弹 UAC
- 如果 .exe 的 manifest 请求 `asInvoker`，首次注册时 schtasks 可能失败
- **推荐**：manifest 用 `asInvoker`，注册失败时输出提示但不阻断运行

### 5.3 Agent.spec 改动

PyInstaller spec 文件无需改动。`run-hidden.vbs` 会在首次运行时自动创建。

## 6. 数据库改动

### agents 表新增 ip 字段

```sql
ALTER TABLE agents ADD COLUMN ip TEXT DEFAULT '';
```

在 `init_db()` 中添加迁移（与其他迁移一样，try/except 幂等）。

### 心跳路由改造

`/api/heartbeat` 接收并存储 `ip` 字段。

## 7. 部署流程

管理员视角的完整流程：

1. 在开发机运行 `agent/build.bat` → 产出 `agent/dist/monitor-agent.exe`
2. 复制 .exe 到 `server/static/agent/monitor-agent.exe`
3. 重启 Server（或首次启动时自动创建目录）
4. 告诉被控机用户：「打开 http://server:14325/download 下载安装」

## 8. 边界情况

| 场景 | 处理 |
|------|------|
| Agent 离线但已安装 | 显示「⚠️ Agent 已安装但离线」+ 重新下载按钮 |
| 多网卡多 IP | Agent 上报所有网卡 IP（逗号分隔），detect 时 LIKE 匹配 |
| 同一局域网 NAT | 检测可能失败，降级为「不确定」→ 显示下载按钮 |
| .exe 被杀毒拦截 | 下载页提示「如被拦截，请添加信任」 |
| .exe 未部署到 static 目录 | 下载接口返回 404，页面提示「请联系管理员上传安装包」 |
| Server 重启 | .exe 在 static 目录，不受影响 |
| Agent 已在运行但计划任务未注册 | 检测显示「已安装」，用户可右键管理员运行重新注册 |
