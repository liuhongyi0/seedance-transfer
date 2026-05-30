FROM python:3.11-slim

WORKDIR /app

# Install system deps (pg_dump for DB backup)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (build context = repo root seedance-transfer/)
COPY Seedance/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code (cache bust: 2026-05-30 v2 — Sentry + R2 + backup + 9 video models)
COPY Seedance/backend/ .

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 启动命令（Railway 会通过 PORT 环境变量指定端口）
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --limit-concurrency 20 --limit-max-requests 2000 --backlog 50"]
