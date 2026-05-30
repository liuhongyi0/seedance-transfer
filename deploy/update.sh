#!/bin/bash
# Seedance Studio — 热更新脚本 (Docker Compose)
# 零停机更新：拉取代码 → 重建镜像 → 滚动重启
#
# 用法：
#   ./deploy/update.sh              # 更新全部
#   ./deploy/update.sh --backend    # 仅更新后端
#   ./deploy/update.sh --nginx      # 仅更新 nginx 配置

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[update]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }

DEPLOY_DIR="${DEPLOY_DIR:-/opt/seedance}"
cd "$DEPLOY_DIR"

MODE="${1:-all}"

log "Pulling latest code..."
git pull --ff-only

if [[ "$MODE" == "--backend" || "$MODE" == "all" ]]; then
    log "Rebuilding backend..."
    docker compose build --no-cache backend
    docker compose up -d backend
    sleep 3
    # Verify
    HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
    log "Backend health: HTTP $HEALTH"
fi

if [[ "$MODE" == "--nginx" || "$MODE" == "all" ]]; then
    log "Reloading nginx..."
    docker compose restart nginx
fi

log "Update complete. Service status:"
docker compose ps
