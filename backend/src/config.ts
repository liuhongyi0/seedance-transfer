// ─────────────────────────────────────────────
// 环境变量 + 区域配置加载
// 区域由 DEPLOYMENT_REGION 环境变量控制 (cn|intl)
// ─────────────────────────────────────────────

import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';
import yaml from 'js-yaml';

// 从项目根目录加载 .env（backend/.env）
dotenv.config({ path: path.resolve(__dirname, '..', '.env') });

// 部署区域
type Region = 'cn' | 'intl';
const region: Region = (process.env.DEPLOYMENT_REGION || 'cn') as Region;

// 区域配置接口
export interface RegionConfig {
  region: string;
  currency: string;
  currency_subunit: string;
  locale: string;
  auth: {
    providers: string[];
    google_client_id: string;
  };
  payment: {
    provider: string;
    stripe_public_key: string;
  };
  cdn: {
    provider: string;
    bucket: string;
  };
  pricing: {
    deepseek_input_per_1m_subunit: number;
    deepseek_output_per_1m_subunit: number;
    qwen_vl_per_1m_subunit: number;
    flux_preview_per_image_subunit: number;
    seedance_t2v_basic_per_sec_subunit: number;
    seedance_t2v_high_per_sec_subunit: number;
    seedance_i2v_basic_per_sec_subunit: number;
    seedance_i2v_high_per_sec_subunit: number;
  };
}

function envInterpolate(value: string): string {
  return value.replace(/\$\{(\w+)\}/g, (_, name: string) => {
    return process.env[name] || '';
  });
}

function findConfigDir(): string {
  // __dirname 在 dist/ 或 src/ 下，../config 统一指向 backend/config/
  return path.resolve(__dirname, '..', 'config');
}

function loadRegionConfig(): RegionConfig {
  const configDir = findConfigDir();
  const yamlFile = path.join(configDir, `${region}.yaml`);

  if (!fs.existsSync(yamlFile)) {
    console.warn(`[Config] Region config not found: ${yamlFile}`);
    const fallback = path.join(configDir, 'cn.yaml');
    if (fs.existsSync(fallback)) {
      return JSON.parse(JSON.stringify(yaml.load(fs.readFileSync(fallback, 'utf-8'))));
    }
    throw new Error(`Region config not found: ${yamlFile} (and no cn.yaml fallback)`);
  }

  const raw = fs.readFileSync(yamlFile, 'utf-8');
  const interpolated = envInterpolate(raw);
  const parsed = yaml.load(interpolated) as RegionConfig;
  return parsed;
}

const regionConfig = loadRegionConfig();

