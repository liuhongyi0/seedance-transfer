FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（pg_dump 用于数据库备份）
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（build context 是仓库根目录 seedance-transfer/）
COPY Seedance/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY Seedance/backend/ .

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 8000

# 启动命令（Railway 会通过 PORT 环境变量指定端口）
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --limit-concurrency 20 --limit-max-requests 2000 --backlog 50"]
