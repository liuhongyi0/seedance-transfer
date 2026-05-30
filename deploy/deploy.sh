#!/bin/bash
# Seedance Studio — 一键部署脚本 (FastAPI + Docker Compose)
# 适用：全新 Ubuntu 22.04/24.04 VPS（首次部署）
#
# 用法：
#   chmod +x deploy/deploy.sh
#   sudo ./deploy/deploy.sh

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
die()  { echo -e "${RED}[error]${NC} $1"; exit 1; }

# ── Configuration ─────────────────────────────────────────────────────
DOMAIN="${DOMAIN:-see4dance.com}"
EMAIL="${EMAIL:-admin@see4dance.com}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/seedance}"
REPO_URL="${REPO_URL:-https://github.com/your-account/seedance-transfer.git}"
DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/')

# ── Step 1: System packages ───────────────────────────────────────────
log "Step 1/9: Installing system packages..."
apt-get update -qq
apt-get install -y -qq curl wget git ufw

# ── Step 2: Docker ────────────────────────────────────────────────────
log "Step 2/9: Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | bash
fi

# Docker Compose plugin
if ! docker compose version &> /dev/null; then
    apt-get install -y -qq docker-compose-plugin
fi
docker --version
docker compose version

# ── Step 3: Firewall ──────────────────────────────────────────────────
log "Step 3/9: Configuring firewall..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ── Step 4: Clone repo ────────────────────────────────────────────────
log "Step 4/9: Cloning repository..."
mkdir -p "$DEPLOY_DIR"
if [ -d "$DEPLOY_DIR/.git" ]; then
    cd "$DEPLOY_DIR" && git pull
else
    git clone "$REPO_URL" "$DEPLOY_DIR"
fi
cd "$DEPLOY_DIR"

# ── Step 5: Environment ───────────────────────────────────────────────
log "Step 5/9: Setting up .env..."
JWT_SECRET=$(openssl rand -hex 64)

if [ ! -f Seedance/backend/.env ]; then
    if [ -f Seedance/backend/.env.example ]; then
        cp Seedance/backend/.env.example Seedance/backend/.env
    fi
    # Update critical values
    cat >> Seedance/backend/.env << EOF

# ── Deploy-generated secrets ──────────────────────────────────────────
JWT_SECRET=${JWT_SECRET}
DATABASE_URL=postgresql://seedance:${DB_PASSWORD}@db:5432/seedance
DB_PASSWORD=${DB_PASSWORD}
BASE_URL=https://${DOMAIN}
EOF
    chmod 600 Seedance/backend/.env
    warn ".env created. Fill in API keys: nano Seedance/backend/.env"
fi

# ── Step 6: Build ─────────────────────────────────────────────────────
log "Step 6/9: Building Docker images..."
docker compose build --pull

# ── Step 7: SSL certificate ───────────────────────────────────────────
log "Step 7/9: Setting up SSL..."
echo "Ensure ${DOMAIN} DNS points to this server's IP before continuing."
read -r -p "Continue with SSL setup? [Y/n] " confirm
if [[ ! "${confirm}" =~ ^[Nn] ]]; then
    bash deploy/certbot-init.sh "$DOMAIN" "$EMAIL"
else
    warn "Skipping SSL. Run later: ./deploy/certbot-init.sh"
fi

# ── Step 8: Launch ────────────────────────────────────────────────────
log "Step 8/9: Starting services..."
docker compose up -d
sleep 5

# ── Step 9: Verify ────────────────────────────────────────────────────
log "Step 9/9: Health check..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health 2>/dev/null || echo "000")

echo ""
echo "────────────────────────────────────────"
echo "  Seedance Studio — 部署结果"
echo "────────────────────────────────────────"
echo "  Backend (8000):  HTTP ${HEALTH} $([ "$HEALTH" = "200" ] && echo "✅" || echo "❌")"
echo "  Nginx (80):      HTTP ${HTTP_CODE} $([ "$HTTP_CODE" = "200" ] && echo "✅" || echo "❌")"
echo "  Domain:          https://${DOMAIN}"
echo "  DB password:     ${DB_PASSWORD} (saved in .env)"
echo ""
echo "  📝 Next steps:"
echo "  1. Fill in API keys: nano ${DEPLOY_DIR}/Seedance/backend/.env"
echo "  2. Restart:          docker compose restart backend"
echo "  3. View logs:        docker compose logs -f backend"
echo "  4. Visit:            https://${DOMAIN}"
echo "────────────────────────────────────────"
