# 项目文件结构

这个项目分为三层：被控端 Agent、服务端 API、浏览器 Dashboard。当前对外下载的是 Inno Setup 安装器，安装器内部包含 Agent 可执行文件和安装脚本。

```text
monitor-demo/
├─ agent/                         # 被控端程序：采集截图、窗口、浏览器历史并上报
│  ├─ main.py                      # Agent 主入口
│  ├─ config.py                    # Agent 环境变量配置
│  ├─ screen_capture.py            # 多屏截图
│  ├─ app_tracker.py               # 活动窗口采集
│  ├─ browser_history.py           # 浏览器历史采集
│  ├─ keyboard_monitor.py          # 聊天软件 Enter 事件监听
│  ├─ install-agent.ps1            # Windows 安装/卸载核心脚本
│  ├─ install-agent.bat            # 旧 ZIP 安装入口，保留兼容
│  ├─ uninstall-agent.bat          # 手动卸载入口，保留兼容
│  ├─ agent.spec                   # PyInstaller 打包配置
│  ├─ build.bat                    # 构建 monitor-agent.exe
│  └─ assets/
│     └─ windows-monitor.ico       # Agent/安装器图标
│
├─ installer/
│  └─ windows-monitor.iss          # Inno Setup 安装器脚本
│
├─ server/                         # FastAPI 服务端
│  ├─ main.py                      # FastAPI 应用入口
│  ├─ routes.py                    # API 路由
│  ├─ models.py                    # SQLite 数据层
│  ├─ config.py                    # 服务端配置
│  ├─ logger.py                    # 日志
│  ├─ Dockerfile                   # 服务端镜像
│  ├─ docker-compose.yml           # 服务器部署
│  ├─ requirements.txt             # Python 依赖
│  ├─ static/
│  │  ├─ download.html             # /download 独立下载页
│  │  ├─ agent/
│  │  │  ├─ WindowsMonitorSetup.exe # 当前 Web 下载的安装器
│  │  │  ├─ monitor-agent.exe       # 安装器内置的 Agent 程序
│  │  │  ├─ install-agent.ps1       # 安装器调用的安装脚本副本
│  │  │  ├─ install-agent.bat       # 兼容旧下载包
│  │  │  └─ uninstall-agent.bat     # 兼容旧下载包
│  │  ├─ assets/
│  │  │  └─ windows-monitor-icon.png # 下载页展示图标
│  │  └─ dist/                     # Vue Dashboard 构建产物
│  ├─ dashboard/                   # Vue 3 Dashboard 源码
│  │  ├─ src/
│  │  ├─ package.json
│  │  └─ vite.config.js
│  └─ data/                        # 运行时数据，gitignore，不提交
│
├─ docs/                           # 需求、设计和结构文档
├─ README.md                       # 项目入口说明
├─ run-tests.bat                   # 测试入口
└─ .gitignore
```

## 构建和发布路径

```text
agent/agent.spec
  ↓ PyInstaller
server/static/agent/monitor-agent.exe
  ↓ Inno Setup: installer/windows-monitor.iss
server/static/agent/WindowsMonitorSetup.exe
  ↓ /api/agent/download
用户访问 /download 下载
```

## 目录规则

- `agent/` 只放 Agent 源码、安装脚本和 Agent 构建配置。
- `installer/` 只放安装器脚本，不放临时输出。
- `server/static/agent/` 放 Web 实际下载所需的发布产物。
- `server/data/`、`build/`、`dist/`、`agent/build/`、`agent/dist/` 都是本地或运行时目录，不应该提交。
- `.codex/`、`AGENTS.md` 是本地 Codex 工作配置，不进入版本库。
