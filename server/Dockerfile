# ============================================
# Monitor Server - Docker 镜像
# 在 server/ 目录下构建
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
COPY . /app/

# 数据目录
RUN mkdir -p /app/data/screenshots

EXPOSE 8899

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8899"]
