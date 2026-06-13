# ============================================
# Monitor Server - Docker 镜像
# ============================================
FROM python:3.11-slim

LABEL org.opencontainers.image.title="monitor-server"
LABEL org.opencontainers.image.description="Monitor system server"
LABEL org.opencontainers.image.source="https://github.com/aewcy/monitor-aewcy"

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制服务端代码
COPY server/ ./server/

# 数据目录 (挂载到宿主机以持久化)
RUN mkdir -p /app/server/data/screenshots

# 暴露端口
EXPOSE 8899

# 启动
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8899"]
