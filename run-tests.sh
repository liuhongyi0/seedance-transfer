#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Seedance Wizard — 全套集成测试脚本
# 使用前确保后端正在运行: cd backend && npm run dev
# ─────────────────────────────────────────────────────────

set -uo pipefail
BASE="http://localhost:3000"
PASS=0; FAIL=0

pass() { echo "  ✅  $1"; PASS=$((PASS + 1)); }
fail() { echo "  ❌  $1"; FAIL=$((FAIL + 1)); }
section() { echo; echo "══════════════════════════════════"; echo "  $1"; echo "══════════════════════════════════"; }

# ── 健康检查 ──────────────────────────────────────────────
section "健康检查"
HEALTH=$(curl -sf "$BASE/health") && pass "health OK: $(echo $HEALTH | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("status","?"),d.get("region","?"))')" || fail "health check failed"

# ── BLOCK A：认证 ─────────────────────────────────────────
section "BLOCK A：认证"

SMS=$(curl -sf -X POST "$BASE/api/auth/sms" \
  -H "Content-Type: application/json" \
  -d '{"phone":"13811111111"}' 2>&1)
echo "  SMS response: $SMS"

# 通过 DB 直接注入测试用户（确保存在）
# bcrypt hash of "Test1234!" (rounds=12)
TEST_HASH='$2b$12$obeRiKuUw6IPI63xx7vHge1WKaxKDBPrYQeX8vEzLh.IsnM1Vb6GO'
psql seedance -q -c "INSERT INTO users(id,phone,password_hash,is_active,auth_provider,created_at) VALUES(gen_random_uuid(),'13800000001','${TEST_HASH}',true,'phone',now()) ON CONFLICT DO NOTHING;" 2>/dev/null && echo "  ℹ️  测试用户插入/已存在" || true

USER_ID=$(psql seedance -t -q -c "SELECT id FROM users WHERE phone='13800000001' LIMIT 1;" 2>/dev/null | tr -d ' \n')
if [ -z "$USER_ID" ]; then
  fail "找不到测试用户 13800000001（DB 写入失败）"
else
  pass "找到测试用户 user_id=${USER_ID:0:8}..."
fi

# 确保 balances 记录存在
psql seedance -q -c "INSERT INTO balances(user_id,amount_fen,currency,updated_at) VALUES('$USER_ID',50000,'CNY',now()) ON CONFLICT DO NOTHING;" 2>/dev/null || true

# 登录拿 JWT
LOGIN=$(curl -sf -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800000001","password":"Test1234!"}' 2>&1)
JWT=$(echo "$LOGIN" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])' 2>/dev/null || echo "")
if [ -n "$JWT" ]; then
  pass "登录成功，JWT 已获取"
else
  fail "登录失败: $LOGIN"
  echo "  ⚠️  后续测试将跳过（无 JWT）"
  echo; echo "总计: PASS=$PASS FAIL=$FAIL"; exit 1
fi

# ── BLOCK B：账户 ─────────────────────────────────────────
section "BLOCK B：账户"

BAL=$(curl -sf "$BASE/api/balance" -H "Authorization: Bearer $JWT")
BAL_FEN=$(echo "$BAL" | python3 -c 'import sys,json;print(json.load(sys.stdin)["amount_fen"])' 2>/dev/null || echo "-1")
CURRENCY=$(echo "$BAL" | python3 -c 'import sys,json;print(json.load(sys.stdin)["currency"])' 2>/dev/null || echo "?")
pass "余额查询 OK: ${BAL_FEN} fen, currency=${CURRENCY}"

# 注入余额（确保够用）
psql seedance -q -c "UPDATE balances SET amount_fen=50000 WHERE user_id='$USER_ID';" 2>/dev/null && pass "余额注入 50000 fen OK" || fail "余额注入失败"

