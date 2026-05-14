# Seedance Wizard — 开发进度 & 上线计划

> 最后更新：2026-05-13（Phase 12 海外版 Railway 部署后）
> 完整开发记录见 `record.md`，架构决策见 `dialogue.md`

---

## 一、当前状态总览

### 已完成 ✅

| 模块 | 状态 | 备注 |
|------|------|------|
| 后端 API（认证/计费/向导/视频） | ✅ | 18/18 测试全绿 |
| 预览图生成（阿里云通义万象 Wanx） | ✅ | 替换 fal.ai，账单统一 |
| 视频生成（muapi.ai Seedance T2V/I2V） | ✅ | 计费正确 |
| Web Portal（Next.js 14） | ✅ | 登录/注册/仪表盘/充值/用量/API Key |
| ComfyUI 节点 + HTML 向导 | ✅ | 实机安装完成 |
| 国际化（zh-CN / en-US） | ✅ | next-intl |
| 海外版架构（DEPLOYMENT_REGION=intl） | ✅ | email + Google OAuth 架构就绪 |
| migrate.ts SQL 解析 | ✅ | 单引号 + 美元引号均正确处理 |
| 生产 build 验证 | ✅ | npx tsc 零错误，migrate failed=0 |
| contract/api-spec.yaml 完整性 | ✅ | 新增 /analyze 端点 + PromptParams schema + Balance.currency + nullable preview_url，YAML 格式修复 |
| Web Portal API 对接修复 | ✅ | ApiKey/Balance 字段名 snake_case→camelCase 规范化，手机号正则前后端对齐 |
| 服务器部署脚本 | ✅ | deploy/ 目录：nginx.conf + ecosystem.config.js + deploy.sh + update.sh + .env.production |
| 邮箱验证码（Resend） | ✅ | 替代短信，fallback 到 console mock |
| Git 仓库 + GitHub | ✅ | liuhongyi0/seedance-transfer (private) |
| Backend Railway 部署 | ✅ | seedance-transfer-production.up.railway.app |
| Web Portal Railway 部署 | ✅ | robust-mercy-production-80fc.up.railway.app |
| PostgreSQL Railway 托管 | ✅ | 自动注入 DATABASE_URL |

### 未完成 ❌

| 模块 | 状态 | 优先级 |
|------|------|------|
| **Backend 环境变量配置** | ❌ API Key 未填 | P0 — 立即 |
| **域名 see4dance.com DNS → Railway** | ❌ Namecheap CNAME 未配置 | P0 |
| **Resend 域名验证 see4dance.com** | ❌ DKIM 已验证，Resend 控制台待确认 | P0 |
| 短信验证码接入 | ❌ 仅 console mock，国内版延期 | P1 |
| 支付接入 | ❌ 充值页有 UI，按钮"即将上线" | P1 |
| 国内版部署（阿里云 ECS） | ❌ 待海外版稳定后 | P1 |
| 视频文件持久化存储 | ❌ 用 muapi CDN，不受控 | P1 |
| 监控/告警 | ❌ | P1 |
| Google OAuth 接入 | ❌ 架构就绪，GOOGLE_CLIENT_ID 未填 | P2 |
| Stripe 支付（海外版） | ❌ stub | P2 |

---

## 二、下一步执行计划（当前：2026-05-13）

### Step 1：Backend 环境变量（立即，5分钟）

在 Railway Backend Service → Settings → Variables 添加：

```
DEPLOYMENT_REGION=intl
JWT_SECRET=<node -e "console.log(require('crypto').randomBytes(64).toString('hex'))">
RESEND_API_KEY=re_KSEcahRk_NsTspRCBPLo73rTPiu5TurdV
RESEND_FROM_EMAIL=onboarding@resend.dev
DEEPSEEK_API_KEY=<待用户填入>
DASHSCOPE_API_KEY=<待用户填入>
MUAPI_KEY=<待用户填入>
FAL_KEY=<可选，已废弃>
```

