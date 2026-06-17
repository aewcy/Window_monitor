# Frontend — Dashboard 前端需求文档

> Raycast 风格监控面板 (`server/static/dashboard-v0-raycast.html`)

## 架构

单文件 SPA，原生 HTML/CSS/JS，无框架、无构建步骤。所有 API 交互通过 `fetch` 完成。

```
┌─────────────────────────────────────────────────┐
│  Header (实时模式/网格/刷新)                       │
├─────────────────────────────────────────────────┤
│  Agent Strip (横向滚动，点击切换被控端)              │
├──────────────────┬──────────────────────────────┤
│  截图卡片         │  活动记录卡片                   │
│  (实时/历史/网格)  │  (窗口切换 + 聊天Enter)        │
├──────────────────┼──────────────────────────────┤
│  浏览器历史卡片    │  系统日志卡片                   │
│                  │                              │
└──────────────────┴──────────────────────────────┘
│  Stats Bar (浮动底部) + Theme Picker (右下角)      │
└─────────────────────────────────────────────────┘
```

## 核心交互

### Agent 选择
- **数据源**: `GET /api/agents`
- **行为**: 点击 Agent 贴片 → 设置 `selectedAgent` → 触发所有卡片刷新
- **显示**: 名称（display_name 优先）、在线/离线状态、当前截图间隔
- **重命名**: 双击 Agent 名称 → 变为输入框 → 回车提交 → `PATCH /api/agents/{name}`

### 截图卡片
- **实时模式**: `GET /api/screenshots/latest?agent=X&monitor=N`，每秒刷新
- **历史模式**: `GET /api/screenshots?agent=X&limit=50&monitor=N`，翻页浏览
- **显示器切换**: 多屏时显示芯片，点击切换 `selectedMonitor`
- **放大视图**: 点击「放大」按钮打开 70vw 全屏叠加层
- **关联截图**: 活动记录/浏览器历史点击时，调用 `showScreenshotById(id)` 显示关联截图

#### 关联截图流程
```
用户点击活动记录行 → onTimelineClick(el)
  → 读取 data-screenshot-id
  → showScreenshotById(id)
  → 更新截图卡片 img.src = /api/screenshots/image/{id}
  → 同步更新放大视图
```

### 活动记录卡片
- **数据源**: `GET /api/app_events?agent=X&limit=20&with_screenshots=true`
- **每 5 秒自动刷新**
- **点击行为**: 点击行 → 高亮该行 → 显示关联截图
- **事件类型**: `窗口`（蓝色标签）/ `聊天`（紫色标签）
- **关联截图**: API 返回 `screenshot_id` 字段，存于行的 `data-screenshot-id` 属性

### 浏览器历史卡片
- **数据源**: `GET /api/browser_history?agent=X&limit=20&with_screenshots=true`
- **每 5 秒自动刷新**
- **点击行为**: 点击行 → 高亮该行 → 显示关联截图
- **浏览器图标**: Chrome 蓝色 `C` / Edge 蓝色 `E`
- **关联截图**: 同活动记录

### 系统日志卡片
- **数据源**: `GET /api/logs?limit=20`
- **每 5 秒自动刷新**
- **级别**: 信息(amber) / 警告(amber加深) / 错误(accent红)

### Stats Bar
- **数据源**: `GET /api/dashboard/stats?agent=X`
- **显示**: 在线 Agent 数、截图总数、今日事件数、浏览器记录数

## 实时通信

### Viewer Heartbeat
```
每秒 POST /api/viewer/heartbeat
  → 服务端记录 _viewer_last_seen
  → Agent 轮询 /api/config 时检测到观察者
  → Agent 切换到 1s LIVE 模式
```

### 自动刷新策略
| 数据 | 刷新间隔 | 说明 |
|------|---------|------|
| 截图 | 1s | 实时模式下 |
| 活动记录 | 5s | 始终 |
| 浏览器历史 | 5s | 始终 |
| 系统日志 | 5s | 始终 |
| 统计 | 5s | 始终 |
| Agent 列表 | 初始加载 | 手动刷新时更新 |

## 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `⌘L` / `Ctrl+L` | 切换实时/历史模式 |
| `⌘G` / `Ctrl+G` | 网格视图（预留） |
| `⌘R` / `Ctrl+R` | 手动刷新全部 |
| `Esc` | 关闭放大/主题面板 |

## 主题系统

- **强调色**: Coral / Electric Blue / Amber / Violet / Emerald / Cyan
- **背景色**: Charcoal / Deep Navy / Pure Black / Slate / Warm Dark
- **存储**: `data-accent` 和 `data-bg` 属性，CSS 变量驱动
- **渐变背景**: 根据强调色动态更新 `.backdrop` 的 radial-gradient

## 状态管理

```javascript
selectedAgent      // 当前选中的 Agent 名称
selectedMonitor    // 当前选中的显示器索引 (null=全部)
monitorTotal       // 当前 Agent 的显示器总数
liveMode           // true=实时刷新, false=历史浏览
screenshotList     // 历史截图列表
currentScreenshotIndex  // 历史截图当前索引
```

## API 端点汇总

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/agents` | GET | Agent 列表 |
| `/api/agents/{name}` | PATCH | 修改显示名称 |
| `/api/screenshots/latest` | GET | 最新截图 |
| `/api/screenshots` | GET | 截图列表（历史） |
| `/api/screenshots/image/{id}` | GET | 截图文件 |
| `/api/app_events` | GET | 活动记录（含截图关联） |
| `/api/browser_history` | GET | 浏览器历史（含截图关联） |
| `/api/logs` | GET | 系统日志 |
| `/api/dashboard/stats` | GET | 统计数据 |
| `/api/viewer/heartbeat` | POST | 观察者心跳 |

## 待实现功能

- [ ] 网格视图（缩略图网格浏览）
- [ ] 截图历史翻页（上一张/下一张）
- [ ] 活动记录筛选（全部/窗口/聊天）
- [ ] 浏览器历史筛选（全部/Chrome/Edge）
- [ ] 日志筛选（级别/分类）
- [ ] 截图下载
- [ ] 暗色/亮色主题切换
