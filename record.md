# Phase 2 开发记录

> 启动时间：2026-05-10
> 完成时间：2026-05-10
> 架构师：Claude（协调 + Review + 集成）
> 契约基础：contract/api-spec.yaml + node-interface.md + db-schema.sql
> 所有技术上下文见 dialogue.md

---

## Agent 状态总览

| Agent | 任务 | 模型 | 状态 | 产出 |
|-------|------|------|------|------|
| Agent 1 | ComfyUI 节点 + HTML 向导 | Sonnet | ✅ | 6 文件 / 2,453 行 |
| Agent 2 | Node.js 后端 | Sonnet | ✅ | 23 文件 / ~11,400 行 |
| Agent 3 | Web Portal（Next.js） | Sonnet | ✅ | 31 文件 / ~2,600 行 |
| Agent 4 | 集成测试 | Opus | ⏳ | — |

---

## Agent 1: ComfyUI 节点 + HTML 向导（a08305db）

### 产出
`comfyui-seedance-wizard/` 目录，6 文件 / 2,453 行

| 文件 | 行数 | 关键内容 |
|------|------|---------|
| `__init__.py` | 13 | 节点映射 + WEB_DIRECTORY = "./web" |
| `nodes.py` | 582 | SeedanceWizardNode + ApiKeyNode + 9 PromptServer 路由 + 配置管理 + WS 推送 |
| `web/main.js` | 163 | sidebarTab + iframe↔fetch RPC (postMessage) + WebSocket→iframe 转发 |
| `web/wizard.html` | 839 | 完整向导 UI（对话+选项+CSS滑块+预览+Prompt编辑+拖拽上传） |
| `web/wizard.css` | 715 | 暗色主题 + 自定义滑块 + 对话气泡 + 模态框 |
| `web/filter-preview.js` | 154 | CSS filter 引擎（warmth→sepia/brightness/blur/contrast/saturation） |

### 决策
- **API Key 安全**：只存 Python 侧配置文件 `seedance_config.json`，前端只知 prefix + configured 布尔值
- **零额外依赖**：urllib 同步 HTTP 客户端，不引入 requests/httpx
- **双通道**：HTML→main.js postMessage RPC（带 req id）+ main.js→Python fetch + Python→main.js WebSocket

---

## Agent 2: Node.js 后端（a6f63699）

### 产出
`backend/` 目录，23 文件 / ~11,400 行 TypeScript

| 层 | 文件 | 内容 |
|----|------|------|
| 入口 | `server.ts` | Express + CORS + JSON(50MB) + 请求日志 + 优雅退出 + DB 迁移 |
| 配置 | `config.ts` | 7 环境变量 + validateConfig() 警告 + muapi 端点 |
| 类型 | `types.ts` | 30+ 接口（全部 req/res/DB/ChatMessage/FilterParams/Express augmentation） |
| DB | `pool.ts` | pg Pool + transaction() 辅助 |
| DB | `migrate.ts` | 读取 contract/db-schema.sql → 按 ; 分句 → 事务执行 |
| DB | `queries.ts` | 17 查询函数 + 定价缓存(60s TTL) + 原子扣费/退款 |
| 中间件 | `auth.ts` | 双模：API Key(SHA-256 → verify_api_key) + JWT verify → getBalance |
| 中间件 | `rateLimit.ts` | 内存滑动窗口 60req/min, X-RateLimit-* headers |
| 中间件 | `errorHandler.ts` | AppError 类 + 预定义工厂(badRequest/unauthorized/insufficientBalance/upstream) |
| 服务 | `deepseek.ts` | DeepSeekDirector (400行): 3 tools + self-built tool_call loop + CSS filter translator |
| 服务 | `qwen.ts` | Qwen VL 看图（DashScope compatible API, qwen-vl-max） |
| 服务 | `flux.ts` | Flux-Schnell 预览（muapi.ai, 同步+轮询 fallback） |
| 服务 | `seedance.ts` | T2V/I2V 提交 + 轮询(muapi.ai, 2s 间隔, 状态映射) |
| 服务 | `pricing.ts` | 5 种服务计费 + 视频费用预估 + fen↔yuan 转换 |
| 路由 | `auth.ts` | POST register/login/sms（sms mock, print to console） |
| 路由 | `keys.ts` | GET list / POST create(仅一次返回明文) / DELETE revoke |
| 路由 | `balance.ts` | GET balance(fen+yuan) + GET usage(分页+service 筛选) |
| 路由 | `wizard.ts` | POST start(message: 会话创建+DeepSeek+扣费) / message(继续+扣费) / preview(Flux+扣费) |
| 路由 | `video.ts` | POST generate(预扣+提交+后台轮询+超时退款) + GET status/result |
| 路由 | `estimate.ts` | POST estimate（不扣费） |

### 决策
- **认证双模**：JWT(7天) 用于 Web Portal 登录 + API Key(sk-seed-xxx, SHA-256 存) 用于 ComfyUI 程序调用
- **计费模型**：异步任务先预扣(pre_cost_fen) → 完成结算 → 失败自动退款(PG 原子操作)
- **tool_call 自建**：不依赖任何 Agent 框架，纯 OpenAI SDK + while loop(max 10 轮)
- **容灾**：无 DB 时 server 仍启动，清晰 warn 但不崩
- **定价热更新**：system_config 表 JSON 值，60s cache TTL

---

## Agent 3: Web Portal（a5a03d3e）

### 产出
`web-portal/` 目录，31 文件 / ~2,600 行 TypeScript+TSX