### Step 2：域名 DNS 指向 Railway

1. Namecheap → Domain List → see4dance.com → Manage → Advanced DNS
2. 删除现有 A 记录
3. 添加 CNAME 记录：`@` → `robust-mercy-production-80fc.up.railway.app`
4. 等 DNS 生效（5-30分钟）
5. Railway Web Portal Service → Settings → Domains → 添加 `see4dance.com`

### Step 3：Resend 域名验证

1. Resend 控制台 → Domains → see4dance.com → 点 Verify
2. 验证通过后改 `RESEND_FROM_EMAIL=Seedance <noreply@see4dance.com>`

### Step 4：端到端测试

1. 浏览器打开 `https://see4dance.com`
2. 注册账号（邮箱 + 验证码）
3. 登录 → 仪表盘 → API Key 页
4. 如果有 API Key 配好，跑一次完整向导分析

> **LLM 可直接实现本节所有代码变更，用户只需完成控制台申请步骤。**

#### 用户需要先做（控制台操作）

1. 登录阿里云控制台 → 短信服务 → 申请签名（选"个人"类型，签名名称如"Seedance"）
2. 申请短信模板（验证码类）：`您的验证码为${code}，5分钟内有效。`
3. 审核通过后（1-2 工作日），在 RAM 控制台新建子账号，只授权 AliyunDysmsFullAccess 权限，获取 AccessKey ID + Secret
4. 填入 `backend/.env`（新增以下四行）：

```env
SMS_ACCESS_KEY_ID=<阿里云 AccessKey ID>
SMS_PROVIDER_KEY=<阿里云 AccessKey Secret>
SMS_SIGN_NAME=Seedance
SMS_TEMPLATE_CODE=SMS_xxxxxx
```

#### LLM 代码任务

**① 安装 SDK**

```bash
cd ~/ClaudeProject/seedance-transfer/backend
npm install @alicloud/dysmsapi20170525 @alicloud/openapi-client
```

**② 修改 `backend/src/config.ts`**

在 `config` 对象中已有 `smsProviderKey`，需补充三个字段：

```typescript
smsProviderKey: process.env.SMS_PROVIDER_KEY || '',
smsAccessKeyId: process.env.SMS_ACCESS_KEY_ID || '',   // 新增
smsSignName:    process.env.SMS_SIGN_NAME    || '',   // 新增
smsTemplateCode:process.env.SMS_TEMPLATE_CODE|| '',   // 新增
```

同时在 `validateConfig()` 中补充警告：

```typescript
if (!config.smsAccessKeyId || !config.smsTemplateCode) {
  warnings.push('SMS_ACCESS_KEY_ID / SMS_TEMPLATE_CODE 未设置，短信验证码将仅打印到控制台');
}
```

**③ 新建 `backend/src/services/sms.ts`**

```typescript
import Dysmsapi, { SendSmsRequest } from '@alicloud/dysmsapi20170525';
import OpenApi from '@alicloud/openapi-client';
import { config } from '../config';

let client: Dysmsapi | null = null;

function getClient(): Dysmsapi {
  if (!client) {
    const openApiConfig = new OpenApi.Config({
      accessKeyId:     config.smsAccessKeyId,
      accessKeySecret: config.smsProviderKey,
      endpoint:        'dysmsapi.aliyuncs.com',
    });
    client = new Dysmsapi(openApiConfig);
  }
  return client;
}

export async function sendSmsCode(phone: string, code: string): Promise<void> {
  // 未配置时 fallback 到 console mock
  if (!config.smsAccessKeyId || !config.smsTemplateCode) {
    console.log(`[SMS Mock] 手机号: ${phone}  验证码: ${code}`);
    return;
  }

  const req = new SendSmsRequest({
    phoneNumbers:  phone,
    signName:      config.smsSignName,
    templateCode:  config.smsTemplateCode,
    templateParam: JSON.stringify({ code }),
  });

  const resp = await getClient().sendSms(req);
  if (resp.body?.code !== 'OK') {
    throw new Error(`阿里云短信发送失败: ${resp.body?.code} — ${resp.body?.message}`);
  }
  console.log(`[SMS] 验证码已发送至 ${phone}，RequestId: ${resp.body?.requestId}`);
}
```

