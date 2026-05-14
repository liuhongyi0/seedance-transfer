// ─────────────────────────────────────────────
// 余额 & 用量路由
// GET /api/balance — 查询余额
// GET /api/usage   — 查询用量历史
// ─────────────────────────────────────────────

import { Router, Request, Response, NextFunction } from 'express';
import { getBalance, getUsageLogs } from '../db/queries';
import { BalanceResponse, UsageListResponse, ServiceType } from '../types';
import { AppError } from '../middleware/errorHandler';
import { getCurrency } from '../services/pricing';

const router = Router();

// ═══════════════════════════════════════════════
// GET /api/balance — 查询余额
// ═══════════════════════════════════════════════

router.get('/balance', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.user!.userId;
    const amountFen = await getBalance(userId);

    const response: BalanceResponse = {
      amount_fen: amountFen,
      amount: Math.round(amountFen) / 100,
      currency: getCurrency(),
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// GET /api/usage — 查询用量历史
// ═══════════════════════════════════════════════

router.get('/usage', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.user!.userId;
    const page = Math.max(1, parseInt(req.query.page as string) || 1);
    const pageSize = Math.min(
      100,
      Math.max(1, parseInt(req.query.page_size as string) || 20)
    );

    const serviceParam = req.query.service as string | undefined;
    const validServices: ServiceType[] = [
      'deepseek',
      'qwen_vl',
      'flux_preview',
      'seedance_t2v',
      'seedance_i2v',
    ];

    let service: ServiceType | undefined;
    if (serviceParam && validServices.includes(serviceParam as ServiceType)) {
      service = serviceParam as ServiceType;
    }

    const result = await getUsageLogs(userId, page, pageSize, service);

    const response: UsageListResponse = {
      total: result.total,
      page,
      items: result.items,
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

export default router;
