# Windows Monitor

员工电脑监控 Demo，包含被控端 Agent、FastAPI 服务端和浏览器 Dashboard。

## 主要入口

- 管理后台：`http://<server-ip>:8899/`
- 下载页：`http://<server-ip>:8899/download`
- API 文档：`http://<server-ip>:8899/docs`
- 文件结构说明：[docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)

## 组件

```text
Agent (Windows) -> FastAPI Server -> Dashboard
```

- `agent/`：被控端程序，采集截图、活动窗口、浏览器历史和聊天 Enter 事件。
- `server/`：服务端 API、SQLite 数据层、静态文件和 Docker 部署配置。
- `server/dashboard/`：Vue 3 Dashboard 源码。
- `installer/`：Inno Setup 安装器脚本。
- `server/static/agent/WindowsMonitorSetup.exe`：Web 下载页实际提供的安装器。

## 常用命令

服务端部署：

```bash
cd server
docker compose up -d --build
```

本地启动服务端：

```bash
cd server
pip install -r requirements.txt
python main.py
```

构建 Dashboard：

```bash
cd server/dashboard
npm install
npm run build
```

构建 Agent：

```bat
cd agent
build.bat
```

编译安装器：

```powershell
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\windows-monitor.iss
```

## 发布链路

```text
agent/build.bat
  -> server/static/agent/monitor-agent.exe
installer/windows-monitor.iss
  -> server/static/agent/WindowsMonitorSetup.exe
/download
  -> /api/agent/download
  -> WindowsMonitorSetup.exe
```

## 注意

本系统会采集屏幕截图、窗口信息和浏览器历史。只能用于已授权、已告知的设备环境。
