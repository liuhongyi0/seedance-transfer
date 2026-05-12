// ─────────────────────────────────────────────
// API Key 管理路由: /api/keys
// GET    /api/keys      — 列出当前用户的所有 Key
// POST   /api/keys      — 创建新 Key（仅此一次返回明文）
// DELETE /api/keys/:id   — 撤销 Key
// ─────────────────────────────────────────────

import { Router, Request, Response, NextFunction } from 'express';
import crypto from 'crypto';
import { sha256 } from '../middleware/auth';
import {
  createApiKey,
  listApiKeys,
  revokeApiKey,
} from '../db/queries';
import { CreateKeyResponse, KeyListResponse } from '../types';
import { AppError } from '../middleware/errorHandler';

const router = Router();

/**
 * 生成一个新的 API Key
 * 格式: sk-seed-{16位hex随机字符}
 */
function generateApiKey(): { fullKey: string; keyPrefix: string; keyHash: string } {
  const randomPart = crypto.randomBytes(8).toString('hex'); // 16 hex chars
  const fullKey = `sk-seed-${randomPart}`;
  const keyPrefix = fullKey.substring(0, 16); // "sk-seed-XXXXXXXX"
  const keyHash = sha256(fullKey);
  return { fullKey, keyPrefix, keyHash };
}

// ═══════════════════════════════════════════════
// GET /api/keys — 列出所有 Key
// ═══════════════════════════════════════════════

router.get('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.user!.userId;
    const keys = await listApiKeys(userId);

    const response: KeyListResponse = { keys };
    res.json(response);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// POST /api/keys — 创建新 Key
// ═══════════════════════════════════════════════

router.post('/', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.user!.userId;
    const { name } = req.body;

    const keyName = (typeof name === 'string' && name.trim()) || 'My Key';
    const { fullKey, keyPrefix, keyHash } = generateApiKey();

    const apiKey = await createApiKey(userId, keyName, keyPrefix, keyHash);

    console.log(
      `[Keys] Created key ${apiKey.id} (${keyPrefix}...) for user ${userId}`
    );

    const response: CreateKeyResponse = {
      key: fullKey,
      detail: apiKey,
    };

    res.status(201).json(response);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// DELETE /api/keys/:id — 撤销 Key
// ═══════════════════════════════════════════════

router.delete('/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = req.user!.userId;
    const keyId = req.params.id as string;

    if (!keyId) {
      throw AppError.badRequest('缺少 Key ID');
    }

    const revoked = await revokeApiKey(keyId, userId);

    if (!revoked) {
      throw AppError.notFound('Key 不存在或已撤销');
    }

    console.log(`[Keys] Revoked key ${keyId} for user ${userId}`);
    res.status(204).send();
  } catch (err) {
    next(err);
  }
});

export default router;