**④ 修改 `backend/src/routes/auth.ts`**

在文件顶部添加 import：
```typescript
import { sendSmsCode } from '../services/sms';
```

将 `/sms` 路由中的 console mock 整段替换为：
```typescript
// 生成验证码（逻辑不变）
const code = String(Math.floor(100000 + Math.random() * 900000));
smsStore.set(phone, { code, expires: Date.now() + config.smsCodeExpiryMs });

// 调用真实短信服务（未配置时自动 fallback 到 console）
await sendSmsCode(phone, code);

res.json({ message: '验证码已发送' });
```

注意：`/sms` 路由改为 `async`，并将整个函数体包裹在 try/catch 中（catch 调用 `next(err)`）。

**⑤ 验证**

```bash
# 未填 .env 时仍应 fallback 到 console，不报错
curl -X POST http://localhost:3000/api/auth/sms -H 'Content-Type: application/json' -d '{"phone":"13800000001"}'
# 期望：{"message":"验证码已发送"}，后端 console 打印验证码
```

---

### Step 3：虎皮椒支付接入（1-2 天）

> **选型：虎皮椒（xunhupay.com）— 个人开发者无需营业执照，支持支付宝+微信，手续费 1-2%**
> **LLM 可直接实现本节所有代码变更。**

**充值套餐定价（已定，写死在前端和后端）：**

| 套餐 key | 价格 | 额度 | 说明 |
|------|------|------|------|
| `lite` | ¥9.9 | 1,000 fen | 体验包 |
| `standard` | ¥49 | 6,000 fen | 标准包 |
| `pro` | ¥99 | 15,000 fen | 专业包 |
| `max` | ¥299 | 50,000 fen | 旗舰包 |

> 定价参考：T2V 5s basic = 155 fen ≈ ¥1.03；图片预览 = 2 fen ≈ ¥0.013

#### 用户需要先做

1. 注册 https://xunhupay.com，绑定个人支付宝/微信收款码
2. 创建应用，获取 `AppID` 和 `AppSecret`
3. 填入 `backend/.env`：

```env
XUNHUPAY_APPID=<虎皮椒 AppID>
XUNHUPAY_APPSECRET=<虎皮椒 AppSecret>
XUNHUPAY_NOTIFY_URL=https://你的域名/api/payment/notify
```

#### LLM 代码任务

**① `backend/src/config.ts` 新增三个字段**

```typescript
xunhupayAppId:     process.env.XUNHUPAY_APPID      || '',
xunhupayAppSecret: process.env.XUNHUPAY_APPSECRET  || '',
xunhupayNotifyUrl: process.env.XUNHUPAY_NOTIFY_URL || '',
```

**② 新建 `backend/src/services/xunhupay.ts`**

虎皮椒 API 文档：https://xunhupay.com/doc.html
签名算法：所有参数按 key 字典序拼接为 `key=val&...`，末尾加 `&appsecret=<secret>`，做 MD5 hex。

