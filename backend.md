# Backend — Server 后端需求文档

> FastAPI + SQLite 服务端 (`server/`)

## 架构

```
Agent ──HTTP POST──▶ FastAPI Server ──▶ SQLite DB
                         │                  │
                         ▼                  ▼
                    文件系统存储         Dashboard 查询
                  (截图 JPEG)
```

## 数据库 (SQLite, 5 表)

### agents — Agent 注册表
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增 |
| name | TEXT UNIQUE | Agent 原始名称（由 AGENT_NAME 环境变量决定） |
| display_name | TEXT | Web 端自定义显示名（空则回退到 name） |
| status | TEXT | online/offline |
| last_seen | TEXT | 最后心跳时间 |
| first_seen | TEXT | 首次上线时间 |
| message | TEXT | 状态消息 |

### screenshots — 截图索引表
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增 |
| agent_name | TEXT FK | 关联 Agent |
| timestamp | TEXT | ISO 时间戳 |
| file_path | TEXT | 文件系统路径 |
| file_size | INTEGER | 文件大小(字节) |
| monitor_index | INTEGER | 显示器索引(0-based) |
| monitor_total | INTEGER | 总显示器数 |

**存储路径**: `data/screenshots/{agent}/{date}/{timestamp}_m{monitor_index}.jpg`

**节流策略**: 每屏 2 秒窗口内已有截图则跳过，保留最早一张
```sql
SELECT id FROM screenshots
WHERE agent_name = ? AND timestamp >= ? AND monitor_index = ?
ORDER BY timestamp ASC LIMIT 1
```

**索引**: `idx_screenshots_agent_time ON (agent_name, timestamp DESC)`

### app_events — 应用事件表
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增 |
| agent_name | TEXT FK | 关联 Agent |
| event_type | TEXT | app_switch / chat_enter |
| window_title | TEXT | 窗口标题 |
| process_name | TEXT | 进程名 |
| process_path | TEXT | 进程路径 |
| display_name | TEXT | 显示名称(聊天应用) |
| timestamp | TEXT | 事件时间 |
| duration_seconds | REAL | 持续时长 |
| screenshot_timestamp | TEXT | 关联截图时间戳 |

### browser_history — 浏览器历史表
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增 |
| agent_name | TEXT FK | 关联 Agent |
| url | TEXT | 网址 |
| title | TEXT | 页面标题 |
| visit_count | INTEGER | 访问次数 |
| last_visit | TEXT | 最后访问时间 |
| browser | TEXT | 浏览器名 |

**去重**: `UNIQUE(agent_name, url, last_visit)`

### diagnostic_logs — 诊断日志表
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增 |
| agent_name | TEXT FK | 关联 Agent |
| category | TEXT | network/storage/capture/system/security/server |
| level | TEXT | INFO/WARNING/ERROR |
| message | TEXT | 日志内容 |
| timestamp | TEXT | 记录时间 |

## API 端点

### 数据接收 (Agent → Server)

#### POST /api/screenshot
接收截图，自动节流。
```json
{
  "agent_name": "试验机-01",
  "timestamp": "2026-06-17T14:32:05",
  "image_base64": "/9j/4AAQ...",
  "format": "jpeg",
  "monitor_index": 0,
  "monitor_total": 2
}
```
**响应**: `{"status": "ok", "id": 42}` — 节流时返回已有截图 ID

#### POST /api/app_event
接收应用事件。
```json
{
  "agent_name": "试验机-01",
  "type": "app_switch",
  "window_title": "GitHub — monitor-demo",
  "process_name": "chrome.exe",
  "process_path": "C:\\...",
  "timestamp": "2026-06-17T14:32:05",
  "screenshot_timestamp": "2026-06-17T14:32:05"
}
```

#### POST /api/browser_history
接收浏览器历史（批量）。
```json
{
  "agent_name": "试验机-01",
  "records": [
    {"url": "https://...", "title": "...", "visit_count": 3, "last_visit": "...", "browser": "chrome"}
  ]
}
```

#### POST /api/heartbeat
Agent 心跳。
```json
{"agent_name": "试验机-01", "screenshot_interval": 0.25}
```

#### POST /api/status
Agent 状态变更。
```json
{"agent_name": "试验机-01", "status": "online", "message": "Agent started"}
```

#### POST /api/diagnostics
Agent 诊断上报。
```json
{"agent_name": "试验机-01", "category": "network", "level": "ERROR", "message": "连接失败"}
```

### 数据查询 (Dashboard → Server)

#### GET /api/agents
返回 Agent 列表，附带当前截图间隔和 display_name。

#### PATCH /api/agents/{name}
修改 Agent 显示名称。
```json
{"display_name": "新名字"}
```
**响应**: `{"status": "ok", "display_name": "新名字"}`

#### GET /api/screenshots/latest?agent=X&monitor=N
返回最新截图记录。`monitor` 可选，筛选特定显示器。

#### GET /api/screenshots?agent=X&limit=50&offset=0&date_from=&date_to=&monitor=N
截图列表，支持分页/日期范围/显示器筛选。

#### GET /api/screenshots/image/{id}
返回截图 JPEG 文件。

