// ─────────────────────────────────────────────
// 虎皮椒（xunhupay.com）支付服务
// 个人开发者无需营业执照，支持支付宝+微信
// ─────────────────────────────────────────────

import crypto from 'crypto';
import { config } from '../config';

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
  orderId: string;
  payUrl:  string;
  qrCode?: string;
}

export async function createOrder(
  packageKey: PackageKey,
  payType: 'alipay' | 'wechat',
  outTradeNo: string,
): Promise<CreateOrderResult> {
  if (!config.xunhupayAppId || !config.xunhupayAppSecret) {
    throw new Error('支付未配置：请设置 XUNHUPAY_APPID 和 XUNHUPAY_APPSECRET');
  }

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
    body: new URLSearchParams(params).toString(),
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
