// ─────────────────────────────────────────────
// 简易限流中间件（内存实现，单进程适用）
// 按 userId + IP 组合限流
// ─────────────────────────────────────────────

import { Request, Response, NextFunction } from 'express';
import { config } from '../config';

interface RateLimitEntry {
  count: number;
  resetAt: number;
}

const store = new Map<string, RateLimitEntry>();

// 定期清理过期条目（每 5 分钟）
setInterval(() => {
  const now = Date.now();
  for (const [key, entry] of store.entries()) {
    if (now > entry.resetAt + 60_000) {
      store.delete(key);
    }
  }
}, 5 * 60 * 1000);

/**
 * 获取限流标识
 * 优先使用 userId（已认证用户），否则使用 IP
 */
function getRateLimitKey(req: Request): string {
  if (req.user?.userId) {
    return `user:${req.user.userId}`;
  }
  const ip =
    (req.headers['x-forwarded-for'] as string)?.split(',')[0]?.trim() ||
    req.socket.remoteAddress ||
    'unknown';
  return `ip:${ip}`;
}

/**
 * 限流中间件
 */
export function rateLimiter(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  // 白名单路径不限流
  if (req.path.startsWith('/api/auth')) {
    next();
    return;
  }

  const key = getRateLimitKey(req);
  const now = Date.now();
  const windowMs = config.rateLimit.windowMs;
  const maxRequests = config.rateLimit.maxRequestsPerWindow;

  let entry = store.get(key);

  if (!entry || now > entry.resetAt) {
    // 新窗口
    entry = {
      count: 1,
      resetAt: now + windowMs,
    };
    store.set(key, entry);
    next();
    return;
  }

  entry.count++;

  if (entry.count > maxRequests) {
    const retryAfterSec = Math.ceil((entry.resetAt - now) / 1000);
    res.set('Retry-After', String(retryAfterSec));
    res.set('X-RateLimit-Limit', String(maxRequests));
    res.set('X-RateLimit-Remaining', '0');
    res.status(429).json({
      code: 'RATE_LIMITED',
      message: `请求过于频繁，请 ${retryAfterSec} 秒后重试`,
    });
    return;
  }

  // 设置限流头
  res.set('X-RateLimit-Limit', String(maxRequests));
  res.set('X-RateLimit-Remaining', String(maxRequests - entry.count));
  res.set('X-RateLimit-Reset', String(Math.ceil(entry.resetAt / 1000)));

  next();
}
