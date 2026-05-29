# Seedance Studio — 开发进度 & 上线计划

> 最后更新：2026-05-23（Railway 重部署 + Stripe 支付 + R2 存储 全部就绪）
> 完整上下文见 `Seedance/CLAUDE.md`，本文件仅跟踪 TODO

---

## 当前部署

| 项目 | 域名 | 状态 |
|------|------|------|
| Python 后端 + Portal | https://see4dance.com | ✅ Online |
| PostgreSQL | Railway 托管，内网 | ✅ Connected |
| Stripe 支付 | 测试模式 | ✅ E2E 打通 |
| R2 对象存储 | Cloudflare，10GB 免费 | ✅ |

Railway 项目：`seedance-studio`（9fe7b138），旧项目 `eloquent-recreation` 待清理。

---

## 已完成 ✅

| 模块 | 内容 |
|------|------|
| FastAPI 后端 | 35+ 端点，5 步视频管线全链路 |
| PostgreSQL 持久化 | PG → Redis → 内存三层降级，自动建表 |
| 用户认证 | 注册/登录/JWT HS256/7天过期 |
| Portal 主页 | Landing → 登录注册 → Dashboard → 充值 |
| Stripe Checkout | 创建 Session，跳转支付页 |
| Stripe Webhook | 签名验证 → 自动充值 → 写 transactions 表 |
| 计费系统 | 任务提交扣款，异常退款，4 种任务全接入 |
| R2 对象存储 | boto3 s3v4，imgbb 降级 |
| 视频分享链接 | /share/{id} 公开查看页 |
| 移动端适配 | portal.html + studio @media 断点 |
| Docker Compose | ECS 国内部署：postgres + backend + nginx |
| deploy-ecs.sh | ECS 一键部署脚本 |
| 内存优化 | DB pool min=1/max=5，uvicorn concurrency=20 |
| 计费 count 限制 | 图片生成 1-4 张，防止并发崩溃 |
| domain 绑定 | see4dance.com → Railway backend |
| Stripe Webhook URL | 更新为 see4dance.com，验签正常 |
| i18n 双语 | portal + studio CSS 方案 |
| 步骤四音乐 | EvoLink Suno v4 API 真实调用 |
| 旧 Railway 项目清理 | `eloquent-recreation` 已删除 |
| 视频持久化存储 | POST /api/upload/video → R2 永久存储 |
| 步骤二调色预览 | CSS 滤镜实时预览 + before/after 对比切换 |
| 移动端适配完善 | 三个断点 (900/700/480px)，全步骤折叠 |
| 模型选择权 | 12 个模型可选，动态定价 |
| Google OAuth | Google Identity Services 已配通 |

---

## 未完成 ❌

| 模块 | 优先级 | 说明 |
|------|--------|------|
| GitHub OAuth | P1 | 前端按钮待加，后端待对接 |
| ECS 国内部署 | P1 | 代码就绪，需阿里云 ECS 实例 |
| 微信支付 | P1 | webhook 占位，返回 501 |
| Session 过期清理 | P2 | 需定期清理 expires_at 过期记录 |
| 监控/告警 | P2 | 无 |

---

## 环境变量速查（Railway）

所有变量已通过 `railway variable set --service backend` 配置：

| 变量 | 来源 |
|------|------|
| DATABASE_URL | `${{Postgres.DATABASE_URL}}` |
| STRIPE_SECRET_KEY | Stripe Dashboard |
| STRIPE_WEBHOOK_SECRET | Stripe Dashboard |
| R2_* | Cloudflare R2 |
| EVOLINK_API_KEY | EvoLink 控制台 |
| VOLC_API_KEY | 火山引擎方舟平台 |
| IMGBB_API_KEY | imgbb.com |
| JWT_SECRET | 本地生成 |
| BASE_URL | Railway 自动 |
