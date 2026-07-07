# Server — 服务端 (监控机)

运行在 Linux 服务器上，接收 Agent 上报的数据，存储到 SQLite，提供 REST API 和 Web 监控面板。

## 部署方式

### 方式一：Docker (推荐)

```bash
cd server
docker compose up -d
```

- 监控面板: `http://<服务器IP>:14325/`
- API 文档: `http://<服务器IP>:14325/docs`

数据持久化在 `./data/` 目录（容器重建不丢失）。

更新部署：

```bash
cd server
git pull
docker compose up -d --build
```

### 方式二：裸机部署

```bash
cd server
pip install -r requirements.txt
python main.py
```

## 配置

[config.py](config.py)：

| 参数 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| `HOST` | `SERVER_HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `SERVER_PORT` | `8899` | 容器内监听端口，宿主机可额外映射 `14325` 给 Web 访问 |
| `AGENT_API_PORT` | `AGENT_API_PORT` | `8899` | Agent/API 专用外部端口，非 `/api/*` 路径会拒绝 |
| `WEB_PUBLIC_PORT` | `WEB_PUBLIC_PORT` | `14325` | Web 面板和下载页对外展示端口 |
| `DATA_DIR` | `DATA_DIR` | `data` | 数据目录 (DB + 截图) |
| `CORS_ORIGINS` | `CORS_ORIGINS` | `["*"]` | CORS 允许源 |

## API 接口

### Agent → Server (数据上报)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/config?agent=xx` | 拉取动态配置 (截图间隔) |
| POST | `/api/heartbeat` | Agent 心跳 |
| POST | `/api/status` | Agent 上下线 |
| POST | `/api/screenshot` | 上传截图 (base64 JPEG) |
| POST | `/api/app_event` | 上报应用事件 (窗口切换/Enter) |
| POST | `/api/browser_history` | 上报浏览器历史 |

### Dashboard → Server (数据查询)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/viewer/heartbeat` | 观察者心跳 (Dashboard 每秒 ping) |
| GET | `/api/agents` | Agent 列表 |
| GET | `/api/dashboard/stats` | 仪表盘统计 |
| GET | `/api/screenshots?agent=xx` | 截图列表 |
| GET | `/api/screenshots/latest?agent=xx` | 最新截图 |
| GET | `/api/screenshots/image/{id}` | 截图文件 |
| GET | `/api/app_usage?agent=xx` | 应用使用汇总 |
| GET | `/api/app_events?agent=xx` | 事件时间线 (支持 with_screenshots) |
| GET | `/api/browser_history?agent=xx` | 浏览器历史 (支持 with_screenshots) |
| GET | `/api/screenshots/dates?agent=xx` | 有截图的日期列表 |
| GET | `/api/screenshots/hours?agent=xx&date=YYY-MM-DD` | 指定日期有截图的小时列表 |
| DELETE | `/api/agents/{name}` | 删除 Agent 及全部关联数据 |
| GET | `/api/storage/stats` | 存储用量统计 |
| POST | `/api/storage/cleanup` | 清理过期截图 `{older_than_hours: 480}` |
| POST | `/api/diagnostics` | Agent 上报诊断信息 |
| GET | `/api/logs` | 诊断日志查询 (支持 category/level/pattern) |
| GET | `/api/logs/categories` | 日志分类及计数 |

## 数据库

SQLite，自动建表。表结构见 [models.py](models.py)：

- `agents` — Agent 在线状态
- `screenshots` — 截图索引 (文件存文件系统)
- `app_events` — 应用事件 (含 screenshot_timestamp 精确关联)
- `browser_history` — 浏览器历史
- `diagnostic_logs` — 诊断日志 (Agent 上报 + Server 内部)

## 文件清单

```
server/
├── main.py                 # FastAPI 入口
├── config.py               # 配置
├── models.py               # SQLite 数据层
├── routes.py               # REST API 路由
├── requirements.txt        # Python 依赖
├── Dockerfile              # Docker 镜像
├── docker-compose.yml      # Docker 编排
├── .dockerignore
├── logger.py                # 日志模块 (按天轮转)
├── static/
│   ├── dist/               # 当前 Vue Dashboard 构建产物
│   ├── download.html       # 下载页
│   └── dashboard-v0-raycast.html # 旧版回退页
└── data/                   # 运行时数据 (gitignore)
    ├── monitor.db
    └── screenshots/
```
