# ============================================
# Monitor Server - Docker 镜像
# 在 server/ 目录下构建
# ============================================

# Stage 1: 构建 Vue Dashboard
FROM node:20-slim AS frontend
WORKDIR /build
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ .
RUN npm run build

# Stage 2: Python 服务
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

# 从 Stage 1 复制 Vue 构建产物 (vite outDir: ../static/dist)
COPY --from=frontend /static/dist /app/static/dist

# 数据目录
RUN mkdir -p /app/data/screenshots

EXPOSE 8899

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8899"]
