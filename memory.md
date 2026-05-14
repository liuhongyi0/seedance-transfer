# Seedance Transfer 项目记忆

> 项目目标：做一个 ComfyUI 自定义节点，HTML 创作向导 × DeepSeek 导演（看图/写Prompt/出预览）→ Seedance 2.0 出视频。节点免费开源，靠 API Key 按量充值变现。

---

## 产品逻辑

- **产品形态**：ComfyUI 自定义节点（开源免费）+ API 中转站（闭源按量收费）+ Web 充值页
- **核心架构**：HTML 向导（用户交互）× DeepSeek 导演（tool_call 调 Qwen 看图/Flux 定大方向）× CSS 实时滤镜（色调/亮度/景深微调，零延迟）→ Seedance 出片
- **双轨并行**：国内（阿里云，微信/支付宝，中文）+ 海外（香港 Railway，Stripe，英文）
- **LLM 侧零开发**：LLM_party（★2229）已原生支持 DeepSeek + MCP tool_call，Qwen/Flux/Seedance 作为工具接入
- **供应商**：从"X公司"拿 Seedance 渠道价（非直接从火山方舟/炘沐）
- **转化漏斗**：ComfyUI 40万用户 × 5% 安装率 → 2万安装 × 1% 付费率（占总用户）→ 4,000 付费天花板
- **主分发渠道**：ComfyUI Manager（零成本，一行 JSON 上架）
- **变现模式**：节点免费，API Key 按量充值，赚渠道差价

## Seedance 2.0 特点

- **开发商**：字节跳动，通过火山引擎方舟平台提供 API
- **官方注册限制**：火山方舟不支持 Google 注册，需中国手机号 + 实名认证（与 Kling 相同）。**我们通过 X 公司渠道绕过此限制**，用户注册的是我们的充值平台（Supabase Auth: 海外 Google OAuth，国内微信/手机号）
- **质量定位**：与 Kling 3.0 同梯队，非代差。对 ComfyUI 用户来说画质差距在「后处理可弥补」范围内
- **原价**：¥0.3–0.5/s ≈ $0.042–0.07/s（火山方舟零售价）
- **渠道优势**：从 X 公司拿渠道折扣价，成本低于官价
- **vs Kling**：Seedance API 海外可直接访问；Kling 需中国企业认证，海外用户只能走 fal.ai 加价 61%
- **ComfyUI 生态现状**：7 个 Seedance 节点，3 活跃（seedance2-comfyui ★183 经 muapi 中转、Jimeng-API ★44 火山直连仅中国、muapi-comfyui ★44），4 僵尸（★0-1）。活跃节点均无 DeepSeek 串联

## 竞争定位

- **不拼价格**，拼：① 海外可达 ② HTML 创作向导 × DeepSeek 导演管线独家 ③ 渠道低价
- **主要 ComfyUI 竞品**：seedance2-comfyui（★183，muapi.ai 中转）、Jimeng-API（★44，仅中国用户）
- **间接竞品**：Kling（海外被封，走 fal.ai 加价 61%）
- **竞品核心短板**：全部裸文本框手写 Prompt，无一有创作向导或预览机制
- **我们的差异化**：HTML 向导引导创作 → DeepSeek 导演出 Prompt → Flux 出第一版预览（$0.001）→ CSS 实时滤镜微调（零延迟零费用）→ 满意出片。试错成本从竞品 $0.60/次降到 $0.001/次，微调体验从"等 2 秒"变成"拖滑块立刻见"
- **开源模型（Wan/Hunyuan/LTX）**：需显卡，是互补品非竞品
- **Runway/Pika/Sora/Veo**：封闭 SaaS 无 ComfyUI 节点，零竞争
- **定价约束**：国内 ≤ Seedance 官价 120%，海外 ≤ 官价 140% 且显著低于 Kling 中转价
- **僵尸节点失败原因**：第三方中转加价无优势、零文档、未上 ComfyUI Manager、无商业动机、Seedance 1.0 质量问题

