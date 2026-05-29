# Seedance Studio

5 步 AI 视频创作工作台。单文件前端 + FastAPI 后端，对接 EvoLink 和火山引擎。

**生产域名**: https://see4dance.com  
**Railway 项目**: `seedance-studio`（9fe7b138-8f4a-465c-891f-68312ea6d2e9），workspace `liuhongyi0's Projects`  
**部署区域**: intl（USD / Stripe / R2）

---

## 项目结构

```
Seedance/
  railway.json           — Railway 部署配置（Dockerfile builder）
  seedance-studio.html   — 前端（单文件，~160KB，含嵌入式 i18n + SSE 客户端）
  backend/
    main.py              — FastAPI 入口，lifespan 管理 httpx + DB pool
    config.py            — DEPLOYMENT_REGION 驱动多区域配置（cn / intl）
    db.py                — asyncpg 连接池（ssl=False，Railway 内网不启用 SSL）
    store.py             — PG → Redis → 内存 三层降级 Session/User/Transaction 存储
    schema.sql           — DDL：users / transactions / sessions / shares
    sse_broker.py        — SSE 任务状态推送 Broker
    .env                 — 本地 API Keys（生产用 Railway Variables）
    requirements.txt     — Python 依赖（asyncpg, stripe, boto3, ...）
    Dockerfile           — 后端容器镜像（python:3.11-slim）
    docker-compose.yml   — ECS 国内部署：postgres + backend + nginx
    nginx.conf           — 前端静态服务 + /api/* 反向代理 + SSE 特殊配置
    deploy-ecs.sh        — ECS 一键部署脚本
    static/
      portal.html        — 主页（Landing → 登录注册 → Dashboard → 充值）
      seedance-studio.html — AI 工作台
    routers/
      auth.py            — 注册/登录/me，JWT HS256 7天过期
      payment.py         — 定价/dashboard/Stripe Checkout/Webhook
      image.py           — 图片生成 + 计费扣款
      video_draft.py     — 视频草稿 + 计费扣款
      music.py           — 音乐生成 + 计费扣款
      final_video.py     — 最终成片 + 计费扣款 + 分享链接
      session.py         — 会话管理
      sse.py             — SSE 实时推送
    services/
      storage.py         — R2 对象存储（boto3 s3v4）+ imgbb 降级
      billing.py         — 计费：calculate_cost / charge / refund
      prompt_builder.py
      translate.py
      color_to_prompt.py
```

---

## Railway 部署（生产）

### 当前服务

| 服务 | 状态 | URL |
|------|------|-----|
| backend | Online | https://see4dance.com |
| Postgres | Online | 内网 postgres.railway.internal:5432 |

### 环境变量（railway variable set --service backend）

| 变量 | 值 |
|------|-----|
| DEPLOYMENT_REGION | intl |
| DATABASE_URL | ${{Postgres.DATABASE_URL}} |
| EVOLINK_API_KEY | sk-7YfN1u8ztRKxgS9x1... |
| VOLC_API_KEY | ark-db62586a-3bcc-46f7... |
| IMGBB_API_KEY | 47c07a6ceac0e884... |
| JWT_SECRET | d28e20a2cbacd25b... |
| STRIPE_SECRET_KEY | sk_test_51TZSZkR18Ran... |
| GOOGLE_CLIENT_ID | (需在 Google Cloud Console 创建 OAuth 2.0 客户端) |
| STRIPE_WEBHOOK_SECRET | whsec_F2yag3WLx6s6ckl... |
| R2_ACCESS_KEY_ID | c7cde21f9706e604f0f... |
| R2_SECRET_ACCESS_KEY | f45b5dc042d87bd534... |
| R2_ENDPOINT | https://73d9b47a2abfe793fbf290e4c22e1c24.r2.cloudflarestorage.com |
| R2_BUCKET | seedance-studios |
| R2_PUBLIC_BASE | https://pub-e1708804800f4e0dbfac4e2006efa5fc.r2.dev |
| BASE_URL | https://backend-production-fe60b.up.railway.app |

### Stripe Webhook
- URL: `https://see4dance.com/api/payment/stripe/webhook`
- Events: `checkout.session.completed`

### 部署命令

```bash
cd Seedance
export PATH="$HOME/.local/bin:$PATH"
railway up --detach --json    # 推送本地代码
```

### ⚠️ 关键注意

- **`railway up` 必须从 Seedance 目录运行**，且必须已 link backend 服务
- 首次 `railway up` 若不指定 `--service`，会部署到已 link 的服务（可能覆盖数据库！）
- PostgreSQL 重建后需重新 `railway variable set` 更新 DATABASE_URL 引用
- `railway domain` 命令需要特殊权限，添加自定义域名建议通过 Web 控制台

---

## Docker Compose 部署（ECS 国内版）

```bash
cd backend
docker compose up -d --build
```