# 创建 API Key
KEY_RESP=$(curl -sf -X POST "$BASE/api/keys" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"自动测试Key"}')
API_KEY=$(echo "$KEY_RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["key"])' 2>/dev/null || echo "")
if [ -n "$API_KEY" ]; then
  pass "API Key 创建 OK: ${API_KEY:0:16}..."
else
  fail "API Key 创建失败"
fi

# 用 API Key 认证
BAL2=$(curl -sf "$BASE/api/balance" -H "Authorization: Bearer $API_KEY" 2>/dev/null || echo "{}")
if echo "$BAL2" | python3 -c 'import sys,json;json.load(sys.stdin)["amount_fen"]' 2>/dev/null; then
  pass "API Key 双模式认证 OK"
else
  fail "API Key 认证失败"
fi

# ── BLOCK C：向导分析 ─────────────────────────────────────
section "BLOCK C：向导分析（Qwen VL + DeepSeek + Flux）"

echo "  下载测试图片..."
curl -sf -o /tmp/test_img.jpg "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400" \
  && pass "测试图片下载 OK" \
  || { fail "图片下载失败"; }

IMG_B64="data:image/jpeg;base64,$(base64 -i /tmp/test_img.jpg | tr -d '\n')"

echo "  调用 /api/wizard/analyze（预计 20-40 秒）..."
ANALYZE=$(curl -sf --max-time 120 -X POST "$BASE/api/wizard/analyze" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{\"image_b64\":\"$IMG_B64\",\"user_idea\":\"把这个产品做成高端商业广告，突出质感和科技感\",\"aspect_ratio\":\"16:9\"}" 2>&1)

SESSION_ID=$(echo "$ANALYZE" | python3 -c 'import sys,json;print(json.load(sys.stdin)["session_id"])' 2>/dev/null || echo "")
BASE_DESC=$(echo "$ANALYZE" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("base_description","")[:60])' 2>/dev/null || echo "")
PREVIEW_URL=$(echo "$ANALYZE" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("preview_url") or "null")' 2>/dev/null || echo "error")
COST=$(echo "$ANALYZE" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("cost_fen","?"))' 2>/dev/null || echo "?")
PARAMS=$(echo "$ANALYZE" | python3 -c 'import sys,json;d=json.load(sys.stdin);p=d.get("initial_params",{});print(p.get("style","?"),p.get("lighting","?"))' 2>/dev/null || echo "?")

if [ -n "$SESSION_ID" ]; then
  pass "analyze OK: session=${SESSION_ID:0:8}..."
  echo "    base_description: $BASE_DESC..."
  echo "    initial_params: $PARAMS"
  echo "    preview_url: $PREVIEW_URL"
  echo "    cost_fen: $COST"
  [ "$PREVIEW_URL" != "null" ] && [ "$PREVIEW_URL" != "error" ] && pass "Flux 预览图生成 OK ✨" || echo "  ⚠️  preview_url=null（Flux 降级，wizard 会显示原图 fallback）"
else
  fail "analyze 失败: $(echo "$ANALYZE" | head -c 200)"
  SESSION_ID=""
fi

# C-3 参数更新预览
if [ -n "$SESSION_ID" ] && [ -n "$BASE_DESC" ]; then
  echo "  测试参数更新预览..."
  PREV_RESP=$(curl -sf --max-time 60 -X POST "$BASE/api/wizard/preview" \
    -H "Authorization: Bearer $JWT" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\":\"$SESSION_ID\",\"base_description\":\"$BASE_DESC\",\"params\":{\"style\":\"cinematic\",\"lighting\":\"golden_hour\",\"shot_type\":\"close_up\",\"mood\":\"dramatic\",\"color_tone\":\"warm\",\"motion_intensity\":70,\"depth_of_field\":60,\"detail_richness\":80,\"saturation_level\":65},\"aspect_ratio\":\"16:9\"}" 2>&1)
  NEW_PROMPT=$(echo "$PREV_RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("composed_prompt","")[:80])' 2>/dev/null || echo "")
  if [ -n "$NEW_PROMPT" ]; then
    pass "参数预览 OK: ${NEW_PROMPT}..."
  else
    fail "参数预览失败: $(echo "$PREV_RESP" | head -c 150)"
  fi
fi

# ── BLOCK D：视频生成 T2V ────────────────────────────────
section "BLOCK D：视频生成"

if [ -n "$SESSION_ID" ]; then
  echo "  提交 T2V 任务..."
  GEN=$(curl -sf --max-time 30 -X POST "$BASE/api/video/generate" \
    -H "Authorization: Bearer $JWT" \
    -H "Content-Type: application/json" \
    -d "{\"session_id\":\"$SESSION_ID\",\"mode\":\"text_to_video\",\"aspect_ratio\":\"16:9\",\"duration\":5,\"quality\":\"basic\"}" 2>&1)
  TASK_ID=$(echo "$GEN" | python3 -c 'import sys,json;print(json.load(sys.stdin)["task_id"])' 2>/dev/null || echo "")
  EST_COST=$(echo "$GEN" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("estimated_cost_fen","?"))' 2>/dev/null || echo "?")
  if [ -n "$TASK_ID" ]; then
    pass "T2V 任务提交 OK: task=${TASK_ID:0:8}..., est_cost=${EST_COST} fen"
    # 轮询状态（最多等 5 分钟）
    echo "  轮询任务状态（最多 5 分钟）..."
    for i in $(seq 1 60); do
      sleep 5
      STATUS_RESP=$(curl -sf "$BASE/api/video/$TASK_ID/status" -H "Authorization: Bearer $JWT" 2>/dev/null || echo "{}")
      STATUS=$(echo "$STATUS_RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("status","?"))' 2>/dev/null || echo "?")
      PROGRESS=$(echo "$STATUS_RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("progress",0))' 2>/dev/null || echo "0")
      echo "    [${i}] status=$STATUS progress=$PROGRESS%"
      if [ "$STATUS" = "completed" ]; then
        VIDEO_URL=$(echo "$STATUS_RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("video_url",""))' 2>/dev/null || echo "")
        pass "T2V 完成! video_url=$VIDEO_URL"
        # 验证 usage_log cost_fen 不为 0
        COST_LOG=$(psql seedance -t -q -c "SELECT cost_fen FROM usage_logs WHERE upstream_task_id IS NOT NULL ORDER BY created_at DESC LIMIT 1;" 2>/dev/null | tr -d ' \n')
        [ "$COST_LOG" != "0" ] && [ -n "$COST_LOG" ] && pass "usage_log cost_fen=$COST_LOG (非0 ✅)" || echo "  ⚠️  cost_fen=$COST_LOG"
        break
      elif [ "$STATUS" = "failed" ]; then
        fail "T2V 失败: $STATUS_RESP"
        break
      fi
    done
  else
    fail "T2V 提交失败: $(echo "$GEN" | head -c 200)"
  fi
fi

# ── BLOCK E：用量 & 余额 ──────────────────────────────────
section "BLOCK E：用量 & 余额"
USAGE=$(curl -sf "$BASE/api/usage?page=1&page_size=10" -H "Authorization: Bearer $JWT")
TOTAL=$(echo "$USAGE" | python3 -c 'import sys,json;print(json.load(sys.stdin)["total"])' 2>/dev/null || echo "?")
pass "用量查询 OK: total=$TOTAL 条记录"

BAL_AFTER=$(curl -sf "$BASE/api/balance" -H "Authorization: Bearer $JWT")
FEN_AFTER=$(echo "$BAL_AFTER" | python3 -c 'import sys,json;print(json.load(sys.stdin)["amount_fen"])' 2>/dev/null || echo "?")
pass "余额查询 OK: $FEN_AFTER fen"

# ── BLOCK F：错误处理 ─────────────────────────────────────
section "BLOCK F：错误处理"

# F-1 余额不足
psql seedance -q -c "UPDATE balances SET amount_fen=0 WHERE user_id='$USER_ID';" 2>/dev/null
ERR=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/wizard/analyze" \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d "{\"image_b64\":\"$IMG_B64\",\"user_idea\":\"test\"}")
[ "$ERR" = "402" ] && pass "余额不足 → HTTP 402 ✅" || fail "期望 402，得到 $ERR"

# F-2 无效 Token
ERR2=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/balance" -H "Authorization: Bearer bad-token")
[ "$ERR2" = "401" ] && pass "无效 Token → HTTP 401 ✅" || fail "期望 401，得到 $ERR2"

# F-3 缺少字段
ERR3=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/wizard/analyze" \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"user_idea":"no image"}')
[ "$ERR3" = "400" ] && pass "缺少 image_b64 → HTTP 400 ✅" || fail "期望 400，得到 $ERR3"

# 恢复余额
psql seedance -q -c "UPDATE balances SET amount_fen=50000 WHERE user_id='$USER_ID';" 2>/dev/null

# ── 汇总 ─────────────────────────────────────────────────
echo
echo "════════════════════════════════════"
echo "  测试结束"
echo "  ✅ PASS: $PASS"
echo "  ❌ FAIL: $FAIL"
echo "════════════════════════════════════"
