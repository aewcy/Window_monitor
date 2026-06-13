# 电脑监控系统 Demo

> ⚠️ **法律声明**: 本软件仅供合法授权的企业内部IT管理使用。部署前必须获得被监控方书面知情同意。严禁用于隐私侵犯、间谍活动或非法监控。

## 架构

```
试验机 (被监控)             Linux 服务器 (中转+存储)          管理端 (查看)
┌────────────────┐         ┌─────────────────────┐         ┌──────────────┐
│ Agent (Python) │ ─HTTP─▶ │ FastAPI Server       │◀─浏览器─│ Web Dashboard │
│ ├ 屏幕截图     │         │ ├ 数据接收 API       │         │              │
│ ├ 应用窗口     │         │ ├ SQLite 存储        │         │              │
│ └ 浏览器历史   │         │ └ 截图文件存储       │         │              │
└────────────────┘         └─────────────────────┘         └──────────────┘
```

**三个角色**：
- **试验机**: 运行精简 Agent，只做采集+上报
- **Linux 服务器**: 中间层，接收数据、存储、提供 API 和面板
- **管理端**: 浏览器打开 Web 面板查看

## 快速开始

### 1. Linux 服务器 (核心) — Docker 部署 (推荐)

```bash
git clone git@github.com:aewcy/monitor-aewcy.git
cd monitor-aewcy/server

# 一键启动
docker compose up -d

# 查看日志
docker compose logs -f
```

启动后：
- 监控面板: `http://<服务器IP>:8899/`
- API 文档: `http://<服务器IP>:8899/docs`

更新部署：

```bash
cd monitor-aewcy/server
git pull
docker compose up -d --build
```

数据持久化在 `./data/` 目录（容器重建不丢失）。

### 1-alt. 裸机部署 (无 Docker)

```bash
cd monitor-aewcy/server
pip install -r requirements.txt
python main.py
```

### 2. 试验机 (Agent)

**Windows — 双击运行：**

```
① 进入 agent/ 目录
② 双击 start.bat   ← 自动检测环境、缺啥装啥、启动
（第一次自动装 venv + 依赖，之后秒开）
```

首次运行前，右键编辑 `start.bat`，修改服务器地址：
```batch
set MONITOR_SERVER_HOST=你的服务器IP    ← 改成这个
set AGENT_NAME=试验机-01               ← 可自定义机器名
```

**Linux 桌面 — 命令行：**

```bash
sudo yum install xdotool   # 或 apt install xdotool
cd agent
pip install -r requirements.txt
MONITOR_SERVER_HOST=<服务器IP> python main.py
```

### 3. 跨网络

试验机和服务器不在同一网络时，用内网穿透：

```bash
# 在服务器上 (最简单)
ngrok http 8899
# 得到 https://xxx.ngrok-free.app
# 把 agent/config.py 的 SERVER_HOST 改成这个域名
```

## 项目结构

```
monitor-aewcy/
├── agent/                          # ← 被控端 (试验机)
│   ├── main.py                     # Agent 主程序
│   ├── config.py                   # 配置 (服务器地址等)
│   ├── screen_capture.py           # 屏幕截图
│   ├── app_tracker.py              # 窗口追踪
│   ├── browser_history.py          # 浏览器历史
│   ├── requirements.txt            # Agent 依赖
│   └── start.bat                   # Windows 双击即用 (自检环境)
├── server/                         # ← 服务端 (Linux 服务器)
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # 服务端配置
│   ├── models.py                   # SQLite 数据层
│   ├── routes.py                   # REST API
│   ├── static/
│   │   └── dashboard.html          # Web 监控面板
│   ├── requirements.txt            # 服务端依赖
│   ├── Dockerfile                  # Docker 镜像
│   ├── docker-compose.yml          # Docker 编排
│   └── .dockerignore
├── .gitignore
└── README.md
```

## 配置参数

### Agent (`agent/config.py`)

| 参数 | 默认 | 说明 |
|------|------|------|
| `SERVER_HOST` | `127.0.0.1` | 服务器地址 |
| `SERVER_PORT` | `8899` | 服务器端口 |
| `AGENT_NAME` | `试验机-01` | 机器标识 |
| `SCREENSHOT_INTERVAL` | `30` | 截图间隔(秒) |
| `APP_TRACK_INTERVAL` | `5` | 窗口检测间隔(秒) |
| `BROWSER_HISTORY_INTERVAL` | `60` | 浏览器采集间隔(秒) |
| `SCREENSHOT_QUALITY` | `40` | JPEG质量 |
| `SCREENSHOT_MAX_WIDTH` | `1280` | 截图最大宽度 |

所有参数支持环境变量覆盖，例如：
```bash
export AGENT_NAME="财务部-PC-03"
export SERVER_HOST=10.0.0.100
python main.py
```

### Server (`server/config.py`)

| 参数 | 默认 | 说明 |
|------|------|------|
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8899` | 监听端口 |
| `MAX_SCREENSHOT_AGE_DAYS` | `7` | 截图保留天数 |

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/heartbeat` | Agent 心跳 |
| POST | `/api/status` | Agent 状态上报 |
| POST | `/api/screenshot` | 上传截图 (base64 JPEG) |
| POST | `/api/app_event` | 活跃窗口上报 |
| POST | `/api/browser_history` | 浏览器历史上报 |
| GET | `/api/agents` | 在线终端列表 |
| GET | `/api/dashboard/stats` | 仪表盘统计 |
| GET | `/api/screenshots?agent=xx` | 截图列表 |
| GET | `/api/screenshots/latest?agent=xx` | 最新截图 |
| GET | `/api/screenshots/image/{id}` | 截图文件 |
| GET | `/api/app_usage?agent=xx` | 应用使用汇总 |
| GET | `/api/browser_history?agent=xx` | 浏览器历史 |
