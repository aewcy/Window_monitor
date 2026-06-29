# 后端需求规格文档

> 基于 `server/routes.py`、`server/models.py`、`server/main.py`、`server/config.py` 源码提取。
> 最后更新: 2026-06-28

---

## 目录

1. [系统概述](#1-系统概述)
2. [配置项](#2-配置项)
3. [数据模型](#3-数据模型)
4. [API 端点一览](#4-api-端点一览)
5. [API 端点详细规格](#5-api-端点详细规格)
6. [业务规则](#6-业务规则)
7. [Agent 更新与冗余需求](#7-agent-更新与冗余需求)

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

Dashboard 每秒发送 heartbeat → Agent 每 3 秒拉取 `/api/config` → 距上次 heartbeat < 10 秒返回 `screenshot_interval: 1`（LIVE），否则返回 `5`（普通观察状态）。

Agent 收到服务端间隔后不会机械照搬，而是交给本地自适应频率控制器裁决：

| 状态 | 间隔 | 条件 |
|------|------|------|
| ACTIVE | 0.25s | 本机 1 分钟内有操作，或窗口切换、聊天应用 Enter 触发活动 |
| LIGHT_IDLE | 10s | 本机空闲 1-5 分钟 |
| DEEP_IDLE | 60s | 本机空闲 5-30 分钟 |
| VERY_DEEP_IDLE | 600s | 本机空闲 30 分钟以上 |

Windows 被控机的“空闲时长”基于系统最后一次键鼠输入时间计算，不以 Agent 进程启动时刻为起点。因此，若部署脚本执行前桌面已经闲置，Agent 启动后可以直接落在 `LIGHT_IDLE` / `DEEP_IDLE` / `VERY_DEEP_IDLE`，这不是策略跳错，而是空闲基线更早。

Live 画面读取 Agent 最近一次上传的内存帧，刷新频率跟随 Agent 实际上传频率；截图入库是独立策略。

服务端仅对入库存储执行节流：同一 Agent、同一显示器在 2 秒窗口内只保留最早截图，避免 ACTIVE 高频采集造成存储暴涨。10 秒及以上的空闲策略本身慢于 2 秒，不受该节流影响。

### 5.4 截图-事件关联

- 应用事件：三级 COALESCE 匹配（精确 → 事后兜底 → 事前兜底）
- 浏览器历史：两级 COALESCE 匹配（事前优先 → 事后兜底）

### 5.5 安全响应头

所有响应附加 `X-Content-Type-Options`、`X-Frame-Options`、`X-XSS-Protection`、`Referrer-Policy`、`Permissions-Policy`、`Content-Security-Policy`。

---

## 7. Agent 更新与冗余需求

> 本节为后续开发需求，目标是在已有被控机在线使用时，支持低风险、可回滚的后台更新。

### 7.1 版本发布

服务端需要维护 Agent 可用版本信息，至少包含：

| 字段 | 说明 |
|------|------|
| `version` | 版本号，例如 `v0.42` |
| `download_url` | Agent 安装包或可执行文件下载地址 |
| `sha256` | 文件 SHA256，用于 Agent 下载后校验 |
| `size_bytes` | 文件大小 |
| `released_at` | 发布时间 |
| `release_notes` | 更新说明 |
| `force_update` | 是否强制更新，默认不强制 |
| `stable` | 是否稳定版 |

服务端必须保留历史版本，不能只覆盖最新版，便于回滚和人工排查。

### 7.2 Agent 上报版本状态

Agent 心跳或状态上报需要包含：

- 当前运行版本
- 最近一次检查更新的时间
- 更新状态：`idle` / `checking` / `downloading` / `installing` / `updated` / `failed` / `rolled_back`
- 更新失败原因
- 最近一次成功更新版本

服务端保存这些字段后，供前端展示和筛选。

### 7.3 更新检查策略

更新采用 Agent 主动拉取模式：

- Agent 定时请求服务端版本接口。
- 默认只检查，不自动安装。
- 服务端或前端给指定 Agent 下发“允许更新”后，该 Agent 才下载并安装。
- 不采用所有 Agent 同时更新的策略。

### 7.4 单机更新流程

单台 Agent 的更新流程必须满足：

1. 下载新版本到临时目录。
2. 校验 SHA256。
3. 备份当前版本为 previous。
4. 由独立 updater 执行替换，避免正在运行的进程覆盖自身。
5. 启动新版本 Agent。
6. 新版本成功心跳后，标记更新成功。
7. 新版本启动失败或超时未心跳时，恢复 previous 并上报回滚状态。

### 7.5 灰度和冗余规则

考虑当前已有多台被控机部署，服务端需要支持灰度更新：

- 默认一次最多允许 1 台 Agent 处于 `installing` 状态。
- 第一台更新成功并稳定观察一段时间后，才允许继续更新下一台。
- 支持按 Agent 名称单独允许更新。
- 支持暂停某台 Agent 的更新。
- 任意 Agent 更新失败后，自动停止本批次后续更新。

### 7.6 权限和安装目录约束

首次安装可以要求管理员权限，用于写入安装目录、创建计划任务和设置目录权限。

后续静默更新应优先复用首次安装时配置好的权限，避免每次更新都要求人工操作。当前项目更依赖用户桌面会话截图，不应把主 Agent 设计成纯 Session 0 服务模式。