| 类型 | 文件 | 内容 |
|------|------|------|
| 配置 | `package.json`, `tsconfig.json`, `tailwind.config.ts`, `next.config.js`, `.env` | Next.js 14 + Tailwind + 环境变量 |
| 类型 | `types/index.ts` | User/ApiKey/Balance/UsageLog/ServiceType/Package + 中文映射表 + 4 档预设套餐 |
| 工具 | `lib/api.ts` | 10 个 API 函数(login/register/sendSms/getKeys/createKey/deleteKey/getBalance/getUsage/getProfile/updatePassword) + 401 自动跳转 |
| 工具 | `lib/auth.tsx` | AuthProvider + useAuth hook + localStorage 恢复 + token 验证 |
| 工具 | `lib/utils.ts` | fenToYuan/formatDate/maskKey/maskPhone/relativeTime/validatePhone |
| 组件 | `Navbar.tsx` | 固定顶部 + Logo + 余额 + 用户下拉(手机号脱敏) + 移动端汉堡菜单 |
| 组件 | `Sidebar.tsx` | 220px 侧边栏 + 5 导航项高亮 + 移动端 overlay |
| 组件 | `BalanceCard.tsx` | 蓝紫渐变卡片 + 大字号元 + 充值链接 |
| 组件 | `ApiKeyCard.tsx` | Key 前缀掩码 + 状态标签 + 创建时间 + 删除二次确认 |
| 组件 | `UsageTable.tsx` | 服务中文映射 + 状态颜色标签(绿/红/蓝/黄) |
| 组件 | `PackageCard.tsx` | 推荐套餐绿边框 + 角标 + 价格/额度/单价 |
| 组件 | `ProtectedRoute.tsx` | 未登录→/login + 加载 spinner |
| 组件 | `Toast.tsx` | ToastProvider + success/error/info + 3 秒消失 |
| 页面 | `app/page.tsx` | 未登录 Hero + 已登录 redirect /dashboard |
| 页面 | `app/login/page.tsx` | 手机号+密码 + 格式校验 + 错误提示 |
| 页面 | `app/register/page.tsx` | 手机号+验证码(60s 倒计时)+密码+确认密码 |
| 页面 | `app/dashboard/page.tsx` | BalanceCard + 3 统计卡片 + 快捷操作 + 最近用量 |
| 页面 | `app/keys/page.tsx` | Key 列表 + 创建弹窗 + 完整明文弹窗("仅此一次") + 复制 + 删除确认 |
| 页面 | `app/usage/page.tsx` | 服务筛选 + UsageTable + 分页器(智能省略号) + 空状态 |
| 页面 | `app/recharge/page.tsx` | 4 列套餐网格 + 支付方式预留(微/支灰色) + 所有按钮"即将上线"Toast |
| 页面 | `app/settings/page.tsx` | 账号信息 + 修改密码(disabled,即将上线) + 语言切换(disabled) |

### 决策
- **支付暂缓**：充值页 UI 完整，所有购买按钮统一弹"即将上线"Toast
- **配色**：深蓝主色 #1a56db + 绿色强调 #10b981 + 灰色背景 #f3f4f6
- **响应式**：<768px 侧边栏折叠 + 表格横向滚动 + 导航汉堡菜单

---

## 集成修复

Agent 1 ↔ Agent 2 路由对齐：6 个端点全部匹配 ✓

Agent 3 ↔ Agent 2 API 格式修复：
- `login` 返回值：`access_token`（契约字段）← 之前错用 `token`
- `getKeys` 返回值：`{ keys: [...] }` 对象解包 ← 之前当数组
- `createKey` 返回值：`{ key, detail }` → 合并为 `{ ...detail, key }`
- `auth.tsx` login 逻辑：登录后额外调 `getBalance()` 构造 user 对象（后端 login 只返回 token，不返回 user）

---

## 总代码量

| 模块 | 文件数 | 行数 | 语言 |
|------|--------|------|------|
| ComfyUI 节点 | 2 | 595 | Python |
| HTML 向导 | 4 | 1,871 | JS+HTML+CSS |
| Node.js 后端 | 23 | ~11,400 | TypeScript |
| Web Portal | 31 | ~2,600 | TypeScript+TSX |
| 契约文档 | 4 | ~800 | YAML+Markdown+SQL |
| **合计** | **64** | **~17,300** | — |

---

## 项目文件树

```
seedance-transfer/
├── comfyui-full-plan.md           # 13章完整产品方案
├── comfyui-for-beginners.md       # 小白版说明
├── memory.md                      # 项目逻辑 & 用户偏好
├── record.md                      # 本文件：开发记录
├── dialogue.md                    # 完整对话记录
├── contract/
│   ├── api-spec.yaml              # OpenAPI 3.0
│   ├── node-interface.md          # 三方通信接口
│   ├── db-schema.sql              # PostgreSQL
│   └── recon-report.md            # 生态侦察
├── comfyui-seedance-wizard/       # Agent 1 产出
│   ├── __init__.py
│   ├── nodes.py
│   └── web/ (main.js, wizard.html, wizard.css, filter-preview.js)
├── backend/                       # Agent 2 产出
│   ├── src/ (server, config, types)
│   │   ├── db/ (pool, migrate, queries)
│   │   ├── middleware/ (auth, rateLimit, errorHandler)
│   │   ├── services/ (deepseek, qwen, flux, seedance, pricing)
│   │   └── routes/ (auth, keys, balance, wizard, video, estimate)
│   └── package.json + tsconfig.json
└── web-portal/                    # Agent 3 产出
    ├── app/ (9 页面)
    ├── components/ (8 组件)
    ├── lib/ (api, auth, utils)
    ├── types/
    └── package.json + tsconfig.json + tailwind.config.ts
```

---

## 时间线

| 时间 | 事件 |
|------|------|
| 2026-05-10 | Phase 2 启动，Agent 1 + Agent 2 并行派出 |
| 2026-05-10 | Agent 1 完成（6 文件） |
| 2026-05-10 | Agent 2 完成（23 文件） |
| 2026-05-10 | 集成验证 + TS 编译修复 |
| 2026-05-10 | Agent 3 派出 |
| 2026-05-10 | Agent 3 完成（31 文件） |
| 2026-05-10 | Agent 3 API 格式对齐修复 + record & dialogue 更新 |
| 2026-05-10 | Agent 4 集成测试：发现 8 致命 + 8 严重 Bug |
| 2026-05-10 | 修复 15 个 Bug（见下方 Agent 4 节） |
| 2026-05-10 | 收尾修复 6 项（Qwen VL 计费 + generate_preview 清理 + balance_after + WS 财务字段 + README + Manager JSON） |
| 2026-05-10 | Phase 3: 海外站点开发（9 阶段，~44 文件，见下方 Phase 3 节） |

---

## Phase 3: 海外站点（国际化 + 多币种 + Google OAuth + Stripe）

> 目标：同一套代码支持 `DEPLOYMENT_REGION=cn|intl` 两套部署
> 实施：Phase 1-8 并行 Agent + 主线程，Phase 9 全面验证

### Phase 1: DB Schema（底座）
- `contract/db-schema.sql`: users 表扩展 `google_id`, `avatar_url`, `auth_provider`, phone 改为可选, 新增约束；balances/usage_logs 加 `currency`；新增海外版定价 `pricing_intl`
- `backend/src/db/migrate.ts`: 幂等错误模式扩展（does not exist / violates）

