# 会议纪要助手 — M3 多服务镜像（api / worker 共用同一镜像，命令区分）
FROM python:3.11-slim

# FFmpeg（抽音轨 / 切片）+ curl（健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用代码与前端静态资源
COPY app ./app
COPY static ./static

EXPOSE 8000

# 默认以 API 服务启动；worker 由 compose 用 `command: celery ...` 覆盖
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
