FROM python:3.11-slim
# cache-bust: v6
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY Seedance/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Seedance/backend/ .

# Verify moderation module is present (forces cache invalidation)
RUN test -f /app/services/moderation.py && echo "moderation module OK" || (echo "MISSING moderation module" && exit 1)

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --limit-concurrency 20 --limit-max-requests 2000 --backlog 50"]