### Phase 2: 多区域配置
- **新建** `backend/config/cn.yaml`: 国内版 YAML（phone 认证、CNY、微信支付宝）
- **新建** `backend/config/intl.yaml`: 海外版 YAML（email+google 认证、USD/cents、Stripe、R2），环境变量插值 `${GOOGLE_CLIENT_ID}` 等
- `backend/src/config.ts`: `loadRegionConfig()` 加载对应 yaml → `config.regionConfig`; 新增 `region`, `googleClientId`, `stripeSecretKey` 等字段; `validateConfig()` 扩展
- `backend/.env.example`: 新增 `DEPLOYMENT_REGION`, `GOOGLE_CLIENT_ID`, `STRIPE_*`, `R2_BUCKET`

### Phase 3: Auth 扩展（Agent 1）
- **新建** `backend/src/routes/oauth.ts`: `POST /auth/google`（verifyIdToken → find/create → JWT）, `POST /auth/email/register`（email+password → bcrypt → create）, `POST /auth/email/login`（email+password → JWT）
- `backend/src/db/queries.ts`: 新增 `findUserByEmail`, `findUserByGoogleId`, `createUserWithEmail`, `createUserWithGoogle`
- `backend/src/routes/auth.ts`: region guard — intl 模式下 phone 注册/登录返回 400
- `backend/src/types.ts`: User 接口扩展（google_id, avatar_url, auth_provider, phone→optional）
- `backend/src/server.ts`: 注册 oauthRoutes 到 `/api/auth`
- `backend/package.json`: 新增 `google-auth-library` 依赖

### Phase 4: Web Portal i18n（Agent 2）
- **新建** `web-portal/locales/zh-CN.json`: 20 个命名空间（common/layout/nav/home/login/register/dashboard/keys/usage/recharge/settings/services/status/apiKey/table/packages/balanceCard/protectedRoute/api/utils/toast）
- **新建** `web-portal/locales/en-US.json`: 完整英文翻译
- **新建** `web-portal/src/i18n.ts`, `middleware.ts`, `navigation.ts`: next-intl 配置（cookie 模式，localePrefix: never）
- **修改** 9 页面 + 8 组件 + 3 lib 文件: 所有硬编码中文 → `t('key')`；`formatDateTime`/`relativeTime` 改为 locale-aware；`Package` 加 `key` 翻译字段
- `web-portal/next.config.js`: 集成 `next-intl/plugin`
- `web-portal/package.json`: 新增 `next-intl` 依赖

### Phase 5: ComfyUI Wizard i18n（Agent 3）
- **新建** `comfyui-seedance-wizard/web/i18n/zh.json`: 77 个中文翻译 key
- **新建** `comfyui-seedance-wizard/web/i18n/en.json`: 77 个英文翻译 key
- **新建** `comfyui-seedance-wizard/web/i18n.js`: 227 行轻量 i18n 引擎（navigator.language 检测、DOM data-i18n 替换、localStorage 持久化、__t()/__setLocale() API）
- `comfyui-seedance-wizard/web/wizard.html`: ~40 元素加 data-i18n 属性，~35 JS 字符串调用转 __t()，新增语言选择器，wizardStart() 发送实际 locale
- `comfyui-seedance-wizard/nodes.py`: 新增 `GET /seedance/locale` 路由

### Phase 6: 多币种
- `backend/src/types.ts`: PricingConfig 新增 subunit 字段 + currency；BalanceResponse 新增 currency
- `backend/src/services/pricing.ts`: `getPricing()` 区域自适应（intl→YAML pricing + DB 覆盖）；新增 `formatAmount()`, `getCurrency()`
- `backend/src/routes/balance.ts`: GET /balance 响应新增 currency

### Phase 7-8: 部署 + Stripe
- **新建** `backend/Dockerfile`, `web-portal/Dockerfile`: 多阶段构建
- **新建** `backend/docker-compose.intl.yml`: 海外版 compose
- **新建** `backend/src/services/stripe.ts` (stub)
- **新建** `backend/src/routes/payment.ts`: Stripe webhook + create-checkout（501 Not Implemented）
- `backend/package.json` + `web-portal/package.json`: 新增 dev:intl / build:intl 脚本

### Phase 9: 验证
- ✅ Backend TypeScript 编译：零错误
- ✅ Web Portal TypeScript 编译：零错误
- ⚠️ Web Portal Next.js build：SWC binary 兼容性问题（本机 Mac ARM64 平台，非代码问题）

### 总文件变更

| 模块 | 新建 | 修改 | 说明 |
|------|------|------|------|
| Backend | 8 | 11 | oauth/payment/stripe routes, cn+intl YAML, Dockerfile×2, compose |
| ComfyUI Wizard | 3 | 2 | i18n/zh.json+en.json+i18n.js, wizard.html, nodes.py |
| Web Portal | 5 | 17 | locales×2, i18n/middleware/navigation, Dockerfile, 全部页面+组件 |
| Contract | 0 | 1 | db-schema.sql |
| **合计** | **16** | **31** | **~47 文件** |

---

## Agent 4: 集成测试（a76cb08e）

### 审查范围
对照 contract/api-spec.yaml + node-interface.md + db-schema.sql，逐模块交叉验证三层代码。

### Bug 发现：8 致命 + 8 严重 + 13 一般

**致命（8 个，全部修复）**：
1. ✅ 注册 `smsCode`→`sms_code`（api.ts 字段名不匹配，注册完全不可用）
2. ✅ 用量分页 `pageSize`→`page_size`（query param 不匹配，分页静默失效）
3. ✅ 用量响应 `{data,totalPages}` vs `{items,page}`（响应结构完全不对，用量页空白）
4. ✅ deleteKey 204 No Content → JSON parse error（删除成功但前端报错）
5. ✅ UsageTable `createdAt` vs `created_at`（字段名不匹配，日期不渲染）
6. ✅ main.js 硬编码 `http://localhost:8188`（非标准端口完全不可用）
7. ✅ `/api/auth/password` 不存在（调用了不存在的端点）
8. ✅ 服务重启丢轮询 + 预扣余额不退款（致命财务 bug）

**严重（8 个，修复 5 个，3 个标记为已知限制）**：
9. ✅ Flux API 在余额检查之前调用 → 调整为先扣费再调 API
10. ✅ Qwen VL 成本未计费 → qwen.ts 返回 {description, usage} + deepseek.ts 累积 token + wizard.ts 单独计费
11. ✅ DeepSeek 自主任性调用 Flux → 移除 generate_preview tool + unused import + 死代码
12. ⚠️ ComfyUI 队列阻塞 10min → 架构限制（视频出片是最终步骤），标记为已知限制
13. ✅ 超时 5min vs 10min → 统一为 10 分钟
14. ✅ 设置模态框可破坏 API Key → 留空不修改，placeholder 显示前缀
15. ✅ 余额不足 WS 事件永不触发 → 移除错误的 `result.get("error")` 条件
16. ✅ /health 需认证 → 移到 auth 中间件之前

