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
- 再修正：网页 URL 规则不再只看 120 秒内浏览器历史；当前台是浏览器时，会在较长历史窗口内按 URL 规则反查，覆盖 TradingView 这类页面长期打开但历史不刷新的场景。
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

## 2026-07-08 Live 不再强制提高截图频率

### 目标

- Live 只显示 Agent 按截图策略上传来的画面。
- Web 正在观看 Live 时，不再反向强制 Agent 进入 1 秒截图。
- 长时间无操作后，截图策略继续按 Agent 空闲阈值降到 10 秒、60 秒、600 秒。

### 实现方案

- `/api/config` 不再根据 `/api/viewer/heartbeat` 返回 1 秒截图间隔，统一返回基础 `5` 秒配置。
- `/api/viewer/heartbeat` 保留为兼容接口，但不参与截图频率决策。
- Agent `resolve_screenshot_strategy` 删除 `VIEWER` 覆盖分支，`server_interval` 仅作为兼容入参保留。
- Dashboard 的 Live 卡片和 Live 放大层停止发送 viewer heartbeat，避免无意义请求。

### 边缘情况与偏离说明

- 偏离点：旧实现把“有人看 Live”当成强制提频信号；现在改为“Live 被动显示当前策略帧”。
- 影响：长空闲时 Live 刷新会变慢，这是节省存储和按策略截图的预期结果。
- 兼容：旧 Agent 即使还带 `VIEWER` 分支，只要服务端不再返回 `1` 秒，也不会被 Web 观看拉高频。

### 0.59.1 Agent 发布包

- 版本：`0.59.1`
- `monitor-agent.exe` size：`56658809`
- `monitor-agent.exe` sha256：`30D92E546C88780887F58EA8CD667067AE4BA8C7DF9DAC525B7ADC074813DDA4`
- `WindowsMonitorSetup.exe` size：`58020316`
- `WindowsMonitorSetup.exe` sha256：`CAA063AB95A05CE82C7DFE1D7E0D6906ED77D6F8D187EE81B4B21C92344A4B8C`
- 发布目的：让后台推送更新后的客户端也删除 `VIEWER` 强制提频分支。

## 2026-07-08 图片上下文信息角

### 目标

- 在单张大图查看时，能直接查看该截图对应的网页 URL、前台程序、窗口标题和保存策略信息。
- 默认不遮挡图片，只在右下角显示一个小三角，点击后展开信息卡。

### 实现方案

- 网格单图预览读取 `previewItem` 中的 `foreground_url`、`foreground_process_name`、`foreground_window_title`、`matched_rule_*`、`save_policy_phase` 字段。
- Live 放大层读取当前 live 帧字段；历史浏览模式回退读取活动/浏览器历史条目中的标题和 URL。
- URL 支持一键复制，长 URL 自动换行，避免撑破面板。

### 边缘情况与偏离说明

- 旧截图没有 URL 或前台字段时，信息卡只显示已有字段，不额外伪造。
- 活动记录进入大图时，如果只拿到 `process_name/window_title`，会先显示这些字段；完整截图字段以后可通过详情接口补强。

## 2026-07-17 特殊名单类型选择菜单

### 目标

- 让“程序名 / 网页 URL”类型选择器与历史截图特殊名单面板保持统一的深色视觉，不再出现浏览器默认的白色下拉菜单。

### 实现方案

- `ScreenshotRulePanel.vue` 将原生 `select` 替换为组件内自定义菜单，仍使用原来的 `formType` 值和新增规则接口。
- 菜单显示当前类型、匹配方式说明和已选状态；点击空白处、按 `Escape` 或选中项目都会关闭。
- 补充焦点样式、`listbox` / `option` 语义和下方向键展开，保留键盘可用性。

### 边缘情况与偏离说明

- 偏离点：不再使用系统原生下拉菜单，因此不同浏览器的系统级菜单外观不会再介入。
- 风险控制：该菜单只影响特殊名单新增表单，不改变规则类型值、后端接口或已有名单数据。