```typescript
import crypto from 'crypto';
import { config } from '../config';

// 套餐定义（与前端保持一致）
export const PACKAGES = {
  lite:     { price: 9.9,  fenAmount: 1000  },
  standard: { price: 49,   fenAmount: 6000  },
  pro:      { price: 99,   fenAmount: 15000 },
  max:      { price: 299,  fenAmount: 50000 },
} as const;
export type PackageKey = keyof typeof PACKAGES;

function sign(params: Record<string, string>): string {
  const sorted = Object.keys(params).sort().map(k => `${k}=${params[k]}`).join('&');
  const raw = `${sorted}&appsecret=${config.xunhupayAppSecret}`;
  return crypto.createHash('md5').update(raw).digest('hex');
}

export interface CreateOrderResult {
  orderId: string;    // 我方订单号
  payUrl:  string;    // 跳转支付页 URL（虎皮椒返回）
  qrCode?: string;    // 二维码 URL（可选）
}

export async function createOrder(
  packageKey: PackageKey,
  payType: 'alipay' | 'wechat',
  outTradeNo: string,   // 我方订单号，UUID
): Promise<CreateOrderResult> {
  const pkg = PACKAGES[packageKey];
  const params: Record<string, string> = {
    appid:        config.xunhupayAppId,
    out_trade_no: outTradeNo,
    total_fee:    String(pkg.price),
    title:        `Seedance 充值 - ${packageKey}`,
    time:         String(Math.floor(Date.now() / 1000)),
    notify_url:   config.xunhupayNotifyUrl,
    type:         payType,
    nonce_str:    crypto.randomBytes(8).toString('hex'),
  };
  params.hash = sign(params);

  const resp = await fetch('https://api.xunhupay.com/payment/do.html', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body:    new URLSearchParams(params),
  });

  const data = await resp.json() as any;
  if (data.return_code !== 'SUCCESS') {
    throw new Error(`虎皮椒下单失败: ${data.return_msg}`);
  }

  return {
    orderId: outTradeNo,
    payUrl:  data.pay_url  || data.url_qrcode,
    qrCode:  data.url_qrcode,
  };
}

export function verifyNotify(params: Record<string, string>): boolean {
  const { hash, ...rest } = params;
  const expected = sign(rest);
  return hash === expected;
}
```

**③ 重写 `backend/src/routes/payment.ts`**

需要新增的 DB 操作（在 `backend/src/db/queries.ts` 追加）：

```typescript
// 创建支付订单记录
export async function createPaymentOrder(
  userId: string, outTradeNo: string, packageKey: string,
  amountYuan: number, fenAmount: number
): Promise<void> {
  await query(
    `INSERT INTO payment_orders (user_id, out_trade_no, package_key, amount_yuan, fen_amount, status)
     VALUES ($1, $2, $3, $4, $5, 'pending')
     ON CONFLICT (out_trade_no) DO NOTHING`,
    [userId, outTradeNo, packageKey, amountYuan, fenAmount]
  );
}

// 核销订单（幂等）：同一 out_trade_no 只充值一次
export async function fulfillPaymentOrder(outTradeNo: string): Promise<boolean> {
  const result = await query(
    `UPDATE payment_orders SET status='paid', paid_at=NOW()
     WHERE out_trade_no=$1 AND status='pending'
     RETURNING user_id, fen_amount`,
    [outTradeNo]
  );
  if (result.rows.length === 0) return false; // 已处理或不存在
  const { user_id, fen_amount } = result.rows[0] as any;
  await query(
    `UPDATE balances SET amount_fen = amount_fen + $1, updated_at=NOW()
     WHERE user_id = $2`,
    [fen_amount, user_id]
  );
  return true;
}
```

同时在 `contract/db-schema.sql` 末尾追加建表语句：

```sql
CREATE TABLE IF NOT EXISTS payment_orders (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID        NOT NULL REFERENCES users(id),
  out_trade_no  VARCHAR(64) UNIQUE NOT NULL,
  package_key   VARCHAR(32) NOT NULL,
  amount_yuan   NUMERIC(10,2) NOT NULL,
  fen_amount    INTEGER     NOT NULL,
  status        VARCHAR(16) NOT NULL DEFAULT 'pending',
  paid_at       TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_payment_orders_user ON payment_orders(user_id);
```

payment.ts 路由实现：

```typescript
// POST /api/payment/create  — 下单（需登录）
// POST /api/payment/notify  — 虎皮椒异步回调（不需要登录，需验签）
// GET  /api/payment/packages — 套餐列表（不需要登录）
```

