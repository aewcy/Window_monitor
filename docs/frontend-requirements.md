# 前端需求规格文档

> 基于 `server/dashboard/src/` 源码提取。
> 最后更新: 2026-06-20

---

## 目录

1. [技术栈](#1-技术栈)
2. [页面布局](#2-页面布局)
3. [组件清单](#3-组件清单)
4. [状态管理（Pinia Stores）](#4-状态管理)
5. [API 调用](#5-api-调用)
6. [交互行为](#6-交互行为)

---

## 1. 技术栈

- **框架：** Vue 3 (Composition API)
- **构建：** Vite，base 为 `/static/dist/`，`/api` 代理到 `:8899`
- **状态管理：** Pinia
- **样式：** CSS 变量设计令牌（`tokens.css`），Raycast 风格深色主题
- **输出：** 构建产物输出到 `server/static/dist/`

---

## 2. 页面布局

### 2.1 主界面（App.vue）

```
┌─────────────────────────────────────────────┐
│ AppHeader（logo + AgentStrip + 主题按钮）     │
├───────────┬───────────┬─────────────────────┤
│ 活动记录   │ 浏览器历史  │ 实时截图             │
│ LogCard   │ BrowserCard│ ScreenshotViewer    │
├───────────┴───────────┴─────────────────────┤
│ StatsBar（全局统计）                          │
└─────────────────────────────────────────────┘
```

- **背景：** 毛玻璃效果 `backdrop-filter: blur(40px)` + 网格线
- **响应式：** 移动端自动堆叠

### 2.2 叠加层

| 叠加层 | 触发方式 | 内容 |
|--------|---------|------|
| `LiveOverlay` | 点击截图放大按钮 | 70vw×70vh 大图预览，支持实时/浏览/历史模式 |
| `GridOverlay` | 点击"网格视图"按钮 | 网格布局，按日期分组，双击进入 overlay |
| `ThemePicker` | 点击主题按钮 | 主题色选择器 |
| `ConfirmDialog` | 删除操作 | 确认对话框 |

---

## 3. 组件清单

### 3.1 AppHeader

- 显示 logo + 标题
- 包含 `AgentStrip` 组件
- 右侧：网格视图按钮 + 主题按钮

### 3.2 AgentStrip

- 水平展示所有 Agent 卡片
- 显示：名称、状态指示灯（绿=在线/灰=离线）、截图间隔
- 点击切换选中 Agent
- **验证：** Agent 列表正确显示，选中状态切换

### 3.3 ScreenshotViewer（嵌入卡片）

- 显示当前选中 Agent 的最新截图
- 标题栏：Agent 名称 + 监控器标签 + FPS 徽章 + 时间戳
- FPS 徽章规则：
  - `interval <= 0.3` → "4fps"
  - `interval <= 1.5` → "1fps"
  - `interval <= 6` → "1/5s"
  - `interval <= 60` → "1/min"
  - 否则 → "sleep"
- **验证：** 截图加载、FPS 徽章显示正确

### 3.4 LiveOverlay（全屏叠加层）

- 尺寸：`70vw × 70vh`
- 三种模式：
  - **实时模式：** 自动刷新最新截图
  - **浏览模式：** 显示活动记录/浏览器历史关联的截图，支持上一张/下一张
  - **历史模式：** 显示网格选中的截图，支持上一张/下一张
- 功能：
  - 滚轮切换图片（上一张/下一张）
  - Ctrl+滚轮缩放（30%~300%）
  - 标题显示：Agent 名 + 来源 + 序号
  - 关闭时：历史模式回到网格，实时模式恢复 live
- **验证：** 模式切换、滚轮导航、缩放、ESC 关闭

### 3.5 GridOverlay（网格叠加层）

- 全屏网格布局展示截图
- 按日期分组，粘性日期标题
- 每个卡片显示：缩略图 + 时间（HH:MM:SS）+ 监控器标签
- 双击卡片进入 LiveOverlay 浏览模式
- 支持多选删除
- **验证：** 日期分组、时间精度、双击打开

### 3.6 LogCard

- 展示诊断日志（`/api/logs`）
- 每 10 秒轮询刷新
- 日志级别颜色标记（ERROR=红, WARNING=黄, INFO=蓝, DEBUG=灰）
- **验证：** 日志列表显示、级别颜色

### 3.7 BrowserCard

- 展示浏览器历史（`/api/browser_history`）
- 支持分页加载（offset 递增）
- 点击记录 → 进入浏览模式在 overlay 中显示关联截图
- **验证：** 分页加载、点击查看截图

### 3.8 ActivityCard

- 展示应用事件时间线（`/api/app_events`）
- 支持分页加载
- 点击事件 → 进入浏览模式显示关联截图
- **验证：** 分页加载、点击查看截图

### 3.9 StatsBar

- 显示全局统计：截图总数、今日事件、浏览器记录、在线 Agent 数
- **验证：** 数值正确显示

### 3.10 CalendarPicker

- 日历面板，选择日期 + 小时筛选
- 调用 `getScreenshotDates` 获取有数据的日期
- 选择日期后调用 `getScreenshotHours` 获取小时分布
- 应用筛选后加载截图到网格视图
- 日期格式使用 T 分隔符：`${date}T${hour}:00:00`
- **验证：** 日期选择、小时筛选、数据加载

### 3.11 ThemePicker

- 主题色选择器
- 切换 CSS 变量实现主题变更
- 持久化到 localStorage
- **验证：** 主题切换、持久化

### 3.12 ConfirmDialog

- 通用确认对话框
- 支持自定义标题、消息、确认/取消按钮文本
- **验证：** 显示、确认/取消回调

---

## 4. 状态管理

### 4.1 agent store（`stores/agent.js`）

| 状态 | 类型 | 说明 |
|------|------|------|
| `agents` | `array` | Agent 列表 |
| `selectedAgent` | `string` | 当前选中的 Agent 名称 |
| `selectedDisplayName` | `string` | 当前选中 Agent 的显示名称 |
| `viewerActive` | `boolean` | 观察者是否活跃 |

**Actions：** `fetchAgents()` / `selectAgent(name)` / `startPolling()` / `stopPolling()`

### 4.2 screenshot store（`stores/screenshot.js`）

| 状态 | 类型 | 说明 |
|------|------|------|
| `screenshotList` | `array` | 实时截图列表 |
| `currentIndex` | `number` | 当前显示索引 |
| `liveMode` | `boolean` | 是否实时模式 |
| `liveOpen` | `boolean` | overlay 是否打开 |
| `gridMode` | `boolean` | 网格模式 |
| `gridItems` | `array` | 网格数据 |
| `displaySource` | `string` | 显示来源（live/browse/history） |
| `displayItems` | `array` | 当前显示列表 |
| `displayIndex` | `number` | 当前显示索引 |

**Actions：** `fetchLatest()` / `goLive()` / `browseTimeline(items, index)` / `browseBrowser(items, index)` / `enterHistory(items, index)` / `prev()` / `next()` / `closeOverlay()`

### 4.3 theme store（`stores/theme.js`）

| 状态 | 类型 | 说明 |
|------|------|------|
| `themeColor` | `string` | 当前主题色 |

**Actions：** `setThemeColor(color)` / `loadTheme()`

---

## 5. API 调用

所有 API 调用封装在 `api.js` 中，使用 `fetch` + JSON 解析。

| 函数 | 端点 | 用途 |
|------|------|------|
| `getAgents()` | `GET /api/agents` | 获取 Agent 列表 |
| `renameAgent(name, displayName)` | `PATCH /api/agents/{name}` | 修改显示名称 |
| `getLatestScreenshot(agent, monitor)` | `GET /api/screenshots/latest` | 获取最新截图 |
| `getScreenshots(agent, limit, offset, monitor, dateFrom, dateTo)` | `GET /api/screenshots` | 查询截图列表 |
| `getScreenshotImage(id)` | `GET /api/screenshots/image/{id}` | 获取截图图片 URL |
| `deleteScreenshots(ids)` | `POST /api/screenshots/delete-batch` | 批量删除截图 |
| `getAppEvents(agent, limit, offset)` | `GET /api/app_events` | 获取应用事件 |
| `getBrowserHistory(agent, limit, offset)` | `GET /api/browser_history` | 获取浏览器历史 |
| `getScreenshotDates(agent)` | `GET /api/screenshots/dates` | 获取有截图的日期 |
| `getScreenshotHours(agent, date)` | `GET /api/screenshots/hours` | 获取小时分布 |
| `getLogs(limit)` | `GET /api/logs` | 获取诊断日志 |
| `getStats(agent)` | `GET /api/dashboard/stats` | 获取统计数据 |
| `sendHeartbeat()` | `POST /api/viewer/heartbeat` | 观察者心跳 |

---

## 6. 交互行为

### 6.1 ESC 键退出（分层）

1. LiveOverlay 打开 → ESC 关闭 overlay
2. GridOverlay 打开 → ESC 关闭网格
3. ThemePicker 打开 → ESC 关闭主题面板

使用 `document.addEventListener('keydown')` 全局监听。

### 6.2 滚轮导航（LiveOverlay）

- 滚轮上/下 → 上一张/下一张
- Ctrl+滚轮 → 缩放图片（30%~300%，步长 10%）
- `e.preventDefault()` 阻止页面滚动

### 6.3 日历筛选流程

1. 点击日历按钮 → 打开 CalendarPicker 面板
2. 调用 `getScreenshotDates` 高亮有数据的日期
3. 选择日期 → 调用 `getScreenshotHours` 显示小时分布
4. 选择小时 → 调用 `getScreenshots(dateFrom, dateTo)` 加载数据
5. 数据加载到 `ss.gridItems`，打开网格视图

### 6.4 观察者心跳

- `usePolling` composable 每秒调用 `sendHeartbeat()`
- 仅在页面可见时发送（`document.visibilityState === 'visible'`）
- 同时每 5 秒刷新 Agent 列表和最新截图

### 6.5 分页加载

- 活动记录和浏览器历史支持无限滚动加载
- 每次加载 `limit` 条，`offset` 递增
- 滚动到底部自动加载下一页
