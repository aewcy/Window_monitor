# Frontend — Dashboard 前端需求文档

> Vue 3 + Vite + Pinia (`server/dashboard/`), Raycast 风格深色主题

## 架构

```
server/dashboard/
├── src/
│   ├── main.js              # Vue 入口 (createApp + Pinia)
│   ├── App.vue              # 布局: backdrop + 4 窗格 + overlays
│   ├── api.js               # 所有 API 调用 (fetch wrapper)
│   ├── stores/
│   │   ├── agent.js         # Agent 选择/列表
│   │   ├── screenshot.js    # 截图/网格/浏览模式状态
│   │   └── theme.js         # 配色主题
│   ├── composables/
│   │   ├── usePolling.js    # 心跳 + 定时刷新
│   │   └── useConfirm.js    # 确认弹窗
│   ├── components/
│   │   ├── AppHeader.vue    # 顶部栏 (Logo + 模式按钮)
│   │   ├── AgentStrip.vue   # Agent 横向滚动列表
│   │   ├── ScreenshotCard.vue    # 截图卡片 (含放大按钮)
│   │   ├── ScreenshotViewer.vue  # 截图显示 (实时/FPS/显示器切换)
│   │   ├── LiveOverlay.vue       # 70vw 放大叠加层 (实时+浏览模式)
│   │   ├── GridOverlay.vue       # 网格视图叠加层 (80vw)
│   │   ├── TimelineCard.vue      # 活动记录卡片
│   │   ├── BrowserCard.vue       # 浏览器历史卡片
│   │   ├── LogCard.vue           # 系统日志卡片
│   │   ├── StatsBar.vue          # 底部统计浮动栏
│   │   ├── ThemePicker.vue       # 配色选择器 (右下角)
│   │   └── ConfirmDialog.vue     # 确认弹窗
│   └── styles/
│       ├── tokens.css       # 设计令牌
│       └── global.css       # 全局样式
├── vite.config.js           # base: /static/dist/, proxy /api → :8899
└── package.json
```

**构建**: `npm run build` → 输出到 `server/static/dist/`
**开发**: `npm run dev` → `http://localhost:5173/static/dist/` (API 代理到 :8899)

## 页面布局

```
┌─────────────────────────────────────────────────┐
│  Header (Logo + 日历/实时模式/网格视图 按钮)        │
├─────────────────────────────────────────────────┤
│  Agent Strip (横向滚动，点击切换被控端)              │
├──────────────────┬──────────────────────────────┤
│  截图卡片         │  活动记录卡片                   │
│  (放大按钮)       │  (点击→浏览模式 overlay)        │
├──────────────────┼──────────────────────────────┤
│  浏览器历史卡片    │  系统日志卡片                   │
│  (点击→浏览模式)   │                              │
└──────────────────┴──────────────────────────────┘
│  Stats Bar (浮动底部) + Theme Picker (右下角)      │
└─────────────────────────────────────────────────┘
```

## 核心交互

### Agent 选择
- **数据源**: `GET /api/agents`
- **行为**: 点击 Agent 贴片 → 设置 `selectedAgent` → 触发所有卡片刷新
- **显示**: display_name 优先、在线/离线状态、当前截图间隔
- **重命名**: 双击 Agent 名称 → 输入框 → 回车 → `PATCH /api/agents/{name}`
- **切换时**: 自动退出浏览模式，回到实时

### 截图卡片
- **实时模式**: `GET /api/screenshots/latest?agent=X&monitor=N`
- **FPS 标签**: 右上角显示当前截图间隔 (4fps / 1fps / 1/5s / 1/min)
- **显示器切换**: 多屏时显示芯片，点击切换 `selectedMonitor`
- **放大**: 点击「放大」按钮 → 打开 LiveOverlay (70vw × 70vh)

### LiveOverlay (放大/浏览叠加层)

支持两种模式:

#### 实时模式 (点击「放大」按钮)
- 显示最新截图
- 右上角 Live 绿色指示灯
- 显示 Agent 名称
- 显示显示器切换芯片
- **关闭**: 点击「关闭」/ 点击遮罩 / ESC