- `POST /api/payment/create`：从 `req.body` 取 `{ package_key, pay_type }`，生成 UUID 订单号，调 `createOrder()`，把订单写 DB，返回 `{ order_id, pay_url, qr_code }`
- `POST /api/payment/notify`：`verifyNotify()` 验签 → `fulfillPaymentOrder()` 充值 → 返回 `success`（虎皮椒要求纯文本 "success"）
- `GET /api/payment/packages`：直接返回 PACKAGES 常量（不扣费，不需要 auth）

**④ `backend/src/server.ts` 注册路由**

当前 payment 路由已注册（`app.use('/api/payment', paymentRoutes)`），内容替换后自动生效，无需修改 server.ts。

**⑤ Web Portal `app/recharge/page.tsx` 接入**

- 将套餐购买按钮的 onClick 从 Toast "即将上线" 改为调用 `POST /api/payment/create`
- 拿到 `pay_url` 后 `window.open(pay_url, '_blank')` 跳转虎皮椒收银台
- 轮询 `GET /api/balance` 每 3 秒检测余额是否增加，增加则提示"充值成功"

**⑥ 验证（未填配置时）**

```bash
# 套餐列表（无需登录）
curl http://localhost:3000/api/payment/packages

# 下单（需 JWT）
curl -X POST http://localhost:3000/api/payment/create \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"package_key":"lite","pay_type":"alipay"}'
# 填了 XUNHUPAY_APPID 后返回 pay_url，未填则返回 501
```

---

### Step 4：服务器部署（1-2 天）

**选型：阿里云 ECS**
- 理由：与 DashScope/muapi 同生态，延迟低，账单统一，国内备案方便
- 推荐配置：`ecs.c7.xlarge`（4核8G，¥400/月含5M带宽）或 `ecs.t6-c2m4.large`（2核4G，¥150/月）
- 系统：Ubuntu 22.04 LTS
- 数据库：阿里云 RDS PostgreSQL（¥70/月，高可用）或 ECS 自建 PostgreSQL

**部署架构：**
```
用户 → Nginx（HTTPS + 反代）
         ├→ :3000  Node.js 后端（PM2 守护）
         └→ :3001  Next.js 前端（PM2 守护）或 静态导出
```

**部署清单：**
- [ ] 购买 ECS（按量付费先试用）
- [ ] 绑定域名（如 app.seedance.ai），申请 SSL 证书（阿里云免费 DV 证书）
- [ ] 安装 Node.js 20 LTS + PM2 + Nginx + PostgreSQL
- [ ] 上传代码（git clone 或 rsync）
- [ ] 配置生产 `.env`（JWT_SECRET 换随机值，端口等）
- [ ] Nginx 配置反向代理 + HTTPS
- [ ] PM2 启动后端：`pm2 start dist/server.js --name seedance-backend`
- [ ] PM2 启动前端：`pm2 start npm --name seedance-frontend -- start`
- [ ] 设置 PM2 开机自启：`pm2 startup && pm2 save`

---

## 三、P1 计划（上线后补充）

### 视频文件持久化存储

当前视频 URL 来自 muapi.ai 的 CloudFront CDN，有效期未知。

**方案：阿里云 OSS**
- 视频任务完成后，后端自动下载并转存到 OSS bucket
- 生成带签名的永久 URL 返回给用户
- 成本约 ¥0.12/GB/月

### 监控与告警

```bash
# PM2 自带基础监控
pm2 monit

# 推荐：接入阿里云 ARMS 或 Sentry
npm install @sentry/node
```

告警项：API 错误率 > 5%、muapi 响应 > 30s、余额异常扣减

### 邮件通知（海外版）

**选型：SendGrid**
- 免费 100 封/天，满足初期
- 用途：注册欢迎邮件、充值成功确认、视频生成完成通知
- 接入：`npm install @sendgrid/mail`，填入 `SENDGRID_API_KEY`

---

## 四、基础设施费用估算（月）

