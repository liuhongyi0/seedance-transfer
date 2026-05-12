// ─────────────────────────────────────────────
// 费用预估路由
// POST /api/estimate — 预估生成费用（不扣费）
// ─────────────────────────────────────────────

import { Router, Request, Response, NextFunction } from 'express';
import { estimateVideoCost, fenToYuan } from '../services/pricing';
import { EstimateRequest, EstimateResponse, VideoMode, Quality } from '../types';
import { AppError } from '../middleware/errorHandler';

const router = Router();

// ═══════════════════════════════════════════════
// POST /api/estimate — 费用预估
// ═══════════════════════════════════════════════

router.post('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { mode, duration, quality }: EstimateRequest = req.body;

    // 参数验证
    const validModes: VideoMode[] = ['text_to_video', 'image_to_video'];
    if (!mode || !validModes.includes(mode)) {
      throw AppError.badRequest(
        '请指定有效的生成模式: text_to_video 或 image_to_video'
      );
    }

    const dur = duration || 5;
    if (dur < 4 || dur > 15) {
      throw AppError.badRequest('视频时长需在 4-15 秒之间');
    }

    const qual = quality || 'high';
    if (qual !== 'basic' && qual !== 'high') {
      throw AppError.badRequest('画质参数无效，可选: basic 或 high');
    }

    const costFen = await estimateVideoCost(mode, dur, qual);

    const response: EstimateResponse = {
      cost_fen: costFen,
      cost_yuan: fenToYuan(costFen),
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

export default router;