## 目标用户（4 类）

1. **硬核开源创作者（25%）**：有 4090，用 Wan/Hunyuan 本地跑 → 补充品，不需要但可做 cloud fallback
2. **无高端显卡创作者（40%，核心目标）**：MacBook/4060，要画质但买不起显卡 → 主战场，API 是唯一解
3. **工作流整合者（20%，最高付费意愿）**：LLM→Img→Video→Upscale 全流程，不愿跳出 ComfyUI → DeepSeek 管线是杀手功能
4. **电商卖家 & 社媒运营（15%，新增量）**：刚接触 ComfyUI，要预置工作流一键出片 → 预置工作流 + 低门槛是关键

## 关键文件

| 文件 | 内容 |
|------|------|
| `comfyui-full-plan.md` | **主方案**（13 章）：ComfyUI切入 → 产品设计 → 技术架构 → 双轨 → 竞争 → 定价 → 收入预测 |
| `competitive-analysis.md` | 15 个模型全竞品分析：客户画像/价格/ComfyUI 集成/优劣势 |
| `seedance-vs-kling.md` | Kling 专项对比：质量/价格/三张牌/竞争策略 |
| `comfyui-plan.md` | 早期 ComfyUI 专项方案（部分内容已合并到 full-plan） |
| `lightweight-integration-plan.md` | 双轨轻量集成方案（飞书/微信/Shopify/Discord 等） |
| `comfyui-for-beginners.md` | **小白版**：零基础看懂 ComfyUI 是什么、为什么选它、产品效果 |
| `record.md` | 完整开发记录（Phase 2–11） |
| `todo-list.md` | 当前状态 + P0/P1 上线计划 |
| `contract/api-spec.yaml` | OpenAPI 3.0 契约（15 端点，含 PromptParams schema） |

## 开发进度（截至 2026-05-13）

- **实际完成量**：~42 人天（含 Phase 2–12 全部阶段）
- **代码量**：~75 文件，~18,000 行
- **测试状态**：18/18 全绿（本地集成测试），ComfyUI 实机安装验证通过
- **部署状态**：
  - Backend: `seedance-transfer-production.up.railway.app` ✅
  - Web Portal: `robust-mercy-production-80fc.up.railway.app` ✅
  - PostgreSQL: Railway 托管 ✅
- **待完成（P0）**：
  1. Backend 环境变量（API Key 填入 Railway）
  2. see4dance.com DNS → Railway CNAME
  3. Resend 域名验证确认
  4. 端到端测试
- **API Key 状态**：DASHSCOPE ✅ / DEEPSEEK ✅ / MUAPI ✅ / Resend ✅ / FAL_KEY ⚠️余额耗尽 / SMS/Stripe ❌未接

## 开发 & 成本

- **开发量**：36 人天（节点含 HTML 向导 9d + 后端 10d + Web 8d + DevOps 3.5d + 测试 4d）
- **零成本复用**：DeepSeek tool_call（LLM_party AGPL，不改代码直接用）、Seedance API 客户端（seedance2-comfyui MIT，fork 复用）
- **Claude Code 自研**：$0–200，5 周业余时间
- **外包开发**：≈¥75,000（$10,300）
- **启动资金**：自研 $888 / 外包 $11,188
- **月运营成本**：$126（起步）/ 固定基础设施 ≈¥270/月（ECS + RDS + SMS + OSS）
- **盈亏平衡**：自研 M1 / 外包 M3（详见 full-plan 第十一章）

## 用户偏好

- 先出方案再动手，不跳步骤
- 价格不能太便宜——核心卖点是可用性不是廉价
- 不相关的竞品不要写进方案
- 方案文档保持精炼，聚焦可执行性
- memory.md 记录产品逻辑和定性判断，测算数字放方案文档中
