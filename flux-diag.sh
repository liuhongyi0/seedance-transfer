#!/usr/bin/env bash
# 诊断 Flux/fal.ai 问题，结果写入共享文件
OUT=~/ClaudeProject/seedance-transfer/flux-diag-result.txt
exec > "$OUT" 2>&1

echo "=== Flux 诊断 $(date) ==="
echo

echo "-- 1. 后端状态 --"
curl -sf http://localhost:3000/health && echo " OK" || echo " 后端未运行"
echo

echo "-- 2. 后端日志中的 Flux 错误 --"
grep -i "flux\|fal\|preview" /tmp/backend-new.log 2>/dev/null | grep -i "error\|fail\|warn\|HTTP\|返回" | tail -20 || echo "(无日志或无错误)"
echo

echo "-- 3. 直接调用 fal.ai API --"
FAL_KEY=$(grep ^FAL_KEY ~/ClaudeProject/seedance-transfer/backend/.env | cut -d= -f2 | tr -d ' ')
echo "Key prefix: ${FAL_KEY:0:20}..."
RESP=$(curl -s -X POST "https://fal.run/fal-ai/flux/schnell" \
  -H "Content-Type: application/json" \
  -H "Authorization: Key $FAL_KEY" \
  -d '{"prompt":"red shoe","image_size":"landscape_16_9","num_images":1,"num_inference_steps":4,"sync_mode":true}' \
  --max-time 30 -w "\n===HTTP_STATUS:%{http_code}===")
echo "Response:"
echo "$RESP"
echo

echo "-- 完成 --"
echo "结果已写入: $OUT"
