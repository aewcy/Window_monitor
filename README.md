# Windows Monitor 后端部署说明

Windows Monitor 是一个“被控端 Agent -> 后端服务 -> Web 管理后台”的监控 Demo。后端负责接收 Agent 上报的数据、保存截图和 SQLite 数据库，并提供 Web Dashboard 与下载页。

## 线上入口

- 管理后台：`http://<服务器IP>:8899/`
- Agent 下载页：`http://<服务器IP>:8899/download`
- API 文档：`http://<服务器IP>:8899/docs`
- 健康检查：`http://<服务器IP>:8899/api/health`

## 后端目录

主要部署目录是 `server/`：

```text
server/
├─ main.py                 # FastAPI 入口
├─ routes.py               # API 路由
├─ models.py               # SQLite 数据层
├─ config.py               # 环境变量配置
├─ logger.py               # 日志
├─ Dockerfile              # 后端镜像
├─ docker-compose.yml      # 推荐部署方式
├─ requirements.txt        # Python 依赖
├─ dashboard/              # Vue Dashboard 源码
├─ static/
│  ├─ dist/                # Dashboard 构建产物
│  ├─ download.html        # Agent 下载页
│  └─ agent/
│     ├─ WindowsMonitorSetup.exe
│     └─ monitor-agent.exe
└─ data/                   # 运行时数据，不提交 Git
```

完整文件结构见：[docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)

## 推荐部署：Docker Compose

服务器需要先安装：

- Git
- Docker
- Docker Compose v2

首次部署：

```bash
git clone git@github.com:aewcy/monitor-aewcy.git
cd monitor-aewcy/server
docker compose up -d --build
```

启动后访问：

```text
http://服务器IP:8899/
```

查看容器状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

## 更新部署

每次代码推送后，服务器执行：

```bash
cd /root/monitor-aewcy/server
git pull --ff-only
docker compose up -d --build
```

如果只是 README 或文档更新，不需要重启 Docker。  
如果改了 `server/main.py`、`server/routes.py`、Dashboard、下载页或安装包，需要重新 `docker compose up -d --build`。

## 数据持久化

`server/docker-compose.yml` 会把宿主机目录挂载到容器：

```yaml
volumes:
  - ./data:/app/data
```

因此这些数据会保存在服务器的 `server/data/`：

- SQLite 数据库
- 截图文件
- 运行日志相关数据

重建容器不会删除 `server/data/`。不要把这个目录提交到 Git。

## 端口和环境变量

默认端口是 `8899`。

`server/docker-compose.yml` 中的默认配置：

```yaml
environment:
  - TZ=Asia/Shanghai
  - SERVER_HOST=0.0.0.0
  - SERVER_PORT=8899
ports:
  - "8899:8899"
```

如果要换端口，例如改成公网 `9000`：

```yaml
ports:
  - "9000:8899"
```

然后重启：

```bash
docker compose up -d
```

## Agent 下载包

用户访问：

```text
http://服务器IP:8899/download
```

页面会下载：

```text
server/static/agent/WindowsMonitorSetup.exe
```

下载接口是：

```text
GET /api/agent/download
```

如果重新生成安装器，需要确认新文件已经放到：

```text
server/static/agent/WindowsMonitorSetup.exe
```

然后提交、推送，服务器 `git pull` 后重建 Docker。

## 本地开发启动

不用 Docker 时可以本地跑：

```bash
cd server
pip install -r requirements.txt
python main.py
```

Dashboard 开发：

```bash
cd server/dashboard
npm install
npm run dev
```

Dashboard 构建：

```bash
cd server/dashboard
npm run build
```

构建产物会输出到：

```text
server/static/dist/
```

## 常见排查

确认后端是否活着：

```bash
curl http://127.0.0.1:8899/api/health
```

确认下载接口是否返回安装器：

```bash
curl -I http://127.0.0.1:8899/api/agent/download
```

查看容器日志：

```bash
cd server
docker compose logs -f --tail=100
```

进入容器：

```bash
docker exec -it monitor-server sh
```

## 安全提醒

本系统会采集截图、活动窗口和浏览器历史。只能部署在已授权、已告知的设备环境中。
