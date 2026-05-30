FROM python:3.11-slim
# cache-bust: 2026-05-30-v3

WORKDIR /app

# Install system deps (pg_dump for DB backup)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY Seedance/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY Seedance/backend/ .

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --limit-concurrency 20 --limit-max-requests 2000 --backlog 50"]
