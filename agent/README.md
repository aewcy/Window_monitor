# Agent — 被控端 (试验机)

运行在被监控的 Windows/Linux 机器上，负责采集屏幕截图、应用窗口、浏览器历史、键盘 Enter 事件并上报服务端。

## 部署方式

### 方式一：独立 .exe (推荐)

被控机无需安装 Python 或任何依赖：

```
① 将 dist/monitor-agent.exe 复制到被控机
② 双击运行
```

通过环境变量配置服务器地址（可写入 .bat 启动脚本）：

```batch
set MONITOR_SERVER_HOST=108.187.15.71
set MONITOR_SERVER_PORT=8899
set AGENT_NAME=试验机-01
monitor-agent.exe
```

### 方式二：源码运行

被控机需安装 Python 3.10+：

```bash
# Windows — 双击 start.bat (自动检测环境)
# Linux
pip install -r requirements.txt
MONITOR_SERVER_HOST=<IP> python main.py
```

## 配置

所有配置在 [config.py](config.py) 中，均支持环境变量覆盖：

| 参数 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| `SERVER_HOST` | `MONITOR_SERVER_HOST` | `108.187.15.71` | 服务端地址 |
| `SERVER_PORT` | `MONITOR_SERVER_PORT` | `8899` | 服务端端口 |
| `AGENT_NAME` | `AGENT_NAME` | `试验机-01` | 机器标识 |
| `SCREENSHOT_INTERVAL` | `SCREENSHOT_INTERVAL` | `30` | 截图间隔(秒) — 运行时会自适应调整 |
| `APP_TRACK_INTERVAL` | `APP_TRACK_INTERVAL` | `5` | 窗口检测间隔(秒) |
| `BROWSER_HISTORY_INTERVAL` | `BROWSER_HISTORY_INTERVAL` | `60` | 浏览器采集间隔(秒) |
| `SCREENSHOT_QUALITY` | `SCREENSHOT_QUALITY` | `40` | JPEG 质量(1-100) |
| `SCREENSHOT_MAX_WIDTH` | `SCREENSHOT_MAX_WIDTH` | `1280` | 截图最大宽度 |

### 前台白名单

[config.py](config.py) 中 `FOREGROUND_WHITELIST` 字典配置了前台白名单应用（WeChat/QQ/DingTalk/Telegram 等），当前台窗口命中白名单时按 Enter 键自动截图。

### 自适应截图频率

| 状态 | 间隔 | 触发条件 |
|------|------|----------|
| ACTIVE | 0.25s | 检测到 Enter 按键或窗口切换 |
| VIEWER | 1s | Dashboard 有人正在查看 |
| IDLE | 5s | 1 分钟无活动 |

## 打包 (.exe)

在本机执行：

```bash
pip install pyinstaller
双击 build.bat
# 或: pyinstaller --clean agent.spec
```

输出: `dist/monitor-agent.exe` (~61MB，单文件，零依赖)

## 文件清单

```
agent/
├── main.py                 # 主程序入口
├── config.py               # 配置文件
├── screen_capture.py       # 屏幕截图 (mss/PIL)
├── app_tracker.py          # 活动窗口追踪 (win32gui)
├── browser_history.py      # 浏览器历史采集
├── keyboard_monitor.py     # 键盘 Enter 监听 (pynput)
├── agent.spec              # PyInstaller 规格
├── build.bat               # 一键打包脚本
├── start.bat               # 源码运行启动脚本
└── requirements.txt        # Python 依赖
```
