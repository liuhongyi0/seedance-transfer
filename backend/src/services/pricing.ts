// ─────────────────────────────────────────────
// 定价计算服务
// 从 system_config 表读取定价，缓存 60 秒
// 国内版：分（fen）/ 海外版：美分（cents）
// 区域自适应：优先读 DB system_config，fallback YAML
// ─────────────────────────────────────────────

import { getPricing as getDbPricing } from '../db/queries';
import { ServiceType, VideoMode, Quality, PricingConfig } from '../types';
import { config } from '../config';

/**
 * 获取当前区域的完整定价（合并 DB 覆盖 + YAML fallback）
 */
export async function getPricing(): Promise<PricingConfig> {
  const dbPricing = await getDbPricing();
  const regionPricing = config.regionConfig.pricing;

  // DB system_config 为最高优先级；若无则用 YAML
  if (config.region === 'intl') {
    return {
      deepseek_input_per_1m_fen: dbPricing.deepseek_input_per_1m_fen || regionPricing.deepseek_input_per_1m_subunit,
      deepseek_output_per_1m_fen: dbPricing.deepseek_output_per_1m_fen || regionPricing.deepseek_output_per_1m_subunit,
      qwen_vl_per_1m_fen: dbPricing.qwen_vl_per_1m_fen || regionPricing.qwen_vl_per_1m_subunit,
      flux_preview_per_image_fen: dbPricing.flux_preview_per_image_fen || regionPricing.flux_preview_per_image_subunit,
      seedance_t2v_basic_per_sec_fen: dbPricing.seedance_t2v_basic_per_sec_fen || regionPricing.seedance_t2v_basic_per_sec_subunit,
      seedance_t2v_high_per_sec_fen: dbPricing.seedance_t2v_high_per_sec_fen || regionPricing.seedance_t2v_high_per_sec_subunit,
      seedance_i2v_basic_per_sec_fen: dbPricing.seedance_i2v_basic_per_sec_fen || regionPricing.seedance_i2v_basic_per_sec_subunit,
      seedance_i2v_high_per_sec_fen: dbPricing.seedance_i2v_high_per_sec_fen || regionPricing.seedance_i2v_high_per_sec_subunit,
      deepseek_input_per_1m_subunit: regionPricing.deepseek_input_per_1m_subunit,
      deepseek_output_per_1m_subunit: regionPricing.deepseek_output_per_1m_subunit,
      qwen_vl_per_1m_subunit: regionPricing.qwen_vl_per_1m_subunit,
      flux_preview_per_image_subunit: regionPricing.flux_preview_per_image_subunit,
      seedance_t2v_basic_per_sec_subunit: regionPricing.seedance_t2v_basic_per_sec_subunit,
      seedance_t2v_high_per_sec_subunit: regionPricing.seedance_t2v_high_per_sec_subunit,
      seedance_i2v_basic_per_sec_subunit: regionPricing.seedance_i2v_basic_per_sec_subunit,
      seedance_i2v_high_per_sec_subunit: regionPricing.seedance_i2v_high_per_sec_subunit,
      currency: 'USD',
    };
  }

  // 国内版：返回 fen 定价
  return {
    ...dbPricing,
    currency: 'CNY',
  };
}

/**
 * 计算 DeepSeek 对话费用
 *
 * @param inputTokens  - 输入 token 数
 * @param outputTokens - 输出 token 数
 * @returns 费用（子单位：国内分/海外美分）
 */
export async function calculateDeepseekCost(
  inputTokens: number,
  outputTokens: number
): Promise<number> {
  const pricing = await getPricing();
  const inputCost =
    (inputTokens / 1_000_000) * pricing.deepseek_input_per_1m_fen;
  const outputCost =
    (outputTokens / 1_000_000) * pricing.deepseek_output_per_1m_fen;
  return Math.ceil(inputCost + outputCost);
}

/**
 * 计算 Qwen VL 费用（按 total tokens 统一计价）
 *
 * @param totalTokens - 总 token 数
 * @returns 费用（子单位）
 */
export async function calculateQwenCost(
  totalTokens: number
): Promise<number> {
  const pricing = await getPricing();
  const cost = (totalTokens / 1_000_000) * pricing.qwen_vl_per_1m_fen;
  return Math.ceil(cost);
}

/**
 * 计算 Flux 预览费用
 *
 * @param imageCount - 生成张数（通常为 1）
 * @returns 费用（子单位）
 */
export async function calculateFluxPreviewCost(
  imageCount: number = 1
): Promise<number> {
  const pricing = await getPricing();
  return pricing.flux_preview_per_image_fen * imageCount;
}

/**
 * 预估视频生成费用
 *
 * @param mode     - 生成模式
 * @param duration - 视频时长（秒）
 * @param quality  - 画质（basic/high）
 * @returns 费用（子单位）
 */
export async function estimateVideoCost(
  mode: VideoMode,
  duration: number,
  quality: Quality
): Promise<number> {
  const pricing = await getPricing();

  if (mode === 'text_to_video') {
    if (quality === 'high') {
      return pricing.seedance_t2v_high_per_sec_fen * duration;
    }
    return pricing.seedance_t2v_basic_per_sec_fen * duration;
  } else {
    if (quality === 'high') {
      return pricing.seedance_i2v_high_per_sec_fen * duration;
    }
    return pricing.seedance_i2v_basic_per_sec_fen * duration;
  }
}

/**
 * 计算实际视频费用（基于实际时长）
 */
export async function calculateActualVideoCost(
  mode: VideoMode,
  actualDurationSeconds: number,
  quality: Quality
): Promise<number> {
  return estimateVideoCost(mode, actualDurationSeconds, quality);
}

/**
 * 获取完整定价配置（供前端展示）
 */
export async function getPricingConfig(): Promise<PricingConfig> {
  return getPricing();
}

/**
 * 将子单位转为可读金额字符串
 * 国内版: 100 fen = 1 CNY; 海外版: 100 cents = 1 USD
 */
export function formatAmount(subunit: number, currency?: string): string {
  const cur = currency || config.regionConfig.currency;
  const amount = Math.round(subunit) / 100;
  if (cur === 'USD') {
    return `$${amount.toFixed(2)}`;
  }
  return `¥${amount.toFixed(2)}`;
}

/**
 * 将分/美分转为元/美元（保留两位小数）
 */
export function fenToYuan(fen: number): number {
  return Math.round(fen) / 100;
}

/**
 * 获取当前区域的货币代码
 */
export function getCurrency(): string {
  return config.regionConfig.currency;
}
