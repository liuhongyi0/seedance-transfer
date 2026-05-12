#!/bin/bash
# ─────────────────────────────────────────────
# Seedance Wizard — 热更新脚本（代码发布）
# 在服务器上已部署后，每次推送新版本时使用
#
# 用法：
#   chmod +x update.sh
#   ./update.sh              # 更新全部
#   ./update.sh --backend    # 仅更新后端
#   ./update.sh --frontend   # 仅更新前端
# ─────────────────────────────────────────────

set -e
DEPLOY_DIR="/var/www/seedance"
GREEN='\033[0;32m'; NC='\033[0m'
log() { echo -e "${GREEN}[update]${NC} $1"; }

MODE="${1:-all}"

cd "${DEPLOY_DIR}"

log "拉取最新代码..."
git pull

if [[ "${MODE}" == "--backend" || "${MODE}" == "all" ]]; then
  log "重新构建后端..."
  cd "${DEPLOY_DIR}/backend"
  npm ci --production=false
  npm run build
  pm2 restart seedance-backend
  log "后端已更新 ✅"
fi

if [[ "${MODE}" == "--frontend" || "${MODE}" == "all" ]]; then
  log "重新构建前端..."
  cd "${DEPLOY_DIR}/web-portal"
  npm ci
  npm run build
  pm2 restart seedance-frontend
  log "前端已更新 ✅"
fi

log "更新完成，PM2 状态："
pm2 list