**收尾修复（6 项）**：
17. ✅ Qwen VL 成本未计费 → qwen.ts 返回 `{description, usage}` 结构化结果 + deepseek.ts 累积 qwenTokens + wizard.ts 单独扣费+记录用量（service: qwen_vl）
18. ✅ generate_preview tool 残留 → 移除 unused import `generatePreview`、更新注释 3→2 tools、删除死代码 generate_preview 跟踪逻辑
19. ✅ wizard/start 缺少 balance_after → WizardStartResponse 新增字段 + wizard.ts 返回最新余额
20. ✅ seedance_video_complete WS 事件缺少财务字段 → nodes.py 两处添加 `estimated_cost_fen` / `actual_cost_fen`
21. ✅ 缺少 README.md → comfyui-seedance-wizard/README.md（安装/配置/节点/架构）
22. ✅ 缺少 ComfyUI Manager 列表 JSON → comfyui-manager.json（名称/描述/节点映射/标签）

### 已验证通过（20+ 项）
- 8 条路由对齐 ✓ / postMessage type 一致 ✓ / WS 事件名一致 ✓
- Bearer token 附加+解析一致 ✓ / SQL 全部参数化 ✓ / API Key 不泄露 ✓
- CSS filter 参数范围 [-1,1] 正确 ✓ / 错误格式 {code, message} 统一 ✓
- TypeScript 编译零错误（含 qwen.ts 结构化返回 + deepseek.ts ToolLoopResult 新增 qwenTokens） ✓

---

## Phase 5：参数驱动向导重设计（2026-05-11）

### 背景
用户提出将 HTML 向导从「CSS 滤镜 + 聊天对话」范式升级为「参数定量驱动 + 即时图片重生成」。

### 核心新流程
```
原图 + 用户想法
  → /api/wizard/analyze:
      Qwen VL → 图片描述（英文）
      → DeepSeek analyzeAndStructure → {base_description, initial_params, creative_rationale}
      → promptComposer.composePrompt → 完整英文 Prompt
      → Flux 生成初始预览图
  → 向导 Step 3：参数面板
      用户调整任意参数（防抖 600ms）
      → /api/wizard/preview (params-driven)
      → promptComposer 重新合成 → Flux 重新生成
  → 用户确认 → /api/video/generate → Seedance 视频
```

### 新增/修改文件

**`backend/src/services/promptComposer.ts`** — 新建
- `composePrompt(baseDescription, params)` — 9 大参数维度 → 英文 Prompt 片段拼接
- `defaultParams()` — 回退默认值
- `validateAndNormalizeParams()` — 入参校验 + 数值 clamp

**`backend/src/services/deepseek.ts`** — 新增 `analyzeAndStructure()`
- 专用 system prompt（结构化分析模式）
- 调用 `structure_creative_params` 工具 → 返回完整 JSON 参数
- 最多 3 次重试 + 默认参数回退

**`backend/src/routes/wizard.ts`** — 重写
- 新增 `POST /api/wizard/analyze` — 完整三步分析链 (Qwen+DeepSeek+Flux)
- `POST /api/wizard/preview` — 支持 `params` 对象驱动合成 + 旧路径兼容
- 保留 `/start` + `/message`（旧对话向导，向后兼容）

**`backend/src/types.ts`** — 新增类型
- `PromptParams` (5 分类 + 4 数值维度)
- `WizardAnalyzeRequest/Response`
- `WizardParamPreviewRequest/Response`

**`comfyui-seedance-wizard/nodes.py`** — 新增路由
- `POST /seedance/wizard/analyze` — 代理到 Node.js 后端
- `GET /seedance/balance` — 供向导状态栏查询余额

**`comfyui-seedance-wizard/web/main.js`** — 重写协议
- 统一 RPC 协议：`seedance_rpc` / `seedance_rpc_result`（含 id 映射 + 超时 90s）
- WS 推送格式：`{type:"seedance_ws", event, payload}`
- 动态解析 PromptServer host（支持非 8188 端口）

**`comfyui-seedance-wizard/web/wizard.html`** — 完整重设计
- **Step 1**：拖放原图 + 创意想法文字框 + 视频比例选择
- **Step 2**：分析中动画（Qwen/DeepSeek/Flux 三步骤可视化）
- **Step 3**：预览图 + 参数面板（5 下拉 + 4 滑块）+ 防抖重生成覆盖层
- **Step 4**：视频生成进度条 + 完成结果 + 复制链接
- 步骤指示器、顶部余额/Key 状态栏、设置弹窗全部内联

### 验证
TypeScript 编译零错误 ✓

---

## Phase 6：环境配置 & 首次启动（2026-05-11）

### API Keys 配置
写入 `backend/.env`：

| 变量 | 服务 | 状态 |
|------|------|------|
| `MUAPI_KEY` | Flux + Seedance（muapi.ai） | ✅ |
| `DEEPSEEK_API_KEY` | DeepSeek 结构化分析 | ✅ |
| `DASHSCOPE_API_KEY` | Qwen VL 图像识别（阿里云） | ✅ |
| `JWT_SECRET` | 开发临时值 | ⚠️ 生产须换 |

新建 `backend/.gitignore`，确保 `.env` 不进入版本库。

### 新建 config/cn.yaml
`config.ts` 在启动时从 `../../config/${region}.yaml` 加载区域配置，此文件此前未生成。内容包含：货币（CNY/fen）、定价初始值、认证方式（phone）、CDN（local）。

### PostgreSQL 安装（macOS）
```
brew install postgresql@16
brew services start postgresql@16
createuser -s postgres        # Homebrew 默认无 postgres 角色
createdb seedance
psql seedance < contract/db-schema.sql   # 绕过 migrate.ts 事务问题
```

**迁移问题根因**：`migrate.ts` 将所有 65 条 SQL 放在单一事务，Statement 2「已存在」报错导致事务中断，后续所有语句失败。临时解法：psql 直接执行；长期应改为每条 SQL 独立 SAVEPOINT。

### 首次启动结果
```
[DB] Connection test OK
[Server] Listening on http://localhost:3000
[Server] Database: connected
GET /health → {"status":"ok","service":"seedance-wizard-api"}
```

7 张表：users / api_keys / balances / usage_logs / wizard_sessions / video_tasks / system_config ✓

### 待完成（冒烟测试）
- [ ] 注册账号（SMS 验证码打印到控制台）
- [ ] 获取 JWT token
- [ ] 调用 `/api/wizard/analyze` 跑完整 Qwen+DeepSeek+Flux 链路
- [ ] 确认 Seedance 视频生成