#### 浏览模式 (点击活动记录/浏览器历史行)
- 显示关联截图
- 顶部标签: `活动 1/20` 或 `浏览 3/15`
- 底部标题: 完整窗口标题或网页标题
- **上一个/下一个**: 只切换有截图的条目，循环导航
- **实时按钮**: 点击回到实时模式
- **关闭**: 自动回到实时模式

#### 浏览模式交互流程
```
用户点击活动记录行 (有 screenshot_id)
  → ss.browseTimeline(events, idx)  // 进入浏览模式
  → ss.liveOpen = true              // 打开 overlay
  → LiveOverlay 显示:
      顶部: "活动 1/20" + Agent 名称
      中间: 截图
      底部: 窗口标题 + 上一个/下一个
      右上: [实时] [关闭] 按钮

用户点击 [下一个]
  → ss.displayIndex++               // 索引+1
  → currentDisplayItem 更新
  → watcher 触发，加载新截图

用户点击 [关闭] 或 [实时]
  → ss.goLive()                     // 回到实时模式
  → overlay 关闭
```

### 网格视图 (GridOverlay)
- **触发**: 顶部栏「网格视图」按钮 或 `⌘G`
- **叠加层**: 80vw × 75vh
- **内容**: 缩略图网格 (auto-fill, minmax(180px, 1fr))
- **交互**:
  - hover 显示复选框 + 删除按钮
  - 全选 / 批量删除
  - 无限滚动 (滚到底部加载下一批 30 张)
  - 点击缩略图打开 LiveOverlay
  - ESC 关闭

### 活动记录卡片
- **数据源**: `GET /api/app_events?agent=X&limit=20&offset=0&with_screenshots=true`
- **每 5 秒自动刷新**
- **无限加载**: 底部"加载更多"按钮，每次 20 条，显示已加载条数
- **点击行为**: 有 `screenshot_id` 的行可点击 → 打开浏览模式 overlay
- **事件类型**: `窗口`（蓝色标签）/ `聊天`（紫色标签）

### 浏览器历史卡片
- **数据源**: `GET /api/browser_history?agent=X&limit=20&offset=0&with_screenshots=true`
- **每 5 秒自动刷新**
- **无限加载**: 底部"加载更多"按钮，每次 20 条，显示已加载条数
- **点击行为**: 有 `screenshot_id` 的行可点击 → 打开浏览模式 overlay
- **浏览器图标**: Chrome 蓝色 `C` / Edge 蓝色 `E`

### 日历选择器 (CalendarPicker)
- **位置**: 顶栏右侧，日历图标按钮
- **功能**: 按日期/时段筛选历史截图
- **数据源**: `GET /api/screenshots/dates?agent=X` (获取有截图的日期)
- **时段筛选**: `GET /api/screenshots/hours?agent=X&date=YYYY-MM-DD` (获取某天的小时分布)
- **筛选**: 点击日期 → 显示时段按钮 (含截图数量) → 选时段后点"查看" → 加载筛选结果
- **交互**: 有截图的日期带圆点标记，可点击；无数据的日期灰色不可点
- **清除**: 点"清除"按钮恢复实时模式

### 系统日志卡片
- **数据源**: `GET /api/logs?limit=20`
- **每 5 秒自动刷新**
- **级别标签**: 信息(amber) / 警告(amber加深) / 错误(accent红)
- **分类标签**: 网络问题/存储问题/采集异常/系统状态/安全警告/服务端

### Stats Bar
- **数据源**: `GET /api/dashboard/stats?agent=X`
- **显示**: 在线 Agent 数、截图总数、今日事件数、浏览器记录数
- **自动刷新**: 每 5 秒

## 主题系统

### 配色选择器 (ThemePicker)
- **位置**: 右下角浮动 🎨 按钮
- **强调色 (6 种)**: Coral / Electric Blue / Amber / Violet / Emerald / Cyan
- **背景色 (5 种)**: Charcoal / Deep Navy / Pure Black / Slate / Warm Dark
- **可自由组合**: 强调色 × 背景色 = 30 种配色方案
- **存储**: `data-accent` 和 `data-bg` HTML 属性，CSS 变量驱动
- **渐变背景**: 根据强调色动态更新 `.backdrop` 的 radial-gradient

