# Implementation Notes

## 2026-07-07 Web 登录改为标签页级会话

### 背景

- 目标：用户关闭当前标签页后，再重新打开 Web 或下载页时，必须重新输入密码。
- 原实现只有 `crkrd_session` cookie，登录态可跨标签页复用，不符合产品要求。

### 实现方案

- 服务端登录成功后，仍然签发 `HttpOnly` cookie。
- 但 cookie 内额外绑定当前标签页生成的 `tab_token` 哈希。
- Dashboard 和下载页在当前标签页的 `sessionStorage` 中保存 `crkrd_tab_session`。
- Web API 请求统一通过请求头 `X-CRKRD-Tab-Session` 传递当前标签页 token。
- 图片、缩略图、预览图、安装包下载这类不能自定义请求头的入口，统一改为通过 URL 参数 `tab_session` 传递 token。

### 涉及文件

- `server/main.py`
- `server/dashboard/src/api.js`
- `server/dashboard/src/components/AgentStrip.vue`
- `server/static/download.html`
- `server/tests/test_api.py`

### 边缘情况与偏离说明

- 偏离点：浏览器首次请求 HTML 页面时，天然不能像 `fetch` 一样附带自定义请求头。
- 处理方式：服务端页面入口仍先基于 cookie 放行 HTML，但会在返回的页面里注入标签页守卫脚本。
- 结果：如果用户是重新新开一个标签页，虽然浏览器还会带旧 cookie，但由于这个新标签页没有 `sessionStorage` 里的 token，页面加载后会立即跳回登录页。
- 说明：最终用户效果满足“关掉标签页后重新打开必须重登”，只是呈现形式不是服务端首包直接拦截，而是页面加载后立即回登录页。
- 部署偏离点：通过 Paramiko 拉取远端 `docker compose` 输出时，日志中包含 `✓` 等字符，本地 Windows Python 默认 `gbk` 输出会抛 `UnicodeEncodeError`。
- 部署处理：远端继续把完整构建日志写入 `/tmp/monitor-build.log`，本地只读取并做 `ascii` 安全降级输出，不让编码问题中断部署流程。
- 部署偏离点：`docker compose up -d --build` 完成后，容器刚重建切换的短时间内，`curl http://127.0.0.1:8899/api/health` 可能返回 `Connection reset by peer`。
- 部署处理：把健康检查改为短间隔重试，等容器真正进入稳定监听态后再继续做登录和版本验收。

### 验证

- `D:\python\python.exe -m pytest server\tests\test_api.py -q`
- `npm run build`

## 2026-07-07 仓库清理规则收敛

### 目标

- Git 仓库只保留项目运行、构建、发布、测试、正式文档需要的内容。
- 本地 AI 工具配置、协作过程文件、缓存、动态测试残留不进入版本库。

### 本次处理

- 从版本库移除 `CLAUDE.md`。
- 从版本库移除 `docs/superpowers/` 下的 AI 过程计划/设计文档。
- `.gitignore` 增加 `docs/superpowers/`，避免后续再次误提交。

### 判断原则

- `agent/`、`server/`、`installer/`、核心 `docs/`、测试、发布链路真实依赖的静态包保留。
- AI 工具说明、代理运行目录、缓存、日志、动态测试产物不保留。

## 2026-07-07 本地目录清理与结构收口

### 目标

- 删除不再使用的源码启动入口、图标参考目录、动态测试残留和本地工具目录。
- 保留当前实际运行链路：`agent/` 源码、`server/` 服务端、`installer/` 安装器、`server/static/agent/` 发布包、`server/static/dist/` 当前 Dashboard 构建产物。

### 本次处理

- 从版本库移除 `agent/start.bat`，后续不再支持双击源码脚本启动 Agent。
- 从版本库移除 `server/static/dashboard.html` 与 `server/static/dashboard-v0.html`，只保留 `server/static/dashboard-v0-raycast.html` 作为旧版回退页。
- 删除本地 AI 工具目录、PyInstaller 中间目录、pytest 缓存、动态测试数据库、动态测试日志、图标参考目录。
- `.gitignore` 增加动态测试残留与本地图标参考目录规则，避免再次回流。

### 结果

- 仓库根目录只保留项目本体、正式文档、构建/发布链路相关内容。
- `agent/` 不再混入“源码双击启动”入口，职责更聚焦在源码、打包和安装更新脚本。
- `server/static/` 收敛为“当前构建产物 + 保留一个旧版回退页”的结构。

## 2026-07-07 特殊名单截图策略

### 目标

- 保持普通程序/网页的历史截图保存逻辑不变。
- 对“低价值长驻前台内容”增加特殊名单：
  - 切到前台后的前 10 秒仍按原策略正常保存。
  - 超过 10 秒后，只保留 Live，不再持续写入历史。
  - 同一前台会话每 5 分钟补 1 张历史截图，避免完全断档。
- 特殊名单只影响历史保存，不影响 Live。

### 实现方案

- Server 新增 `screenshot_rules` 表，支持两类规则：
  - `process`：按前台程序名精确匹配
  - `url_contains`：按前台完整 URL 连续模糊匹配