## 2026-07-17 截图频率与历史保存裁决

### 目标

- 截图频率调整为：活动少于 1 分钟时 `0.25` 秒、空闲 1-3 分钟时 10 秒、空闲 3 分钟以上时 10 分钟。
- 特殊名单的历史保存统一由 Server 判断；Agent 仅上报截图对应的程序名、窗口标题和完整 URL。

### 实现方案

- Agent 删除本地特殊名单会话、预热和补存判定，只保留前台上下文采集；上传载荷不再携带 `store_history`、命中规则或策略阶段。
- Server 忽略旧 Agent 可能携带的 `store_history` 和策略元数据，以自身规则结果作为 Live 元数据与历史入库的唯一依据。
- Server 的名单规则保持不变：命中后前 10 秒允许保存，之后每 5 分钟补一张；普通对象仍保留每屏 2 秒历史节流。
- 新 Agent 版本为 `0.59.2`，用于将新的截图频率和上下文职责推送到被控机。

### 边缘情况与偏离说明

- Server 重启会清空内存中的名单会话计时；同一对象下一张图会重新进入最多 10 秒预热，偏向少漏图而非少存图。
- 旧 Agent 即使继续上传 `store_history=false` 或 `suppressed`，Server 也不再接受其裁决，避免新旧双重状态相互冲突。
- 测试必须分别从 `agent`、`server` 目录执行；若在仓库根目录把两套测试合并运行，Python 会将 `agent/main.py` 误解析为 Server 的 FastAPI `main`，属于测试导入路径冲突，不是功能错误。
- 发布辅助脚本调用 `/api/agents` 时应按 JSON 数组解析，而不是假设 `{ "agents": [...] }` 包装；接口本身正常，已按实际格式完成在线机器更新任务创建。

### 0.59.2 Agent 发布包

- `monitor-agent.exe` size：`57190025`
- `monitor-agent.exe` sha256：`296B466930C5F0C870C94E040CED45AE40771131FCE8A338ADF6065F4A339111`
- `WindowsMonitorSetup.exe` size：`58550732`
- `WindowsMonitorSetup.exe` sha256：`36C7DCD8106C81EBF79245179CD32C7EE4F0DF7764455626EC9E1D7063D72C97`

## 2026-07-17 双屏 Live 切换与上传延迟

### 目标

- 切换屏幕时优先显示目标屏最新画面，不因 5 秒延迟流刚好尚未就绪而停留在“正在切换屏幕”。
- 双屏高频采集时优先传输最新帧，避免上传队列积压后某一屏长期比另一屏落后。

### 实现方案

- 主 Live 卡片与放大 Live 在切屏后同时探测目标屏 fresh 帧和延迟帧；延迟帧可用前持续使用 fresh 帧，确认可用后才恢复延迟流。
- 切屏期间不读取另一块屏幕的图片，也不把历史截图当作 Live 首帧。
- Agent 默认截图上传队列从 200 帧降为 8 帧。双屏 4fps 时只保留约最近 1 秒候选帧，队列满时继续按“丢弃最旧、保留最新”运行。
- 新 Agent 版本为 `0.59.3`，使队列调整能经 Web 后台更新下发。

### 边缘情况与偏离说明

- Server 的延迟流仍保持 5 秒设计；本次只消除切屏期间的空白，未改变常态 Live 的延迟展示规则。
- 网络或上传异常导致目标屏完全没有 fresh 帧时，界面仍保持加载提示，不显示另一屏或历史旧图冒充目标屏 Live。

### 0.59.3 Agent 发布包

- `monitor-agent.exe` size：`57190600`
- `monitor-agent.exe` sha256：`822E223ED97D613FBE85295AA75A8F5F1D27B4E8B61F2FA37C0FA1F68FFD86C9`
- `WindowsMonitorSetup.exe` size：`58550784`
- `WindowsMonitorSetup.exe` sha256：`D674916A096810AF661F20E41371E577C6F96971ECEF55D4FDD21761963D434B`
