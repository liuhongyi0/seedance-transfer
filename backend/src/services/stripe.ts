// ─────────────────────────────────────────────
// Stripe 支付服务（预留，支付暂未上线）
// ─────────────────────────────────────────────

import { config } from '../config';

export function isStripeAvailable(): boolean {
  return config.region === 'intl' && !!config.stripeSecretKey;
}

export async function createCheckoutSession(
  _userId: string,
  _packageId: string
): Promise<{ sessionUrl: string }> {
  throw new Error('Stripe 支付暂未上线');
}

export async function verifyWebhook(
  _rawBody: Buffer,
  _signature: string
): Promise<{ event: string; customerId?: string; amount?: number }> {
  throw new Error('Stripe webhook 暂未上线');
}
