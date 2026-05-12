// ─────────────────────────────────────────────
// 认证中间件 — Bearer Token 验证
// 支持两种 Token 类型：
//   1. API Key（sk-seed-xxx）→ SHA-256 哈希 + DB 验证
//   2. JWT（用户登录获取）→ JWT 签名验证 + DB 余额查询
// 白名单：/api/auth/* 不需认证
// ─────────────────────────────────────────────

import { Request, Response, NextFunction } from 'express';
import crypto from 'crypto';
import jwt from 'jsonwebtoken';
import { config } from '../config';
import { verifyApiKey, getBalance } from '../db/queries';

/**
 * JWT Payload 结构
 */
interface JwtPayload {
  userId: string;
  sub: string;
  iat: number;
  exp: number;
}

/**
 * 白名单路径前缀（不需要认证）
 */
const AUTH_WHITELIST = [
  '/api/auth',
  '/api/payment/packages',
  '/api/payment/notify',
];

function isWhitelisted(path: string): boolean {
  return AUTH_WHITELIST.some((prefix) => path.startsWith(prefix));
}

/**
 * 对字符串做 SHA-256 哈希，返回 hex 字符串
 */
function sha256(input: string): string {
  return crypto.createHash('sha256').update(input).digest('hex');
}

/**
 * 认证中间件
 */
export async function authMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  // 白名单路径跳过
  if (isWhitelisted(req.path)) {
    next();
    return;
  }

  const authHeader = req.headers.authorization;

  if (!authHeader) {
    res.status(401).json({
      code: 'UNAUTHORIZED',
      message: '缺少认证信息，请在 Authorization header 中提供 Bearer token',
    });
    return;
  }

  const parts = authHeader.split(' ');
  if (parts.length !== 2 || parts[0] !== 'Bearer') {
    res.status(401).json({
      code: 'UNAUTHORIZED',
      message: '认证格式错误，请使用: Authorization: Bearer <token>',
    });
    return;
  }

  const token = parts[1].trim();

  if (!token) {
    res.status(401).json({
      code: 'UNAUTHORIZED',
      message: 'Token 不能为空',
    });
    return;
  }

  try {
    // 判断 Token 类型
    if (token.startsWith('sk-seed-')) {
      // ── API Key 验证 ───────────────────────
      await verifyApiKeyToken(token, req);
    } else {
      // ── JWT 验证 ────────────────────────────
      await verifyJwtToken(token, req);
    }

    next();
  } catch (err: any) {
    console.error('[Auth] Verification error:', err.message);

    if (err.name === 'TokenExpiredError') {
      res.status(401).json({
        code: 'TOKEN_EXPIRED',
        message: 'Token 已过期，请重新登录',
      });
      return;
    }

    if (err.name === 'JsonWebTokenError') {
      res.status(401).json({
        code: 'INVALID_TOKEN',
        message: 'Token 无效',
      });
      return;
    }

    res.status(401).json({
      code: 'UNAUTHORIZED',
      message: '认证失败：' + (err.message || '未知错误'),
    });
  }
}

/**
 * 验证 API Key（sk-seed-xxx 格式）
 */
async function verifyApiKeyToken(
  token: string,
  req: Request
): Promise<void> {
  const keyHash = sha256(token);
  const result = await verifyApiKey(keyHash);

  if (!result) {
    throw new Error('API Key 无效或已过期');
  }

  req.user = {
    userId: result.userId,
    apiKeyId: result.apiKeyId,
    balanceFen: result.balanceFen,
  };
}

/**
 * 验证 JWT Token
 */
async function verifyJwtToken(
  token: string,
  req: Request
): Promise<void> {
  const payload = jwt.verify(token, config.jwtSecret) as JwtPayload;

  if (!payload.userId) {
    throw new Error('JWT 缺少 userId');
  }

  // 查询最新余额
  const balanceFen = await getBalance(payload.userId);

  req.user = {
    userId: payload.userId,
    balanceFen,
  };
}

/**
 * 导出 sha256 工具函数供路由使用（创建 API Key 时做 hash）
 */
export { sha256 };
