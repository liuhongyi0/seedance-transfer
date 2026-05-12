#!/bin/bash
# ─────────────────────────────────────────────
# Seedance Wizard — 一键部署脚本
# 适用：全新 Ubuntu 22.04 ECS（首次部署）
#
# 用法：
#   chmod +x deploy.sh
#   sudo ./deploy.sh
# ─────────────────────────────────────────────

set -e  # 任何命令失败立即退出
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
die()  { echo -e "${RED}[error]${NC} $1"; exit 1; }

# ── 配置区（首次部署前填写）──────────────────
DOMAIN="app.seedance.ai"          # ← 替换为你的域名
REPO_URL="https://github.com/你的账号/seedance-wizard.git"  # ← 替换为你的仓库
DEPLOY_DIR="/var/www/seedance"
DB_NAME="seedance"
DB_USER="seedance"
DB_PASS=$(openssl rand -base64 24 | tr -d '/')   # 随机生成

# ─────────────────────────────────────────────

log "=== Step 1: 系统更新 & 基础工具 ==="
apt-get update -qq
apt-get install -y -qq git curl wget nginx postgresql certbot python3-certbot-nginx ufw

# ── 防火墙 ───────────────────────────────────
log "=== Step 2: 防火墙配置 ==="
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
log "防火墙已启用（22/80/443）"

# ── Node.js 20 LTS ───────────────────────────
log "=== Step 3: 安装 Node.js 20 LTS ==="
if ! command -v node &> /dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
node --version
npm --version

# ── PM2 ──────────────────────────────────────
log "=== Step 4: 安装 PM2 ==="
npm install -g pm2
mkdir -p /var/log/pm2

# ── PostgreSQL ───────────────────────────────
log "=== Step 5: 配置 PostgreSQL ==="
systemctl start postgresql
systemctl enable postgresql

# 创建数据库用户和数据库（幂等）
sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" 2>/dev/null || true
log "PostgreSQL 数据库已就绪: ${DB_NAME}@localhost / 用户: ${DB_USER}"
warn "数据库密码（请记录）: ${DB_PASS}"

# ── 拉取代码 ─────────────────────────────────
log "=== Step 6: 拉取代码 ==="
mkdir -p "${DEPLOY_DIR}"
if [ -d "${DEPLOY_DIR}/.git" ]; then
  cd "${DEPLOY_DIR}" && git pull
else
  git clone "${REPO_URL}" "${DEPLOY_DIR}"
fi

# ── 生成 .env ────────────────────────────────
log "=== Step 7: 配置环境变量 ==="
JWT_SECRET=$(node -e "console.log(require('crypto').randomBytes(64).toString('hex'))")

if [ ! -f "${DEPLOY_DIR}/backend/.env" ]; then
  cat > "${DEPLOY_DIR}/backend/.env" << EOF
DEPLOYMENT_REGION=cn
PORT=3000
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@127.0.0.1:5432/${DB_NAME}
JWT_SECRET=${JWT_SECRET}

# ── 以下 Key 需手动填写 ──────────────────────
DEEPSEEK_API_KEY=
DASHSCOPE_API_KEY=
MUAPI_KEY=
FAL_KEY=

SMS_ACCESS_KEY_ID=
SMS_PROVIDER_KEY=
SMS_SIGN_NAME=Seedance
SMS_TEMPLATE_CODE=

XUNHUPAY_APPID=
XUNHUPAY_APPSECRET=
XUNHUPAY_NOTIFY_URL=https://${DOMAIN}/api/payment/notify
EOF
  chmod 600 "${DEPLOY_DIR}/backend/.env"
  warn ".env 已生成，请填写 API Key 后重新运行: nano ${DEPLOY_DIR}/backend/.env"
else
  log ".env 已存在，跳过生成"
fi

# ── 构建后端 ─────────────────────────────────
log "=== Step 8: 构建后端 ==="
cd "${DEPLOY_DIR}/backend"
npm ci --production=false
npm run build
log "后端构建完成"

# ── 构建前端 ─────────────────────────────────
log "=== Step 9: 构建前端 ==="
cd "${DEPLOY_DIR}/web-portal"
npm ci
npm run build
log "前端构建完成"

# ── Nginx 配置 ───────────────────────────────
log "=== Step 10: 配置 Nginx ==="
cp "${DEPLOY_DIR}/deploy/nginx.conf" /etc/nginx/sites-available/seedance
# 替换域名占位符
sed -i "s/app.seedance.ai/${DOMAIN}/g" /etc/nginx/sites-available/seedance

# 删除 default 配置，启用 seedance
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/seedance /etc/nginx/sites-enabled/seedance

nginx -t && systemctl reload nginx
log "Nginx 配置完成"

# ── PM2 启动 ─────────────────────────────────
log "=== Step 11: PM2 启动服务 ==="
cd "${DEPLOY_DIR}"
pm2 delete all 2>/dev/null || true
pm2 start deploy/ecosystem.config.js
pm2 save
pm2 startup systemd -u root --hp /root 2>/dev/null | tail -1 | bash 2>/dev/null || true
log "PM2 服务已启动"

# ── Let's Encrypt SSL ─────────────────────────
log "=== Step 12: SSL 证书 ==="
warn "即将申请 Let's Encrypt 证书，请确保 ${DOMAIN} 已解析到本机 IP"
read -r -p "  继续申请证书？[y/N] " confirm
if [[ "${confirm}" =~ ^[Yy]$ ]]; then
  certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m admin@${DOMAIN} || \
    warn "证书申请失败，请检查域名解析后手动运行: certbot --nginx -d ${DOMAIN}"
else
  warn "跳过证书申请。可手动运行: certbot --nginx -d ${DOMAIN}"
fi

# ── 验收检查 ─────────────────────────────────
log "=== Step 13: 验收检查 ==="
sleep 3
BACKEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/health)
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3001)

echo ""
echo "────────────────────────────────────────────"
echo "  部署结果"
echo "────────────────────────────────────────────"
echo "  后端健康检查 (3000):  HTTP ${BACKEND_HEALTH} $([ "${BACKEND_HEALTH}" = "200" ] && echo "✅" || echo "❌")"
echo "  前端状态 (3001):      HTTP ${FRONTEND_STATUS} $([ "${FRONTEND_STATUS}" = "200" ] && echo "✅" || echo "❌")"
echo "  PostgreSQL:           $(pg_isready -U ${DB_USER} -d ${DB_NAME} > /dev/null 2>&1 && echo "✅ 运行中" || echo "❌ 异常")"
echo "  PM2 进程:"
pm2 list
echo ""
echo "  📝 下一步："
echo "  1. 填写 API Key: nano ${DEPLOY_DIR}/backend/.env"
echo "  2. 重启后端:     pm2 restart seedance-backend"
echo "  3. 访问:         https://${DOMAIN}"
echo "────────────────────────────────────────────"