### 设计令牌 (CSS 变量)
```css
--ground     /* 页面底色 */
--surface    /* 卡片背景 (半透明) */
--hairline   /* 边框色 */
--accent     /* 强调色 */
--green      /* 正向/在线 */
--red        /* 负向/错误 */
--amber      /* 警告/数据 */
--blue       /* 信息/链接 */
--purple     /* 聊天/特殊 */
--text       /* 主文字 */
--text-secondary /* 次文字 */
--muted      /* 静默文字 */
```

## 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `⌘L` / `Ctrl+L` | 切换实时/历史模式 |
| `⌘G` / `Ctrl+G` | 打开/关闭网格视图 |
| `⌘R` / `Ctrl+R` | 手动刷新全部 |
| `ESC` | 关闭所有 overlay/面板 |

## 状态管理 (Pinia)

### agent store
```javascript
agents              // Agent 列表
selectedAgent       // 当前 Agent 名称
selectedMonitor     // 显示器索引 (null=全部)
monitorTotal        // 显示器总数
selectedAgentData   // 当前 Agent 完整数据 (computed)
```

### screenshot store
```javascript
liveMode            // true=实时, false=历史
screenshotList      // 历史截图列表
currentIndex        // 历史截图索引

// 浏览模式
displaySource       // 'live' | 'timeline' | 'browser'
displayItems        // 浏览条目列表 (带 screenshot_id + title)
displayIndex        // 当前浏览索引
currentDisplayItem  // 当前条目 (computed)

// 网格视图
gridMode            // 是否打开网格
gridItems           // 网格截图列表
gridSelected        // 选中 ID 集合
gridOffset          // 分页偏移
gridLoading         // 加载中
gridExhausted       // 已加载全部

// Live overlay
liveOpen            // 是否打开放大 overlay
```

## API 端点汇总

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/agents` | GET | Agent 列表 |
| `/api/agents/{name}` | PATCH | 修改显示名称 |
| `/api/screenshots/latest` | GET | 最新截图 |
| `/api/screenshots` | GET | 截图列表（支持 limit/offset/date_from/date_to/monitor） |
| `/api/screenshots/image/{id}` | GET | 截图文件 |
| `/api/screenshots/delete-batch` | POST | 批量删除截图 |
| `/api/screenshots/dates` | GET | 有截图的日期列表及每天数量 |
| `/api/screenshots/hours` | GET | 指定日期内有截图的小时列表及每小时数量 |
| `/api/app_events` | GET | 活动记录 (limit/offset/with_screenshots) |
| `/api/browser_history` | GET | 浏览器历史 (limit/offset/with_screenshots) |
| `/api/logs` | GET | 系统日志 |
| `/api/logs/categories` | GET | 日志分类计数 |
| `/api/dashboard/stats` | GET | 统计数据 |
| `/api/viewer/heartbeat` | POST | 观察者心跳 |

## 已实现功能

- [x] Vue 3 + Vite + Pinia 组件化架构
- [x] Agent 选择 + 重命名
- [x] 实时截图 + FPS 标签
- [x] 多显示器切换
- [x] Live 放大 overlay (70vw)
- [x] 活动记录/浏览器历史 → 浏览模式 overlay (带标题+上下切换)
- [x] 活动记录/浏览器历史无限加载 ("加载更多"按钮)
- [x] 日历日期筛选 (按日期/时段查看历史截图)
- [x] 网格视图 overlay (80vw, 缩略图+全选+批量删除+无限滚动)
- [x] 配色系统 (6 强调色 × 5 背景色)
- [x] 底部统计栏
- [x] 系统日志查看
- [x] 确认弹窗 (删除操作)
- [x] 键盘快捷键 (⌘L / ⌘G / ⌘R / ESC)
- [x] CSP 允许 Google Fonts

## 待实现功能

- [ ] 活动记录筛选 (全部/窗口/聊天)
- [ ] 浏览器历史筛选 (全部/Chrome/Edge)
- [ ] 日志筛选 (级别/分类)
- [ ] 截图下载
- [ ] 历史模式翻页 (上一张/下一张)
- [ ] 配色持久化 (localStorage)
