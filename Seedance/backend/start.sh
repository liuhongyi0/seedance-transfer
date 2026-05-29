#!/bin/bash
# Seedance Studio 后端一键启动脚本

set -e

echo "==================================="
echo "  Seedance Studio 后端启动"
echo "==================================="

# 检查Python版本
python3 --version || { echo "❌ 需要 Python 3.9+"; exit 1; }

# 检查.env文件
if [ ! -f ".env" ]; then
  echo "📋 复制 .env.example → .env"
  cp .env.example .env
  echo "⚠️  请编辑 .env 文件，填入你的API Key后重新运行"
  echo "   EVOLINK_API_KEY=  → https://evolink.ai 注册获取"
  echo "   VOLC_API_KEY=     → https://console.volcengine.com 获取"
  exit 0
fi

# 安装依赖
echo "📦 安装Python依赖..."
pip install -r requirements.txt -q

# 启动服务
echo ""
echo "🚀 启动后端服务..."
echo "   API文档：http://localhost:8000/docs"
echo "   健康检查：http://localhost:8000/health"
echo ""
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
