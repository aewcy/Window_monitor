# monitor-demo 上下文迁移 Prompt

> 将此文件内容粘贴到新对话框，即可恢复本次会话的全部项目上下文。

---

## 项目概览

电脑监控系统 Demo，三组件架构：

```
试验机 (被监控) → 服务器 (中转+存储) → 管理端 (查看)
Agent (Python)    FastAPI Server        Web Dashboard
```

- 仓库: `git@github.com:aewcy/monitor-aewcy.git`，单分支 `main`
- 远程服务器: `192.168.61.133:8899`，部署路径 `/root/monitor-aewcy/server`
- **最新 commit: `dc05a98`** — chore: .gitignore 排除 .agents/ .claude/

### 技术栈

| 层 | 技术 |
|---|---|
| Agent 被控端 | Python 3, mss, pynput, pywin32, psutil, requests, PyInstaller |
| Server 服务端 | Python 3, FastAPI, uvicorn, SQLite (sqlite3), Docker |
| Dashboard 前端 | 原生 HTML/CSS/JS，单文件 ~1490 行，无框架 |
| 数据库 | SQLite，原生 sqlite3 模块，线程本地连接，WAL 模式 |

### 目录结构

```
monitor-demo/
├── agent/
│   ├── main.py            # 主控 (Reporter + 3级自适应频率)
│   ├── config.py          # 被控端配置
│   ├── screen_capture.py  # mss 截图 (JPEG quality=40, max_width=1280)
│   ├── app_tracker.py     # win32gui 窗口追踪
│   ├── browser_history.py # 浏览器历史采集
│   ├── keyboard_monitor.py # pynput 键盘 Enter 监听
│   ├── agent.spec         # PyInstaller 打包规格 (25+ hidden imports)
│   ├── build.bat          # 一键构建 monitor-agent.exe
│   └── requirements.txt
├── server/
│   ├── main.py            # FastAPI 入口 (CORS+CSP+Cache-Control)
│   ├── config.py          # 服务端配置
│   ├── models.py          # SQLite 数据层 (CRUD+截图去重+日期/小时查询)
│   ├── routes.py          # REST API (20+接口)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── static/
│       └── dashboard.html # Web 面板 (~1490行)
└── .gitignore             # 排除 .agents/ .claude/ build/ dist/ server/data/
```

---

## 本次会话全部改动（按时间倒序）

### dc05a98 — chore: .gitignore 排除 .agents/ .claude/
- `.gitignore` 添加 `.agents/` 和 `.claude/`（Claude Code 运行时缓存）
- `CLAUDE.md` 和 `skills-lock.json` 保持可追踪

### d5d0e68 — feat: 网格无限滚动 + 日历直接进网格视图
**这是最大的 Dashboard UX 改动：**
- 日历选日期/小时/All dates → **自动进入网格视图**（不再进单图 HISTORY 模式）
- **网格无限滚动**：滚到距底部 150px 时自动加载下一批（500张/批）
- **不设上限**：一直加载到该日期/小时的全部截图
- ▶ 按钮在网格模式下手动触发加载下一批
- 新增状态变量：`gridOffset`, `gridExhausted`, `gridLoading`, `GRID_BATCH=500`
- 新增函数：`onGridScroll()`, `loadGridBatch(append)`, `resetGridAndLoad()`
- `selectCalendarDate()` / `selectHour()` / `clearCalendarFilter()` 都改用 `resetGridAndLoad()`
- `buildScreenshotUrl()` 新增 `limit` 参数
- `toggleGridView()` 重构，进入网格时调用 `resetGridAndLoad()`
- 网格底部显示状态：`"Loading more..."` / `"— All N screenshots loaded —"`
- `selectAgent()` 和 `refreshAll()` 在网格模式下自动调用 `resetGridAndLoad()`

### b7e1708 — fix: 日历加载竞态 + VIEWER覆盖LIGHT_IDLE
**修复两个 bug：**
1. **日历点日期无图**：`toggleScreenshotMode()` 异步触发 `loadScreenshots()`（无日期过滤），与 `loadScreenshotsForDate()` 竞态。修复：`toggleScreenshotMode(skipLoad)` 新增参数。
2. **闲置后仍 1s 截图**：频率控制器中 VIEWER 检查在 LIGHT_IDLE 之前，Dashboard 开着时 `_server_interval=1` 永远命中。修复：**LIGHT_IDLE 优先级提到 VIEWER 之前**。

### 725a74d — feat: HISTORY模式分页浏览 (◀▶换页)
- ◀▶ 在页内正常前后翻阅
- 到页边界时自动加载上一页/下一页（offset ±2000）
- 显示页码 `[page N]`
- 统一 `loadScreenshotsPage()` / `loadScreenshotsPageOffset()`