- Agent 在 `/api/config` 中拉取特殊名单、预热时长、补帧时长。
- Agent 新增 `ForegroundSavePolicy`：
  - 非名单对象：`store_history=true`
  - 名单对象前 10 秒：`save_policy_phase=warmup`
  - 超过 10 秒：`save_policy_phase=suppressed`
  - 满 5 分钟：`save_policy_phase=keepalive`
- `/api/screenshot` 继续先写 Live 内存帧，再根据 `store_history` 决定是否调用 `save_screenshot(...)`。
- 截图索引额外记录：
  - `foreground_process_name`
  - `foreground_window_title`
  - `foreground_url`
  - `matched_rule_type`
  - `matched_rule_pattern`
  - `save_policy_phase`
- Dashboard 顶部 Header 增加“特殊名单”面板，可直接维护程序和网页规则。

### 涉及文件

- `agent/foreground_context.py`
- `agent/main.py`
- `agent/tests/test_foreground_policy.py`
- `server/models.py`
- `server/routes.py`
- `server/tests/test_api.py`
- `server/dashboard/src/api.js`
- `server/dashboard/src/App.vue`
- `server/dashboard/src/components/AppHeader.vue`
- `server/dashboard/src/components/ScreenshotRulePanel.vue`
- `server/dashboard/src/stores/screenshot.js`

### 边缘情况与偏离说明

- 偏离点：当前仓库原本只具备“浏览器历史采集”，没有“当前最前台标签页完整 URL”能力。
- 当前处理：新增前台 URL 最佳努力解析，基于浏览器近期历史 + 当前窗口标题做匹配推断。
- 影响：网页规则不是浏览器内核级精确读当前标签页，极端场景下可能拿不到 URL，此时网页规则不会命中，历史保存回到普通策略。
- 明确保留：没有把 URL 获取失败退化成窗口标题规则，避免误杀正常历史保存。
- 后续修正：历史保存策略主判断迁到 Server，旧 Agent 即使不上传 `store_history`，Server 也会基于最近 `app_switch` 和浏览器历史记录判断是否入库。
- 兼容策略：新版 Agent 上传的前台字段仍作为更准的上下文；旧 Agent 先通过最近活动事件兜底，网页 URL 规则通过最近浏览器历史弱匹配。
- 明确边界：Live 始终先写内存帧，特殊名单只影响历史落盘。

### 验证

- `D:\python\python.exe -m pytest server\tests\test_api.py -q`
- `D:\python\python.exe -m pytest agent\tests\test_foreground_policy.py -q`
- `D:\python\python.exe -m py_compile agent\main.py agent\foreground_context.py server\routes.py server\models.py`
- `npm run build`

## 2026-07-07 Agent 免重构发布与后台推送更新

### 目标

- 后续发布 `monitor-agent.exe` / `WindowsMonitorSetup.exe` 时，不再依赖重构 Server 镜像。
- 下载页和 Web 后台推送更新都读取同一个“当前激活版本”。
- 更新任务创建后绑定具体 `target_version`，避免激活版本后续切换导致下载包漂移。

### 实现方案

- `docker-compose.yml` 新增 `../releases/agent:/app/releases/agent` 挂载。
- 发布目录约定为 `/app/releases/agent/{version}/`：
  - `monitor-agent.exe`
  - `WindowsMonitorSetup.exe`
- 复用 `agent_versions` 表作为发布版本清单。
- `is_active=1` 表示当前激活版本，激活操作会先清空其他版本的激活状态。
- 新增发布管理接口：
  - `POST /api/agent/versions/register`
  - `POST /api/agent/versions/{version}/activate`
- `/api/agent/version`、`/api/agent/download`、`/api/agent/exe` 默认读取当前激活版本。
- `/api/agent/packages/{version}/exe|setup` 按指定版本目录读取文件。
- `/api/updater/jobs/next` 按 job 的 `target_version` 返回版本包元数据，不再返回当前 latest。

### 冗余与兼容设计

- 保留 `server/static/agent` 旧包作为 `0.59.0` 兜底版本。
- 如果 releases 目录还没有注册版本，服务端会自动注册旧静态包，并在没有激活版本时激活它。
- 注册版本时由服务端读取文件并计算 sha256/size，避免人工填写错误。
- 激活版本前会校验 exe/setup 文件都存在。
- 旧接口 `/api/agent/exe`、`/api/agent/download` 保留，继续服务下载页和旧更新入口。

### 后续发布流程

- 本地构建 Agent exe 和安装器。
- 上传到服务器 `/root/monitor-aewcy/releases/agent/{version}/`。
- 调用 `POST /api/agent/versions/register` 注册版本。
- 调用 `POST /api/agent/versions/{version}/activate` 激活版本。
- Web 点“允许更新”后，后台更新任务默认推送当前激活版本。

### 验证

- `D:\python\python.exe -m pytest server\tests\test_api.py -q`
- `D:\python\python.exe -m py_compile server\routes.py server\models.py`
