#!/bin/bash
# Seedance Studio 国内版 ECS 一键部署脚本
# 用法：在 ECS 上克隆仓库后，cd backend && bash deploy-ecs.sh

set -e

echo "=== Seedance Studio 国内版部署 ==="

# 检查 Docker
if ! command -v docker &>/dev/null; then
    echo "安装 Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker && systemctl start docker
fi

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "创建 .env 文件，请填入你的 API Key..."
    cat > .env <<'EOF'
# 部署区域（国内版）
DEPLOYMENT_REGION=cn

# EvoLink API Key
EVOLINK_API_KEY=sk-your-evolink-key

# 火山引擎 API Key
VOLC_API_KEY=ark-your-volc-key

# imgbb 图床 Key（用于 TOS URL 中转）
IMGBB_API_KEY=your-imgbb-key

# JWT 签名密钥（openssl rand -hex 32）
JWT_SECRET=change-me-to-random-32-chars

# 数据库密码
DB_PASSWORD=seedance-prod-$(openssl rand -hex 6)

# 服务地址
BASE_URL=http://your-server-ip
EOF
    echo ".env 已创建，请编辑填入真实 Key 后重新运行此脚本"
    exit 1
fi

# 加载环境变量
set -a; source .env; set +a

echo "启动服务（PostgreSQL + 后端 + nginx）..."
docker compose up -d --build

echo ""
echo "=== 部署完成 ==="
echo "检查状态: docker compose ps"
echo "查看日志: docker compose logs -f backend"
echo "健康检查: curl http://localhost:8000/health"
echo "主页访问: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')/"
