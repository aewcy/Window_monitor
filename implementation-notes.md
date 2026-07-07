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