#### GET /api/screenshots/dates?agent=X
返回有截图的日期列表及每天数量。用于日历组件高亮有数据的日期。

#### GET /api/screenshots/hours?agent=X&date=YYYY-MM-DD
返回指定日期内有截图的小时列表及每小时数量。用于时段筛选。

#### GET /api/app_events?agent=X&limit=20&offset=0&with_screenshots=true
活动记录，支持分页。`with_screenshots=true` 时每条记录关联最近截图的 `screenshot_id`。

**截图关联策略** (COALESCE 三级 fallback):
1. 精确匹配 — 事件携带 `screenshot_timestamp` 时直接关联
2. 事后兜底 — 事件后最近的截图
3. 事前兜底 — 事件前最近的截图

#### GET /api/browser_history?agent=X&limit=100&offset=0&with_screenshots=true
浏览器历史。`with_screenshots=true` 时每条记录关联最近截图。

**截图关联策略** (COALESCE 二级 fallback):
1. 访问前最近的截图
2. 访问后最近的截图

#### GET /api/logs?category=&level=&agent=&pattern=&limit=200&offset=0
诊断日志查询，支持正则筛选。

#### GET /api/logs/categories
日志分类及计数。

#### GET /api/dashboard/stats?agent=X
仪表盘统计: 总截图数、今日事件数、浏览器记录数、在线 Agent 数。

#### GET /api/storage/stats
存储使用统计。

### 观察者心跳 & 动态配置

#### POST /api/viewer/heartbeat
Dashboard 每秒调用，表示有人在看。

#### GET /api/config?agent=X
Agent 轮询动态配置。
```json
{
  "screenshot_interval": 1,  // 有人看→1s, 没人看→5s
  "app_track_interval": 2
}
```

### 存储管理

#### POST /api/storage/cleanup
清理过期截图。
```json
{"older_than_hours": 480, "agent": "试验机-01"}
```

#### DELETE /api/screenshots/{id}
删除单张截图。

#### POST /api/screenshots/delete-batch
批量删除。
```json
{"ids": [1, 2, 3]}
```

#### DELETE /api/agents/{name}
删除 Agent 及所有关联数据。

## 关键设计决策

### 截图节流
- **策略**: 2 秒窗口内已有截图则跳过，保留最早一张
- **目的**: Agent 以 4fps 采集，存储降为 ~0.5fps/屏
- **SQL**: `ORDER BY timestamp ASC LIMIT 1` 确保保留最早

### 多显示器支持
- **文件名**: `{timestamp}_m{monitor_index}.jpg` 防止覆盖
- **索引**: `screenshots` 表有 `monitor_index` 列
- **筛选**: 所有截图查询 API 支持 `monitor` 参数

### 截图-事件关联
- **精确关联**: 事件携带 `screenshot_timestamp`，直接匹配
- **时间邻近**: 无精确关联时，按时间最近匹配
- **三级 fallback**: 精确 → 事后 → 事前

### 线程安全
- **连接**: `threading.local()` 每线程独立 SQLite 连接
- **模式**: WAL 模式支持并发读
- **节流**: SELECT + INSERT 无事务锁，存在 TOCTOU 竞态（极端情况下可能多存一张）

### 安全
- **CORS**: 可配置允许源
- **响应头**: CSP / X-Frame-Options / X-Content-Type-Options
- **CSP 策略**:
  - `default-src 'self'`
  - `script-src 'self' 'unsafe-inline'`
  - `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`
  - `font-src 'self' https://fonts.gstatic.com`
  - `img-src 'self' data: blob:`
  - `connect-src 'self'`
  - `frame-ancestors 'none'`
- **Agent 删除**: 拒绝含路径遍历字符的名称

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| SERVER_HOST | 0.0.0.0 | 监听地址 |
| SERVER_PORT | 8899 | 监听端口 |
| DATA_DIR | server/data/ | 数据存储目录 |
| CORS_ORIGINS | * | CORS 允许源 |

## 技术栈

- **Python 3.11+** (Docker: python:3.11-slim)
- **FastAPI** — Web 框架
- **uvicorn** — ASGI 服务器
- **SQLite** — 数据库 (WAL 模式)
- **无 ORM** — 原生 sqlite3 + `?` 占位符
- **Node.js 20** — Vue Dashboard 构建 (Docker 多阶段)
- **Docker 多阶段构建**: Stage 1 (node:20-slim) 构建 Vue → Stage 2 (python:3.11-slim) 运行服务

## 待优化

- [ ] 截图节流 TOCTOU 竞态 — 需要事务锁或 UNIQUE 约束
- [ ] `save_screenshot` 返回 None 时路由仍返回 HTTP 200
- [ ] `except ValueError` 捕获不到 `timestamp=None` 的 `TypeError`
- [ ] 文件写入和 DB INSERT 不是原子操作，失败时可能产生孤立文件
- [ ] SQLite 连接永不关闭，长期运行可能泄漏文件描述符
- [ ] `query_diagnostics` 正则筛选在 Python 侧过滤，数据量大时性能堪忧
- [ ] `loadLogs` 每次 refreshAll 都请求，即使日志面板折叠
