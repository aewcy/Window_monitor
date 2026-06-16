# 电脑监控系统 Demo

> ⚠️ 本软件仅在授权电脑执行。监控活动以公司权益为先，员工在使用电脑前已知情。

## 架构

```
试验机 (被监控)            服务器 (中转+存储)             管理端 (查看)
┌──────────────────┐     ┌─────────────────────┐     ┌──────────────┐
│ Agent (Python)   │─HTTP▶│ FastAPI Server      │◀──浏览器│ Web Dashboard │
│ ├ 屏幕截图       │     │ ├ 数据接收 API      │     │              │
│ ├ 应用窗口       │     │ ├ SQLite 存储       │     │              │
│ ├ 浏览器历史     │     │ └ 截图文件存储      │     │              │
│ └ 键盘Enter监控  │     └─────────────────────┘     └──────────────┘
└──────────────────┘
```

## 快速开始

### 1. 服务端

```bash
cd server
docker compose up -d
# → http://localhost:8899
```

详见 [server/README.md](server/README.md)

### 2. 被控端

```
# 独立 .exe (推荐 — 无需 Python):
复制 agent/dist/monitor-agent.exe → 双击运行

# 或源码运行:
cd agent && pip install -r requirements.txt && python main.py
```

详见 [agent/README.md](agent/README.md)

## 项目结构

```
monitor-demo/
├── agent/                     # 被控端 — 采集 + 上报
│   ├── README.md              #   部署与配置文档
│   ├── main.py                #   主程序
│   ├── config.py              #   配置文件
│   ├── screen_capture.py      #   屏幕截图
│   ├── app_tracker.py         #   窗口追踪
│   ├── browser_history.py     #   浏览器历史
│   ├── keyboard_monitor.py    #   键盘 Enter 监控
│   ├── agent.spec             #   PyInstaller 打包
│   ├── build.bat              #   一键打包
│   ├── start.bat              #   源码启动
│   └── requirements.txt       #   依赖
├── server/                    # 服务端 — 接收 + 存储 + API + 面板
│   ├── README.md              #   部署与 API 文档
│   ├── main.py                #   FastAPI 入口
│   ├── config.py              #   配置
│   ├── models.py              #   SQLite 数据层 (5 表)
│   ├── routes.py              #   REST API (26 端点)
│   ├── logger.py              #   日志模块 (按天轮转)
│   ├── Dockerfile             #   Docker 镜像
│   ├── docker-compose.yml     #   Docker 编排
│   ├── requirements.txt       #   依赖
│   └── static/
│       └── dashboard.html     #   Web 面板 (原生 HTML/CSS/JS)
├── tests/                     # 测试
├── .gitignore
└── README.md                  # ← 本文件
```