| 项目 | 服务 | 费用 |
|------|------|------|
| 服务器 | 阿里云 ECS 2核4G | ¥150 |
| 数据库 | 阿里云 RDS PostgreSQL（可选，ECS 自建免费） | ¥70 |
| 短信 | 阿里云 SMS（1000条/月） | ¥45 |
| 存储 | 阿里云 OSS（10GB） | ¥1.2 |
| SSL | 阿里云免费 DV 证书 | ¥0 |
| **AI 服务（按用量）** | DashScope + muapi | 按用量 |
| **合计（固定部分）** | | **≈ ¥270/月** |

---

## 五、历史测试记录（存档）

> 以下为开发阶段测试记录，供参考。生产环境测试使用自动化测试脚本 `run-tests.sh`。

### 测试结果（2026-05-12 最终版）

```
BLOCK A 认证流程:     18/18 ✅
BLOCK B 账户管理:     ✅
BLOCK C 向导分析:     ✅（Wanx 预览图生成 OK ✨）
  preview_url: https://dashscope-result-*.aliyuncs.com/...
  cost_fen: 4（qwen=1 + deepseek=2 + wanx=1）
BLOCK D 视频生成 T2V: ✅（1次轮询完成，cost_fen=155）
BLOCK E 用量计费:     ✅
BLOCK F 错误处理:     ✅（402/401/400 全正确）
```

### 已修复 Bug 汇总

| Phase | Bug | 修复 |
|-------|-----|------|
| 7 | muapi Flux 404 | fal.ai → Wanx 双路由降级 |
| 7 | Seedance request_id 字段缺失 | 添加可选字段 |
| 7 | Seedance outputs/output 字段不匹配 | `outputs?.[0] \|\| output?.[0]` |
| 7 | I2V image_b64 传 null | 优先使用 state.imageB64 |
| 7 | analyze Flux 失败不退费 | 先操作后扣费 + Flux 独立 try/catch |
| 8 | fal.ai 余额耗尽 | 切换阿里云通义万象为主路由 |
| 10 | migrate.ts 单引号 SQL 解析 | 新增 inSingleQuote 状态机 |
| 10 | fal.ai HTTP 403 + muapi 404 | Wanx 为主路由，fal.ai 为备用 |

### 集成测试运行方式

```bash
# 快速重跑（后端已在运行）
bash ~/ClaudeProject/seedance-transfer/run-now.command

# 重启后端 + 全量测试
bash ~/ClaudeProject/seedance-transfer/restart-and-test.command

# 结果文件
cat /tmp/test-results.txt
```

---

## 六、手动测试命令参考

### 前置条件

```bash
# 1. PostgreSQL 运行中
brew services list | grep postgresql

# 2. 后端运行中
curl http://localhost:3000/health

# 3. 后端启动（如未运行）
cd ~/ClaudeProject/seedance-transfer/backend
npm run dev > /tmp/backend.log 2>&1 &
```

### 认证

```bash
# 发送验证码（验证码打印到后端 console）
curl -s -X POST http://localhost:3000/api/auth/sms \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800000001"}' | python3 -m json.tool

# 登录
curl -s -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800000001","password":"Test1234!"}' | python3 -m json.tool

export JWT="<access_token>"
```

### 向导分析

```bash
curl -s -o /tmp/test.jpg "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400"
export IMG_B64="data:image/jpeg;base64,$(base64 -i /tmp/test.jpg | tr -d '\n')"

curl -s -X POST http://localhost:3000/api/wizard/analyze \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{\"image_b64\":\"$IMG_B64\",\"user_idea\":\"高端商业广告\",\"aspect_ratio\":\"16:9\"}" \
  | python3 -m json.tool
```

### 海外版验证

```bash
cd ~/ClaudeProject/seedance-transfer/backend
DEPLOYMENT_REGION=intl npm run dev > /tmp/backend-intl.log 2>&1 &
curl -s http://localhost:3000/health | python3 -m json.tool
# 期望: {"region":"intl","currency":"USD",...}
```