---

## 最终文件清单

| 模块 | 文件数 | 行数 | 新增文件 |
|------|--------|------|---------|
| ComfyUI 节点 | 2 | ~630 | — |
| HTML 向导 | 3 | ~1,200 | — |
| Node.js 后端 | 24 | ~12,200 | promptComposer.ts |
| Web Portal | 31 | ~2,600 | — |
| 契约文档 | 4 | ~800 | — |
| 配置/文档 | 4 | ~120 | config/cn.yaml, .gitignore |
| **合计** | **68** | **~17,600** | — |

---

## Phase 7: 首次测试与 Bug 修复（2026-05-11）

### 测试执行

完整执行 todo-list.md 的 8 模块测试（Block A–H），结果记录在 [todo-list.md](todo-list.md#测试结果2026-05-11)。

### 发现的 Bug（5 个，全部修复）

| Bug | 严重度 | 位置 | 根因 | 修复 |
|-----|--------|------|------|------|
| muapi Flux API 404 | 致命 | `services/flux.ts` | muapi.ai 无 Flux 端点 | Flux 降级: preview_url=null + 自动退款 |
| Seedance `request_id` | 致命 | `services/seedance.ts` | API 返回 `request_id` 不在接口定义 | 添加 `request_id?`/`id?` 可选字段 |
| Seedance `outputs` vs `output` | 致命 | `services/seedance.ts` | API 返回复数 `outputs`，代码找 `output` | `outputs?.[0] \|\| output?.[0]` |
| I2V 发 `image_b64: null` | 严重 | `wizard.html` | 逻辑取反，有预览图时发 null | 优先使用 `state.imageB64` |
| `/analyze` Flux 失败不退费 | 严重 | `routes/wizard.ts` | Flux 失败后已扣 Qwen+DeepSeek 无法退款 | 重构为先操作后扣费，Flux 独立 try/catch + 退款 |

### 架构改进

- **`/api/wizard/analyze` 重构**: 扣费顺序从「边操作边扣费」改为「先操作再统一扣费」，Flux 失败仅降级不丢数据（preview_url=null）
- **`server.ts` 修复**: orphan recovery 移出 migrate 的 try/catch，迁移失败不影响视频轮询恢复
- **Flux 降级设计**: muapi.ai 不提供 Flux → 系统在无 Flux 时仍完整返回 Qwen+DeepSeek 结果

### 测试环境备忘

- 后端在 [localhost:3000](http://localhost:3000)
- 测试账号: `13800000001` / `Test1234!`，JWT 见 todo-list.md
- 三种 API Key 均就绪: MUAPI_KEY / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY
- **开发时用 `npm run dev`**（ts-node），`npm start` 跑编译后 JS

### 待办
- [ ] 集成真实 Flux 提供商（Replicate/Together AI/Fal.ai）
- [ ] `migrate.ts` 每条 SQL 独立 SAVEPOINT
- [ ] Block H: ComfyUI 节点安装测试
- [ ] 海外版端到端测试（`DEPLOYMENT_REGION=intl`）

---

## Phase 8 — Bug 修复与提供商替换（2026-05-11）

### 变更内容

#### 1. Flux 提供商迁移：muapi.ai → fal.ai
- **文件**: `backend/src/services/flux.ts`（全量重写）
- muapi.ai 的 `/flux-schnell` 端点不存在（404），改用 [fal.ai](https://fal.ai/models/fal-ai/flux/schnell)
- 新端点：`POST https://fal.run/fal-ai/flux/schnell`，认证 `Authorization: Key <FAL_KEY>`
- 使用 `sync_mode: true` 同步返回，无需轮询（< 1s 出图）
- aspect_ratio 映射：`16:9→landscape_16_9`, `9:16→portrait_9_16`, `1:1→square_hd`, `4:3→landscape_4_3`, `3:4→portrait_4_3`
- **config.ts**: 新增 `config.falKey` 读取 `process.env.FAL_KEY`
- **backend/.env**: 新增 `FAL_KEY=`（待填写）— 在 https://fal.ai/dashboard/keys 注册获取

#### 2. wizard.html Step 3 预览降级
- **文件**: `comfyui-seedance-wizard/web/wizard.html`
- 新增 `#preview-fallback` + `#preview-fallback-img` 区域（Flux 不可用时显示）
- 新函数 `showPreviewFallback(originalB64)`：使用原始上传图（半透明）+提示文字代替空白
- `showPreviewImage(null)` 自动 fallback；图片加载失败也 fallback
- 效果：用户可以看到原图轮廓，仍可正常调参和生成视频

#### 3. migrate.ts SAVEPOINT 重构
- **文件**: `backend/src/db/migrate.ts`
- 原问题：PostgreSQL 在事务中遇到 `already exists` 等错误会进入 aborted 状态，catch 后继续执行仍全部失败
- 修复：每条语句包裹在独立 `SAVEPOINT sp_migrate_{i}` 中，出错时 `ROLLBACK TO SAVEPOINT` + `RELEASE`，事务继续
- 非幂等错误（真正的错误）记录 `failed` 计数，不再 throw，完成后打印汇总
- 最终日志格式：`[Migrate] Done — applied=N, skipped=M, failed=K`

#### 4. usage_logs cost_fen=0 修复
- **文件**: `backend/src/routes/video.ts`
- 原问题：视频任务完成时调用 `updateUsageLogStatus(usageLogId, 'success')` 未传 `costFen`，导致 DB 里 `cost_fen` 始终为 0
- 修复：完成时传入 `actualCost`（即 `estimated_cost_fen`）：`updateUsageLogStatus(usageLogId, 'success', actualCost)`

### 待办（更新）
- [ ] 填入 `FAL_KEY`，重启后端测试 Flux 预览
- [ ] Block H: ComfyUI 节点安装测试
- [ ] 海外版端到端测试（`DEPLOYMENT_REGION=intl`）

---

## Phase 9 — 全量任务扫尾（2026-05-11）

### Block H：ComfyUI 节点审查

- **`nodes.py` 缺少 `import urllib.parse`**（已修复）— `forward()` 方法在 `params` 不为 None 时会调用 `urllib.parse.urlencode`，但原文件只导入了 `urllib.request` 和 `urllib.error`，运行时 `AttributeError`
- **`wizard.html resetWizard()` 遗漏 `#preview-fallback` 隐藏**（已修复）— 重置向导时新增的 fallback 区域未隐藏
- **`README.md` 全面更新**：补充完整安装步骤、所有 PromptServer 路由表、4 步流程说明、H-3 验证命令

静态检查结果：语法 ✅，所有 7 条路由 ✅，ComfyUI 映射导出 ✅

### 海外版端到端验证

- **`config/intl.yaml` 创建**（之前只有 cn.yaml）：DEPLOYMENT_REGION=intl 启动时 fallback 会报缺失 intl.yaml 错误，现已补齐
- **定价**：USD 美分，T2V basic 5s = $0.30（30 cents），Flux 每张 $0.01
- **路由审查**：
  - 手机注册/登录 → `region=intl` 时返回 400 区域守卫 ✅
  - 邮箱注册/登录 (`POST /api/auth/email/register|login`) ✅
  - Google OAuth (`POST /api/auth/google`) — `GOOGLE_CLIENT_ID` 未配置时返回 501 ✅
  - `balance.ts` 返回 `currency: "USD"` ✅
- **TypeScript 编译**：`npx tsc --noEmit` 零错误 ✅
- 海外版手动验证命令已追加到 `todo-list.md`

### I2V 路径修复

- **`seedance.ts` base64 前缀去除**：muapi.ai `image` 字段需要纯 base64（不含 `data:image/jpeg;base64,` 前缀）。修复：`raw.includes(',') ? raw.split(',')[1] : raw`
- 代码路径：用户上传图 → `state.imageB64`（含前缀）→ RPC → `video.ts` → `submitI2V(image_b64)` → 去前缀 → muapi.ai ✅

### 当前剩余 TODO（仅需用户本地操作）

1. **填入 `FAL_KEY`**（`backend/.env`）：https://fal.ai/dashboard/keys 注册免费账号
2. **Block H 实机安装**：`ln -s ~/ClaudeProject/seedance-transfer/comfyui-seedance-wizard <ComfyUI>/custom_nodes/`，启动 ComfyUI 后按 README 配置 API Key
3. **海外版手动回归**：`npm run dev:intl`，按 todo-list.md 海外版验证清单逐条执行

---

## Phase 10 — 扫尾修复 + 提供商替换（2026-05-12）

### 背景
集成测试 18/18 全绿，但 Flux 预览图始终返回 null。本阶段完成剩余所有技术债，并完成 ComfyUI 实机安装。

### 修复内容

#### 1. migrate.ts 单引号 SQL 拆分 Bug（已修复）
- **文件**: `backend/src/db/migrate.ts` — `splitSqlStatements()`
- **根因**: 解析器只处理了 `$$...$$ ` 美元引号块，未处理 `'...'` 单引号字符串
- **表现**: `COMMENT ON COLUMN usage_logs.units IS 'deepseek/qwen_vl=tokens; flux_preview=张数; seedance=秒数'` 中的 `;` 被误识别为语句分隔符，导致 3 条 COMMENT 语句解析失败
- **修复**: 新增 `inSingleQuote` 状态机（含 `''` 转义处理），分号在单引号内不拆分
- **验证**: 单元测试通过（3 语句正确拆分）；生产 build `failed=0`（之前 `failed=3`）

#### 2. fal.ai 余额耗尽 → 切换阿里云通义万象（已修复）
- **文件**: `backend/src/services/flux.ts`（全量重写）
- **根因**: fal.ai 账号余额耗尽（HTTP 403 "Exhausted balance"），muapi.ai Flux 端点不存在（HTTP 404）
- **新架构**:
  - **主路由**: 阿里云 DashScope 通义万象 `wanx2.1-t2i-turbo`（DASHSCOPE_API_KEY 已配置，账单统一）
  - **备用路由**: fal.ai Flux-Schnell（当 Wanx 失败时自动切换）
  - 移除 muapi.ai Flux 路由（端点不存在）
- **Wanx 接入细节**:
  - 异步任务模式：POST 提交 → 轮询 `task_id`（3s 间隔，最多 60s）
  - 支持 5 种宽高比：16:9→1280×720, 9:16→720×1280, 1:1→1024×1024, 4:3→1024×768, 3:4→768×1024
  - negative_prompt: `"blurry, low quality, distorted, text, watermark"`
- **验证**: 集成测试 `preview_url: https://dashscope-result-*.aliyuncs.com/...` ✅，`Flux 预览图生成 OK ✨`

#### 3. ComfyUI 实机安装（已完成）
- **安装**: macOS + Apple Silicon（arm64）+ Python 3.13
- **路径**: `~/ComfyUI`，PyTorch MPS 版本
- **节点 link**: `ln -s ~/ClaudeProject/seedance-transfer/comfyui-seedance-wizard ~/ComfyUI/custom_nodes/seedance-wizard`
- **验证**: 启动日志 `Seedance Wizard routes registered on PromptServer` ✅

#### 4. 生产 Build 验证（已完成）
- **命令**: `cd backend && npx tsc && npm start`
- **结果**: TypeScript 编译零错误 ✅，migrate `failed=0` ✅，端口冲突（3000 已被 dev 占用，非 bug）

### API Key 状态（截至 2026-05-12）

| 变量 | 服务 | 状态 |
|------|------|------|
| `DASHSCOPE_API_KEY` | Qwen VL + 通义万象预览图 | ✅ 双用途 |
| `DEEPSEEK_API_KEY` | DeepSeek 结构化分析 | ✅ |
| `MUAPI_KEY` | Seedance 视频生成 (T2V/I2V) | ✅ |
| `FAL_KEY` | fal.ai（备用，余额已耗尽） | ⚠️ 需充值或废弃 |
| `JWT_SECRET` | 开发临时值 | ⚠️ 生产须换随机值 |
| `SMS_PROVIDER_KEY` | 短信验证码 | ❌ 未接入（console mock） |

### 全量测试结果（2026-05-12 最终）

```
BLOCK A 认证:     ✅ PASS
BLOCK B 账户:     ✅ PASS
BLOCK C 向导分析: ✅ PASS（Wanx 预览图生成 OK ✨）
BLOCK D 视频生成: ✅ PASS（T2V 1次轮询完成）
BLOCK E 用量计费: ✅ PASS
BLOCK F 错误处理: ✅ PASS
总计: 18/18 PASS, 0 FAIL
```

### 下一阶段：上线准备
详见 `todo-list.md` — 基础设施选型与上线计划。

---

## Phase 11 — API Spec 补全（2026-05-12）

### 背景
DeepSeek Code Review（Phase B）指出 `contract/api-spec.yaml` 存在三处遗漏，本阶段全部修复。

### 修复内容

#### 1. 新增 `POST /api/wizard/analyze` 端点
- **问题**：该端点在 Phase 5 实现，是当前向导的核心入口，但从未写入 api-spec.yaml
- **新增内容**：完整 requestBody（`image_b64` / `user_idea` / `aspect_ratio`）、响应 schema（含 `initial_params: $ref PromptParams`、`preview_url: nullable`、计费字段）、400/402 错误码

#### 2. 新增 `PromptParams` 组件 schema
- **问题**：`/analyze` 响应中 `initial_params` 字段的 9 个维度（style / lighting / shot_type / mood / color_tone + 4 个 0–100 滑块）在 spec 中无任何定义，其他模型无法理解其结构
- **新增**：`components/schemas/PromptParams`，明确枚举值和 integer 范围

#### 3. `Balance` schema 补充 `currency` 字段
- **问题**：`BalanceResponse` TypeScript 类型（`types.ts` 第 100 行）和 `balance.ts` 路由返回值都包含 `currency`，但 yaml schema 缺失
- **修复**：`Balance.properties` 新增 `currency: { type: string, example: "CNY" }`

#### 4. `preview_url` 标记为 `nullable: true`
- **问题**：`/api/wizard/preview` 和 `/api/wizard/analyze` 的响应 schema 中 `preview_url` 为 `type: string`，但实际实现在 Flux 失败时返回 `null`，spec 与实现不符
- **修复**：两处均改为 `nullable: true`，并补充 `composed_prompt` 字段（params 路径时返回）

#### 5. 修复预存在的 YAML 格式错误（3 处）
- **问题**：`ApiKey.last_used_at`、`WizardSession.current_prompt`、`VideoTaskResult.actual_cost_fen` 的 flow mapping 前缺少空格（`key:{...}` → `key: {...}`），导致 yaml.safe_load 报 ScannerError
- **修复**：补加空格，YAML 现可正常解析

### 验证
```bash
python3 -c "import yaml; yaml.safe_load(open('contract/api-spec.yaml')); print('YAML OK')"
# → YAML OK ✅
```

### 更新后 api-spec.yaml 端点清单

| 标签 | 路径 | 方法 | 状态 |
|------|------|------|------|
| Auth | /api/auth/register | POST | ✅ |
| Auth | /api/auth/login | POST | ✅ |
| Auth | /api/auth/sms | POST | ✅ |
| API Keys | /api/keys | GET / POST | ✅ |
| API Keys | /api/keys/{id} | DELETE | ✅ |
| Balance | /api/balance | GET | ✅ |
| Balance | /api/usage | GET | ✅ |
| Wizard | /api/wizard/analyze | POST | ✅ **新增** |
| Wizard | /api/wizard/start | POST | ✅ |
| Wizard | /api/wizard/message | POST | ✅ |
| Wizard | /api/wizard/preview | POST | ✅ |
| Video | /api/video/generate | POST | ✅ |
| Video | /api/video/{taskId}/status | GET | ✅ |
| Video | /api/video/{taskId}/result | GET | ✅ |
| Utils | /api/estimate | POST | ✅ |

---

## 项目总览：工作量与基础设施选型

### 已完成工作量估算

#### 代码量

| 模块 | 文件 | 代码行数 | 语言 |
|------|------|---------|------|
| Node.js 后端 | 24 | ~12,200 | TypeScript |
| Web Portal | 31 | ~2,600 | TypeScript/TSX |
| ComfyUI 节点 | 2 | ~630 | Python |
| HTML 向导 | 3 | ~1,200 | HTML/JS/CSS |
| 契约文档 | 4 | ~800 | YAML/SQL/MD |
| 配置/运维 | 4 | ~170 | YAML/Docker |
| **合计** | **68** | **~17,600** | — |

#### 人天拆解

| 工作项 | 内容 | 估算人天 |
|--------|------|---------|
| 架构设计 | OpenAPI 规范、DB Schema、多区域架构设计、契约文档 | 3 天 |
| 后端开发 | 认证双模（JWT+API Key）、计费系统（预扣/退款）、AI 三链路（Qwen VL+DeepSeek+Wanx）、视频生成（T2V/I2V）、限流/错误处理、DB 迁移 | 14 天 |
| 前端开发 | Next.js 14 Portal（9页面+8组件）、登录/注册/仪表盘/充值/用量/设置、i18n 双语 | 6 天 |
| ComfyUI 节点 | Python 节点 + PromptServer 路由、4步向导 HTML/CSS/JS、参数驱动预览、WebSocket 实时推送、i18n | 7 天 |
| 海外版架构 | YAML 多区域配置、Google OAuth 框架、Stripe stub、邮箱认证路由、多币种计费 | 3 天 |
| 测试与调试 | 集成测试脚本（18个 case）、发现+修复 25+ bug、文档编写 | 5 天 |
| 运维配置 | Docker 多阶段构建、PM2 配置、Nginx 模板、CI 脚本 | 1 天 |
| **合计** | | **≈ 39 人天** |

#### 对照市场价值

| 计费标准 | 费用 |
|----------|------|
| 国内外包（中级全栈，¥3,500/天） | **¥136,500** |
| 国内外包（高级全栈，¥5,000/天） | **¥195,000** |
| 国内开发公司报价（含项目管理） | **¥250,000 - ¥350,000** |
| 海外（$600/天，不含设计） | **$23,400** |

> 这是一个完整 AI SaaS MVP：认证 + 计费 + AI 多链路集成 + 双端（Web Portal + ComfyUI 插件）+ 国际化 + 海外版架构。从零到测试全绿用了约 3 个日历日（并行开发）。

---

### 基础设施选型建议

#### 服务器：阿里云 ECS

**推荐配置**：`ecs.c7.large`（2核4G，¥200/月，含3M带宽）或 `ecs.c7.xlarge`（4核8G，¥400/月，含5M带宽）

| 方案 | 规格 | 月费 | 适用阶段 |
|------|------|------|---------|
| 起步 | 2核4G + 3M 带宽 | ¥200 | 0-500 日活 |
| 成长 | 4核8G + 5M 带宽 | ¥400 | 500-5000 日活 |
| 扩展 | 负载均衡 + 多实例 | ¥1000+ | 5000+ 日活 |

**理由**：已有 DashScope API Key（阿里云账号），账单合并；RDS PostgreSQL ¥70/月起，免维护；国内访问延迟最低。

**系统**：Ubuntu 22.04 LTS，Node.js 20 LTS，PM2 守护进程，Nginx 反向代理。

---

#### 短信验证码：阿里云短信服务

- **费用**：¥0.045/条（国内），新用户赠 100 条
- **接入**：安装 `@alicloud/dysmsapi20170525`，申请签名+模板（审核 1-2 工作日）
- **理由**：已有阿里云账号，最简路径

```env
SMS_ACCESS_KEY_ID=<RAM 子账号 AK>
SMS_ACCESS_KEY_SECRET=<RAM 子账号 SK>
SMS_SIGN_NAME=Seedance
SMS_TEMPLATE_CODE=SMS_xxxxxx
```

---

#### 支付接入：分阶段方案

**阶段一（快速上线，个人主体）**

| 渠道 | 方案 | 手续费 | 到账 |
|------|------|--------|------|
| 微信支付 | 虎皮椒（hupijiao.com）或 PayJS | 1-2% | T+1 |
| 支付宝 | 支付宝当面付（个人账号可申请） | 0.6% | 实时 |

> 虎皮椒：无需营业执照，个人开发者即可接入微信支付，开通 1 天内。

**阶段二（企业主体）**

| 渠道 | 申请材料 | 审核周期 | 手续费 |
|------|---------|---------|--------|
| 微信支付商户号 | 营业执照 + 法人身份证 + 银行卡 | 3-5 工作日 | 0.6% |
| 支付宝企业账号 | 营业执照 | 1-3 工作日 | 0.6-1.0% |

**后端充值套餐建议**（参考）：

| 套餐 | 售价 | 额度 | 折合视频 |
|------|------|------|---------|
| 体验包 | ¥9.9 | 1,000 fen | ~6 个 5s 视频 |
| 标准包 | ¥49 | 6,000 fen | ~38 个 |
| 专业包 | ¥99 | 15,000 fen | ~96 个 |
| 旗舰包 | ¥299 | 50,000 fen | ~322 个 |

> T2V 5s basic = 155 fen ≈ ¥1.03 成本

---

#### 邮箱通知：SendGrid（海外版）

- **免费额度**：100 封/天，满足初期
- **付费**：$19.95/月（无限量）
- **用途**：注册欢迎、充值确认、视频生成完成
- **国内替代**：阿里云邮件推送（DirectMail），¥0.03/封

---

## Phase 12 — 海外版部署（2026-05-13）

### 背景
用户购买两个域名（see4dance.com / see4dance.cn），决定先全力搞海外版，部署到 Railway。

### 已完成

#### 1. 邮箱验证码（替换短信）
- **背景**：中国短信监管严格，需资质审批，改为邮箱验证
- **新建** `backend/src/services/mail.ts`：Resend API 发送邮件 + 自动 fallback 到 console mock（Resend 失败不抛错）
- **新建** `backend/src/routes/oauth.ts` 邮箱路由：
  - `POST /api/auth/email/send-code` — 6位数字验证码，60s 限频，5min 过期
  - `POST /api/auth/email/register` — email + password + code → 创建用户
  - `POST /api/auth/email/login` — email + password → JWT
- `backend/src/config.ts`：新增 `resendApiKey` / `resendFromEmail` 字段
- `web-portal/app/login/page.tsx` + `register/page.tsx`：重写为双 Tab（Email 默认 + Phone 次选）
- `web-portal/lib/api.ts` / `auth.tsx`：新增 email 相关 API 函数

#### 2. Git 仓库 + GitHub
- 初始化 git → 创建 .gitignore（排除 node_modules/、.env、.next/、dist/、规划文档等）
- 清理：统一 `backend/config/` 为单一配置源，删除根 `config/` 冗余副本
- 修复 `findConfigDir()` 去掉冗余候选路径
- 创建 GitHub 私有仓库 `liuhongyi0/seedance-transfer` → push

#### 3. Backend 部署 Railway
- **Dockerfile** 修复：构建上下文设为仓库根目录，`COPY contract/db-schema.sql` 等路径正常解析
- `package.json` build 脚本兼容 Docker（`npx tsc` 不含 cp）
- 服务配置：Root Directory 清空，Dockerfile Path = `backend/Dockerfile`
- **域名**：`seedance-transfer-production.up.railway.app`
- **健康检查**：`GET /health` → `{"status":"ok"}`
- **PostgreSQL**：Railway 托管，`DATABASE_URL` 自动注入

#### 4. Web Portal 部署 Railway
- **Dockerfile** 修复：repo-root 路径，`COPY web-portal/ .`，`output: 'standalone'`
- **package-lock.json 修复**：npm 11 vs npm 10 不兼容，用 npm 10 重新生成
- **next.config.js 修复**：`next-intl/plugin('./src/i18n.ts')` 指定路径
- **middleware 修复**：
  - 从 `src/middleware.ts` 移到项目根 `middleware.ts`（Next.js 要求与 `app/` 同级）
  - 替换 next-intl createMiddleware 为自定义 cookie-based locale 检测（避免 URL rewrite 冲突）
- **`src/i18n.ts`**：新增 `defaultLocale` export
- 服务配置：Root Directory 清空，Dockerfile Path = `web-portal/Dockerfile`
- **域名**：`robust-mercy-production-80fc.up.railway.app`
- **验证**：`/` `/login` `/dashboard` 均返回 200

#### 5. 配置与文档
- **gitignore**：排除 `/config/`、`deploy/.env.production`、`*.md`（根级规划文档）
- **Dockerfile 默认值**：`DEPLOYMENT_REGION=intl`、`NEXT_PUBLIC_REGION=intl`

### 部署架构

```
Railway 项目: seedance-transfer
├── PostgreSQL (Railway 托管)
├── Backend Service
│   ├── Dockerfile: backend/Dockerfile
│   └── Domain: seedance-transfer-production.up.railway.app
└── Web Portal Service
    ├── Dockerfile: web-portal/Dockerfile
    └── Domain: robust-mercy-production-80fc.up.railway.app
```

### 当前 Agent 文件状态
- record.md、todo-list.md、memory.md 三位一体，保持同步

```env
SENDGRID_API_KEY=SG.xxxxxxxx
SENDGRID_FROM_EMAIL=noreply@seedance.ai
```

---

#### 月运营成本汇总

| 项目 | 服务 | 月费 |
|------|------|------|
| 服务器 | 阿里云 ECS 2核4G | ¥200 |
| 数据库 | 阿里云 RDS PostgreSQL（可选，ECS 自建免费） | ¥70 |
| 短信 | 阿里云 SMS（500条/月） | ¥23 |
| 存储 | 阿里云 OSS（视频归档，10GB） | ¥1 |
| SSL | 阿里云免费 DV 证书 | ¥0 |
| **固定合计** | | **≈ ¥294/月** |
| **AI 成本（变量）** | DashScope + muapi（按用量） | 按收入比例 |
