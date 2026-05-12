// ─────────────────────────────────────────────
// 支付路由
// POST /api/payment/create   — 下单（需登录）
// POST /api/payment/notify   — 虎皮椒异步回调（无需登录，验签）
// GET  /api/payment/packages — 套餐列表（无需登录）
// ─────────────────────────────────────────────

import { Router, Request, Response, NextFunction } from 'express';
import { v4 as uuidv4 } from 'uuid';
import { config } from '../config';
import { AppError } from '../middleware/errorHandler';
import { createOrder, verifyNotify, PACKAGES, PackageKey } from '../services/xunhupay';
import { createPaymentOrder, fulfillPaymentOrder } from '../db/queries';

const router = Router();

// ═══════════════════════════════════════════════
// GET /api/payment/packages — 套餐列表
// ═══════════════════════════════════════════════

router.get('/packages', (_req: Request, res: Response) => {
  const packages = Object.entries(PACKAGES).map(([key, pkg]) => ({
    key,
    price: pkg.price,
    fenAmount: pkg.fenAmount,
    currency: config.region === 'intl' ? 'USD' : 'CNY',
  }));

  res.json({ packages });
});

// ═══════════════════════════════════════════════
// POST /api/payment/create — 下单
// ═══════════════════════════════════════════════

router.post('/create', async (req: Request, res: Response, next: NextFunction) => {
  try {
    if (!config.xunhupayAppId || !config.xunhupayAppSecret) {
      res.status(501).json({
        code: 'NOT_IMPLEMENTED',
        message: '支付功能即将上线，敬请期待。',
      });
      return;
    }

    const { package_key, pay_type } = req.body;

    if (!package_key || !PACKAGES[package_key as PackageKey]) {
      throw AppError.badRequest(
        `无效的套餐。可选值: ${Object.keys(PACKAGES).join(', ')}`
      );
    }

    if (!['alipay', 'wechat'].includes(pay_type)) {
      throw AppError.badRequest('支付方式无效，可选值: alipay, wechat');
    }

    const userId = req.user!.userId;
    const outTradeNo = uuidv4();
    const pkg = PACKAGES[package_key as PackageKey];

    // 写 DB：创建待支付订单
    await createPaymentOrder(userId, outTradeNo, package_key, pkg.price, pkg.fenAmount);

    // 调虎皮椒下单
    const result = await createOrder(
      package_key as PackageKey,
      pay_type,
      outTradeNo
    );

    res.json({
      order_id: result.orderId,
      pay_url: result.payUrl,
      qr_code: result.qrCode || null,
      amount: pkg.price,
      fen_amount: pkg.fenAmount,
      currency: config.region === 'intl' ? 'USD' : 'CNY',
    });
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// POST /api/payment/notify — 虎皮椒异步回调
// ═══════════════════════════════════════════════

router.post('/notify', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const params = req.body as Record<string, string>;

    // 验签
    if (!verifyNotify(params)) {
      console.warn('[Payment] Notify signature verification failed');
      res.status(400).send('sign error');
      return;
    }

    const { out_trade_no, return_code } = params;

    if (return_code !== 'SUCCESS') {
      console.warn(`[Payment] Payment failed for order ${out_trade_no}: ${params.return_msg}`);
      res.send('success'); // 虎皮椒要求返回 success
      return;
    }

    // 核销订单（幂等）
    const fulfilled = await fulfillPaymentOrder(out_trade_no);
    if (fulfilled) {
      console.log(`[Payment] Order fulfilled: ${out_trade_no}`);
    } else {
      console.log(`[Payment] Duplicate or unknown order: ${out_trade_no}`);
    }

    res.send('success');
  } catch (err) {
    next(err);
  }
});

export default router;