### a3fe412 — 调整闲置频率: 1分钟→5s, 5分钟→1分钟
- LIGHT_IDLE_INTERVAL: 60s → 5s
- DEEP_IDLE_INTERVAL: 300s → 60s
- LIGHT_IDLE_THRESHOLD: 1800s → 300s（5分钟即进入深度闲置）

### c16e0b6 — feat: Dashboard轮询对齐被控端频率 + 显示实时FPS
- Agent 心跳携带 `screenshot_interval`
- Server 内存存储并在 `/api/agents` 返回
- Dashboard 自适应轮询：ACTIVE→250ms, VIEWER→1s, IDLE→5s/10s
- Agent 卡片和 Screenshot 面板显示 FPS：⚡4fps/🔵1fps/🟡1/5s/⏳1/min

### 47fdd45 — perf: 截图直接替换(去渐变) + 锁定viewer高度
- LIVE 模式去掉 crossfade 渐变，直接替换 `img.src`
- 首张截图 `onload` 后锁定 viewer box 高度，防布局抖动
- 切换 Agent 时解锁高度

### 11d528c — fix: 日历日期筛选bug修复 + 小时分类选择器
- **修复 date_to bug**：从 `"2026-06-15"` 改为 `"2026-06-15T23:59:59"`（字符串比较问题）
- 新增 `GET /api/screenshots/hours` 端点
- 日历下方新增小时选择器（chip 按钮，带数量角标）

### be0a663 — feat: 截图去重(1fps存储) + 浏览上限提升
- `save_screenshot()` 同一秒内只保留最新一张（4fps采集→≤1fps存储）
- API limit: 200→2000, Grid: 100→500, List: 50→200

### 79f5996 — fix: .dockerignore 修正 data/ 路径
- `server/data/` → `data/`（构建上下文是 server/ 目录）

### 8973f80 — feat: 日历日期浏览 + 三级自适应截图频率
**初始日历功能：**
- `GET /api/screenshots/dates` 端点
- `GET /api/screenshots` 新增 `date_from`/`date_to` 参数
- Dashboard 侧边栏日历组件：月份导航、高亮有数据的日期、Today/All dates 按钮

---

## 当前截图频率策略（最终版）

### Agent 端 — 3 级自适应（agent/main.py:226-262）

```
if 距上次操作 < 1分钟:           → 0.25s  (ACTIVE, 4fps)
elif 闲置 < 5分钟:               → 5s     (LIGHT_IDLE, 每5秒1次)  ← 优先于VIEWER
elif 服务端下发 ≤1.5s (有人看):  → 1s     (VIEWER)
else:                           → 60s    (DEEP_IDLE, 每分1次)
```

- 活动来源：Enter 键（白名单聊天应用）+ 窗口切换。鼠标移动不算活动。
- 事件触发（不等定时器）：窗口切换和 Enter 键立即截图，携带 `screenshot_timestamp` 精确关联。

### 服务端 — 去重 ≤1fps
- `save_screenshot()` 同一秒内只保留最新一张（删旧文件+旧索引→写新）
- Dashboard 每秒 POST `/api/viewer/heartbeat`，服务端据此下发 `screenshot_interval`

### Dashboard 端 — 轮询对齐 + FPS 显示
- Agent 心跳(15s)携带当前 `screenshot_interval` → Server 内存存储 → `/api/agents` 返回
- Dashboard 自适应轮询：ACTIVE→250ms, VIEWER→1s, IDLE→5s/10s
- FPS 显示：Agent 卡片和 Screenshot 面板标题

---

## 当前 API 接口列表

### Agent → Server (POST):
| 接口 | 说明 |
|------|------|
| POST /api/heartbeat | 心跳 + `screenshot_interval` |
| POST /api/status | 上下线 |
| POST /api/screenshot | 截图上报 (base64 JPEG) |
| POST /api/app_event | 应用事件 |
| POST /api/browser_history | 浏览器历史 |

### Agent ← Server (GET):
| 接口 | 说明 |
|------|------|
| GET /api/config?agent=xx | 动态配置（根据 viewer heartbeats 返回 interval） |

### Dashboard → Server (POST):
| 接口 | 说明 |
|------|------|
| POST /api/viewer/heartbeat | 观察者心跳（Dashboard 每秒 ping） |
| POST /api/screenshots/delete-batch | 批量删除 |