export const config = {
  // 部署区域
  region: region as string,
  regionConfig,

  port: parseInt(process.env.PORT || '3000', 10),

  databaseUrl:
    process.env.DATABASE_URL ||
    'postgresql://postgres:postgres@localhost:5432/seedance',

  deepseekApiKey:
    process.env.DEEPSEEK_API_KEY || '',

  dashscopeApiKey:
    process.env.DASHSCOPE_API_KEY || '',

  muapiKey:
    process.env.MUAPI_KEY || '',

  // fal.ai API Key（Flux-Schnell 预览图）
  falKey:
    process.env.FAL_KEY || '',

  jwtSecret:
    process.env.JWT_SECRET || 'dev-secret-change-in-production',

  // 邮件发送（Resend API）
  resendApiKey:
    process.env.RESEND_API_KEY || '',
  resendFromEmail:
    process.env.RESEND_FROM_EMAIL || '',

  smsProviderKey:
    process.env.SMS_PROVIDER_KEY || '',

  // 阿里云短信（AccessKey ID + 签名 + 模板）
  smsAccessKeyId:
    process.env.SMS_ACCESS_KEY_ID || '',
  smsSignName:
    process.env.SMS_SIGN_NAME || '',
  smsTemplateCode:
    process.env.SMS_TEMPLATE_CODE || '',

  // 虎皮椒支付（xunhupay.com）
  xunhupayAppId:
    process.env.XUNHUPAY_APPID || '',
  xunhupayAppSecret:
    process.env.XUNHUPAY_APPSECRET || '',
  xunhupayNotifyUrl:
    process.env.XUNHUPAY_NOTIFY_URL || '',

  // Google OAuth（海外版）
  googleClientId:
    process.env.GOOGLE_CLIENT_ID || '',

  // Stripe（海外版，预留）
  stripeSecretKey:
    process.env.STRIPE_SECRET_KEY || '',
  stripeWebhookSecret:
    process.env.STRIPE_WEBHOOK_SECRET || '',

  // JWT 有效期（秒）
  jwtExpiresIn: 7 * 24 * 60 * 60, // 7 天

  // bcrypt cost factor
  bcryptRounds: 12,

  // 轮询间隔（毫秒）
  pollIntervalMs: 2000,

  // 最大轮询等待时间（毫秒）
  maxPollTimeMs: 10 * 60 * 1000, // 10 分钟（与 Python 节点对齐）

  // 定价缓存 TTL（毫秒）
  pricingCacheTtlMs: 60 * 1000, // 1 分钟

  // 限流配置
  rateLimit: {
    windowMs: 60 * 1000, // 1 分钟窗口
    maxRequestsPerWindow: 60, // 每窗口最大请求数
  },

  // SMS 验证码有效期（毫秒）
  smsCodeExpiryMs: 5 * 60 * 1000, // 5 分钟

  // DeepSeek API 地址
  deepseekBaseUrl: 'https://api.deepseek.com/v1',

  // DashScope API 地址（阿里云兼容模式）
  dashscopeBaseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',

  // muapi.ai 端点
  muapi: {
    fluxSchnell: 'https://api.muapi.ai/api/v1/flux-schnell',
    seedanceT2V: 'https://api.muapi.ai/api/v1/seedance-v2.0-t2v',
    seedanceI2V: 'https://api.muapi.ai/api/v1/seedance-v2.0-i2v',
    predictionResult: (taskId: string) =>
      `https://api.muapi.ai/api/v1/predictions/${taskId}/result`,
  },
};

/**
 * 校验必需的配置项，缺失时发出警告
 */
export function validateConfig(): string[] {
  const warnings: string[] = [];

  if (!config.deepseekApiKey) {
    warnings.push('DEEPSEEK_API_KEY 未设置，DeepSeek 导演功能将不可用');
  }
  if (!config.dashscopeApiKey) {
    warnings.push('DASHSCOPE_API_KEY 未设置，Qwen VL 图像分析将不可用');
  }
  if (!config.muapiKey) {
    warnings.push('MUAPI_KEY 未设置，Seedance 视频生成将不可用');
  }
  if (!config.falKey) {
    warnings.push('FAL_KEY 未设置，Flux 预览图将降级（preview_url=null）');
  }
  if (!config.smsAccessKeyId || !config.smsTemplateCode) {
    warnings.push('SMS_ACCESS_KEY_ID / SMS_TEMPLATE_CODE 未设置，短信验证码将仅打印到控制台');
  }
  if (!config.resendApiKey) {
    warnings.push('RESEND_API_KEY 未设置，邮件验证码将仅打印到控制台');
  }
  if (!config.xunhupayAppId || !config.xunhupayAppSecret) {
    warnings.push('XUNHUPAY_APPID / XUNHUPAY_APPSECRET 未设置，支付功能将不可用');
  }
  if (config.jwtSecret === 'dev-secret-change-in-production') {
    warnings.push('JWT_SECRET 使用默认值，生产环境请修改');
  }
  if (config.region === 'intl' && !config.googleClientId) {
    warnings.push('GOOGLE_CLIENT_ID 未设置，海外版 Google 登录将不可用');
  }
  if (config.region === 'intl' && !config.stripeSecretKey) {
    warnings.push('STRIPE_SECRET_KEY 未设置，海外版支付将不可用（支付暂未上线）');
  }

  return warnings;
}

console.log(`[Config] Region: ${config.region}, Currency: ${regionConfig.currency}, Locale: ${regionConfig.locale}`);
