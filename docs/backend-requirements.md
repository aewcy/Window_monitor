# 后端需求规格文档

> 基于 `server/routes.py`、`server/models.py`、`server/main.py`、`server/config.py` 源码提取。
> 最后更新: 2026-06-20

---

## 目录

1. [系统概述](#1-系统概述)
2. [配置项](#2-配置项)
3. [数据模型](#3-数据模型)
4. [API 端点一览](#4-api-端点一览)
5. [API 端点详细规格](#5-api-端点详细规格)
6. [业务规则](#6-业务规则)

---

## 1. 系统概述

服务端基于 **FastAPI** 框架，使用 **SQLite** 存储结构化数据，文件系统存储截图图片。

- 监听地址：`0.0.0.0:8899`（可配置）
- 数据库路径：`{DATA_DIR}/monitor.db`（WAL 模式，外键约束开启）
- 截图存储路径：`{DATA_DIR}/screenshots/{agent_name}/{date}/{timestamp}_m{monitor}.jpg`
- 线程安全：使用 `threading.local()` 线程本地连接
- API 前缀：`/api`（所有 API 路由挂在 `APIRouter(prefix="/api")` 下）
- CORS：默认允许所有来源（`*`），可配置
- 安全响应头：`X-Content-Type-Options`、`X-Frame-Options`、`X-XSS-Protection`、`Referrer-Policy`、`Permissions-Policy`、`Content-Security-Policy` 均在中间件中设置

---

## 2. 配置项

来源文件：`server/config.py`

| 配置项 | 环境变量名 | 默认值 | 说明 |
|--------|-----------|--------|------|
| `HOST` | `SERVER_HOST` | `0.0.0.0` | 服务绑定地址 |
| `PORT` | `SERVER_PORT` | `8899` | 服务端口 |
| `DATA_DIR` | `DATA_DIR` | `server/data/` | 数据根目录（数据库 + 截图） |
| `SCREENSHOT_DIR` | （自动派生） | `{DATA_DIR}/screenshots` | 截图文件存储目录 |
| `DB_PATH` | （自动派生） | `{DATA_DIR}/monitor.db` | SQLite 数据库文件路径 |
| `CORS_ORIGINS` | `CORS_ORIGINS` | `*` | 允许的跨域来源，逗号分隔 |

---

## 3. 数据模型

### 3.1 agents 表 — Agent 注册与状态

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `id` | INTEGER | PK | 自增 | 主键 |
| `name` | TEXT | 是 | — | Agent 唯一标识（UNIQUE） |
| `status` | TEXT | 否 | `'offline'` | 在线状态：`online` / `offline` |
| `last_seen` | TEXT | 否 | NULL | 最后心跳时间（ISO 格式本地时间） |
| `first_seen` | TEXT | 否 | 当前时间 | 首次注册时间 |
| `message` | TEXT | 否 | `''` | Agent 上报的状态消息 |
| `display_name` | TEXT | 否 | `''` | Web 端自定义显示名称 |

**关键操作：** `upsert_agent` / `delete_agent`（级联删除） / `rename_agent` / `get_agents`（按 last_seen DESC）

**安全校验：** `delete_agent` 用正则 `^[a-zA-Z0-9_.\-]+$` 校验 agent name，防止路径遍历攻击。

### 3.2 screenshots 表 — 截图索引

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `id` | INTEGER | PK | 自增 | 主键 |
| `agent_name` | TEXT | 是 | — | 所属 Agent（外键） |
| `timestamp` | TEXT | 是 | — | 截图时间（ISO 格式） |
| `file_path` | TEXT | 是 | — | 图片文件路径 |
| `file_size` | INTEGER | 否 | 0 | 图片字节数 |
| `monitor_index` | INTEGER | 否 | 0 | 显示器序号（从 0 开始） |
| `monitor_total` | INTEGER | 否 | 1 | Agent 总显示器数量 |

**关键操作：** `save_screenshot`（含 2 秒节流） / `get_screenshots` / `get_latest_screenshot` / `get_screenshot_dates` / `get_screenshot_hours` / `delete_screenshot` / `delete_screenshots_batch`

### 3.3 app_events 表 — 应用使用事件

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `id` | INTEGER | PK | 自增 | 主键 |
| `agent_name` | TEXT | 是 | — | 所属 Agent |
| `event_type` | TEXT | 是 | — | 事件类型（`window_switch` / `chat_enter`） |
| `window_title` | TEXT | 否 | `''` | 窗口标题 |
| `process_name` | TEXT | 否 | `''` | 进程名称 |
| `process_path` | TEXT | 否 | `''` | 进程路径 |
| `display_name` | TEXT | 否 | `''` | 应用显示名称 |
| `timestamp` | TEXT | 是 | — | 事件发生时间 |
| `duration_seconds` | REAL | 否 | 0 | 持续时长（秒） |
| `screenshot_timestamp` | TEXT | 否 | `''` | 关联截图时间戳 |

### 3.4 browser_history 表 — 浏览器历史

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `id` | INTEGER | PK | 自增 | 主键 |
| `agent_name` | TEXT | 是 | — | 所属 Agent |
| `url` | TEXT | 是 | — | 访问的 URL |
| `title` | TEXT | 否 | `''` | 页面标题 |
| `visit_count` | INTEGER | 否 | 1 | 访问次数 |
| `last_visit` | TEXT | 是 | — | 最后访问时间 |
| `browser` | TEXT | 否 | `'unknown'` | 浏览器类型 |
| `reported_at` | TEXT | 否 | 当前时间 | 上报时间 |

**唯一约束：** `(agent_name, url, last_visit)` + `INSERT OR IGNORE` 去重

### 3.5 diagnostic_logs 表 — 诊断日志

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `id` | INTEGER | PK | 自增 | 主键 |
| `agent_name` | TEXT | 否 | `''` | 所属 Agent |
| `category` | TEXT | 是 | — | 分类（非法值回退 `system`） |
| `level` | TEXT | 否 | `'INFO'` | 级别（非法值回退 `INFO`） |
| `message` | TEXT | 是 | — | 日志内容 |
| `timestamp` | TEXT | 否 | 当前时间 | 记录时间 |

---

## 4. API 端点一览

| # | 方法 | 路径 | 分类 | 功能 |
|---|------|------|------|------|
| 1 | GET | `/api/health` | 健康检查 | 服务健康检测 |
| 2 | POST | `/api/viewer/heartbeat` | 观察者 | Dashboard 观察者心跳 |
| 3 | GET | `/api/config` | 观察者 | Agent 拉取动态配置 |
| 4 | POST | `/api/heartbeat` | 数据接收 | Agent 心跳上报 |
| 5 | POST | `/api/status` | 数据接收 | Agent 状态更新 |
| 6 | POST | `/api/screenshot` | 数据接收 | 接收截图数据 |
| 7 | POST | `/api/app_event` | 数据接收 | 接收应用事件 |
| 8 | POST | `/api/browser_history` | 数据接收 | 接收浏览器历史 |
| 9 | GET | `/api/dashboard/stats` | 统计查询 | 仪表盘统计数据 |
| 10 | GET | `/api/storage/stats` | 存储管理 | 存储使用统计 |
| 11 | POST | `/api/storage/cleanup` | 存储管理 | 清理过期截图 |
| 12 | POST | `/api/diagnostics` | 诊断日志 | Agent 上报诊断信息 |
| 13 | GET | `/api/logs` | 诊断日志 | 查询诊断日志 |
| 14 | GET | `/api/logs/categories` | 诊断日志 | 日志分类及计数 |
| 15 | GET | `/api/agents` | Agent 管理 | Agent 列表 |
| 16 | DELETE | `/api/agents/{agent_name}` | Agent 管理 | 删除 Agent 及关联数据 |
| 17 | PATCH | `/api/agents/{agent_name}` | Agent 管理 | 修改 Agent 显示名称 |
| 18 | GET | `/api/screenshots` | 截图管理 | 截图列表查询 |
| 19 | GET | `/api/screenshots/latest` | 截图管理 | 获取最新截图 |
| 20 | GET | `/api/screenshots/dates` | 截图管理 | 有截图的日期列表 |
| 21 | GET | `/api/screenshots/hours` | 截图管理 | 指定日期的小时列表 |
| 22 | GET | `/api/screenshots/image/{id}` | 截图管理 | 返回截图图片文件 |
| 23 | DELETE | `/api/screenshots/{id}` | 截图管理 | 删除单张截图 |
| 24 | POST | `/api/screenshots/delete-batch` | 截图管理 | 批量删除截图 |
| 25 | GET | `/api/app_usage` | 应用事件 | 应用使用汇总 |
| 26 | GET | `/api/app_events` | 应用事件 | 应用事件时间线 |
| 27 | GET | `/api/browser_history` | 浏览器历史 | 浏览器历史列表 |

---

## 5. 业务规则

### 5.1 截图节流（2 秒窗口）

同一 Agent 的同一显示器在 2 秒窗口内只保留最早的一张截图。

### 5.2 Agent 心跳和在线状态

Agent 上报心跳 → `status = "online"`, `last_seen = 当前时间`。服务端不主动将 Agent 标记为离线。

### 5.3 Viewer 心跳和 LIVE 模式

Dashboard 每秒发送 heartbeat → Agent 拉取 `/api/config` → 距上次 heartbeat < 10 秒返回 `screenshot_interval: 1`（LIVE），否则返回 `5`（正常）。

### 5.4 截图-事件关联

- 应用事件：三级 COALESCE 匹配（精确 → 事后兜底 → 事前兜底）
- 浏览器历史：两级 COALESCE 匹配（事前优先 → 事后兜底）

### 5.5 安全响应头

所有响应附加 `X-Content-Type-Options`、`X-Frame-Options`、`X-XSS-Protection`、`Referrer-Policy`、`Permissions-Policy`、`Content-Security-Policy`。