- 前端 nginx 监听 :80
- 后端 uvicorn 监听 :8000
- SSE `/api/sse/*` 已关闭 nginx 缓冲

手动启动（不用 Docker）：
```bash
cd backend
pip install -r requirements.txt
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 数据库

### PostgreSQL（生产）

- Railway 托管，`postgres.railway.internal:5432`
- 连接池：asyncpg，min_size=1，max_size=5
- **ssl=False**：Railway 内网 PostgreSQL 拒绝 SSL 升级
- DDL 在 `schema.sql`，首次启动自动执行 `store.init_schema()`

### 三层降级

```
PostgreSQL（DATABASE_URL 存在）
  → Redis（REDIS_URL 存在但无 PG）
    → 内存 dict（本地开发最后降级）
```

---

## Stripe 支付

### 套餐映射

| package_id | amount_subunit | credits | 名称 |
|------------|---------------|---------|------|
| starter | 700 ($7) | 50 | Starter |
| standard | 1800 ($18) | 200 | Standard |
| pro | 5200 ($52) | 800 | Pro |

### 支付流程

1. 前端 `POST /api/payment/create-checkout` → 创建 Stripe Checkout Session
2. 用户跳转 Stripe 支付页，完成支付
3. Stripe 回调 `POST /api/payment/stripe/webhook` → 验签 → `store.topup_balance()`
4. `topup_balance` 在 PG 事务中 UPDATE balance + INSERT transaction

### ⚠️ Stripe SDK v9+ 注意

`construct_event` 返回的 `event["data"]["object"]` 是 **StripeObject**，不支持 `.get()` 字典方法。必须先 `session.to_dict()` 转换后再访问 `metadata`、`amount_total` 等字段。

---

## R2 对象存储

- boto3 S3 client，签名版本 s3v4，region=auto
- Bucket: `seedance-studios`
- 上传后公网 URL: `{R2_PUBLIC_BASE}/{prefix}/{uuid}.ext`
- R2 未配置时降级到 imgbb

---

## 计费系统（`services/billing.py`）

- `calculate_cost(task_type, **params)` → 返回 subunit 金额
- `charge(user_id, task_type, amount, meta)` → store.topup_balance 负数扣款
- `refund(user_id, task_type, amount, meta)` → store.topup_balance 正数退款
- 任务提交时扣款，异常时退款（所有 router 均已接入）

### 定价速查

| 任务 | intl (USD) | cn (CNY) |
|------|-----------|----------|
| 图片每张 | $0.03 | ¥0.22 |
| 视频草稿每个 | $0.38 | ¥2.70 |
| 音乐每个 | $0.01 | ¥0.10 |
| 最终成片 1080p/s | $0.30 | ¥2.13 |

---

## 关键技术约束

- EvoLink 通过 `GET /v1/tasks/{id}` 统一轮询；火山引擎 Seedance 2.0 使用 multimodal `content[]` 数组
- 图片 TOS 签名 URL 需经 R2/imgbb 中转后给 EvoLink 使用
- 视觉描述必须走火山引擎 ARK（`doubao-1-5-vision-pro-32k-250115`）
- 所有 Router 的 store 调用必须 `await`
- 轮询超时应 `continue` 而非 crash；`MAX_POLL_DRAFT=100`（300s），`MAX_POLL_FINAL=200`（600s）
- SSE 推送在 nginx 中必须关闭 `proxy_buffering`
- 图片生成 count 限制 1-4（防止并发过多导致内存溢出）
- uvicorn 启动参数：`--limit-concurrency 20 --limit-max-requests 2000 --backlog 50`

---

## 待完成

### 国际版（intl / see4dance.com）

| 项目 | 状态 | 说明 |
|------|------|------|
| Google OAuth | ⚠️ 待配置 | 后端已对接，前端按钮已就位，需在 Railway 设置 `GOOGLE_CLIENT_ID` 才会显示按钮 |
| 步骤四音乐 | ✅ 已接入 | EvoLink Suno v4 API 真实调用（已移除 Mock `or True`） |
| 视频上传持久化 | ✅ 已实现 | `POST /api/upload/video` → R2 永久存储 |
| 步骤二调色预览 | ✅ 已实现 | CSS 滤镜实时预览 + before/after 对比切换 |
| 移动端适配 | ✅ 已完成 | 三个断点 (900/700/480px)，全步骤多列→单列折叠 |
| 旧 Railway 项目 | ✅ 已清理 | `eloquent-recreation` 已删除 |
| Stripe 支付 | ✅ 正常 | Webhook + Checkout 完整闭环 |
| 模型选择权 | ✅ 已上线 | 12 个模型可选，动态定价 |

### 国内版（cn / 暂缓）

| 项目 | 状态 | 说明 |
|------|------|------|
| ECS 国内部署 | ⏸️ 暂缓 | docker-compose + nginx 配置已完成，待推送 |
| 微信支付 | ⏸️ 暂缓 | webhook 端点返回 501，需对接微信支付 API |