### Dashboard ← Server (GET):
| 接口 | 说明 |
|------|------|
| GET /api/health | 健康检查 |
| GET /api/agents | Agent 列表（含 `screenshot_interval`） |
| GET /api/dashboard/stats | 统计 |
| GET /api/screenshots?agent=&limit=&offset=&date_from=&date_to= | 截图列表（支持分页+日期过滤） |
| GET /api/screenshots/latest?agent= | 最新截图 |
| GET /api/screenshots/image/{id} | 截图文件 |
| GET /api/screenshots/dates?agent= | 有截图的日期列表+计数 |
| GET /api/screenshots/hours?agent=&date= | 指定日期的小时列表+计数 |
| GET /api/app_events?agent=&with_screenshots= | 活动时间线 |
| GET /api/app_usage?agent= | 应用使用汇总 |
| GET /api/browser_history?agent=&with_screenshots= | 浏览器历史 |

### DELETE:
| 接口 | 说明 |
|------|------|
| DELETE /api/screenshots/{id} | 删除单张 |

---

## Dashboard 功能全景

### 布局
- 左侧 280px 侧边栏：Stats → Calendar → Hour Selector → Agents
- 右侧内容区：Screenshot 面板 → Activity 时间线 → App Usage 表格 → Browser History 表格
- 侧边栏可折叠

### Screenshot 面板
- **LIVE 模式** (🔴): 自适应轮询，直接替换无渐变，锁高度
- **HISTORY 模式** (📷): 单图浏览，◀▶ 翻页（页内+跨页）
- **GRID 模式** (⊞): 无限滚动，500张/批，不设上限，▶ 手动触发加载
- **日历联动**: 选日期/小时 → 自动进 GRID 模式
- **删除**: 网格复选框多选 + 单张悬停删除 + 确认对话框
- **Modal**: 点击缩略图/时间线条目 → 全屏大图

### 自动刷新
- 轮询间隔：250ms(ACTIVE) / 1s(VIEWER) / 5s(LIGHT_IDLE) / 10s(DEEP_IDLE)
- 全量刷新频率自适应（3-60s）
- Dashboard 每秒发 viewer heartbeat

---

## 被控端 (Agent) 核心设计

### Reporter 上报器
- HTTP POST JSON，重试 3 次，超时 10s
- `screenshot()`, `window()`, `browser()`, `chat_enter()`, `heartbeat()`

### 键盘 Enter 监听
- pynput 钩子线程（<1ms 返回，避免 Windows 300ms 钩子超时）
- 工作者线程出队 → `get_active_window()` → 匹配 `FOREGROUND_WHITELIST`
- 白名单：17 个 Windows + 8 个 Linux 聊天应用

### 打包
- PyInstaller 6.17.0，输出 `agent/dist/monitor-agent.exe` (~61MB)
- 注意：**每次修改 agent 代码后需要重跑构建**

---

## 数据库结构

```sql
agents(id, name UNIQUE, status, last_seen, first_seen, message)
screenshots(id, agent_name, timestamp TEXT, file_path, file_size)
  INDEX: (agent_name, timestamp DESC)
app_events(id, agent_name, event_type, window_title, process_name, 
           process_path, display_name, timestamp, duration_seconds, screenshot_timestamp)
browser_history(id, agent_name, url, title, visit_count, last_visit, browser, reported_at)
  UNIQUE: (agent_name, url, last_visit)
```

### 截图-事件关联策略
- app_events: 精确匹配(screenshot_timestamp) → 事后最近 → 事前最近（3级 COALESCE）
- browser_history: 访前截图 → 访后兜底（2级 COALESCE）

---

## 部署命令

```bash
# 被控端打包
cd agent && pyinstaller --clean --noconfirm agent.spec

# 服务端 (Docker)
cd server && docker compose down && docker compose up -d --build

# 服务端 (裸机)
cd server && pip install -r requirements.txt && python main.py

# Git
git pull origin main
```

---

## 关键配置

- 服务器 IP: `192.168.61.133:8899`
- Agent 默认连接: `agent/config.py` → `SERVER_HOST = "192.168.61.133"`
- 服务端监听: `server/config.py` → `HOST = "0.0.0.0"`, `PORT = 8899`
- 截图质量: JPEG quality=40, max_width=1280
- `.dockerignore` 排除 `data/`（防止截图打入镜像）

---

## 已知注意事项

1. **每次修改 agent 代码需重构建 exe**：`cd agent && pyinstaller --clean --noconfirm agent.spec`
2. **远程服务器部署**：需 `git pull` + `docker compose up -d --build`
3. **磁盘管理**：远程服务器根分区 17G，`docker system prune -af` 回收空间
4. **Dashboard 缓存**：`/` 和 `/static/dashboard.html` 响应添加 `Cache-Control: no-cache, no-store, must-revalidate`
5. **截图去重**：服务端 `save_screenshot()` 同一秒内只保留最新一张
6. **VIEWER 模式不再覆盖 LIGHT_IDLE**：LIGHT_IDLE(5s) 优先于 VIEWER(1s)
