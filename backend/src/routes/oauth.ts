// ─────────────────────────────────────────────
// OAuth & Email 认证路由: /api/auth/*
// POST /api/auth/google          — Google OAuth 登录
// POST /api/auth/email/register  — 邮箱注册
// POST /api/auth/email/login     — 邮箱登录
// 注意：此路由在白名单中，不需要 Bearer token
// ─────────────────────────────────────────────

import { Router, Request, Response, NextFunction } from 'express';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import { OAuth2Client } from 'google-auth-library';
import { config } from '../config';
import {
  findUserByEmail,
  findUserByGoogleId,
  createUserWithEmail,
  createUserWithGoogle,
} from '../db/queries';
import {
  GoogleLoginRequest,
  EmailRegisterRequest,
  EmailLoginRequest,
  RegisterResponse,
  LoginResponse,
} from '../types';
import { AppError } from '../middleware/errorHandler';
import { sendVerificationCode } from '../services/mail';

const router = Router();

// ── 邮箱验证码内存存储 ─────────────────────────

interface EmailCodeEntry {
  code: string;
  expires: number;
}

const emailCodeStore = new Map<string, EmailCodeEntry>();

setInterval(() => {
  const now = Date.now();
  for (const [key, entry] of emailCodeStore.entries()) {
    if (now > entry.expires) emailCodeStore.delete(key);
  }
}, 60_000);

function verifyEmailCode(email: string, code: string): boolean {
  const entry = emailCodeStore.get(email);
  if (!entry) return false;
  if (Date.now() > entry.expires) {
    emailCodeStore.delete(email);
    return false;
  }
  return entry.code === code;
}

// ── Google OAuth2 客户端（惰性初始化）───────────────

let googleClient: OAuth2Client | null = null;

function getGoogleClient(): OAuth2Client {
  if (!googleClient) {
    googleClient = new OAuth2Client(config.googleClientId);
  }
  return googleClient;
}

// ── 邮箱格式校验 ──────────────────────────────

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validateEmail(email: string): boolean {
  return EMAIL_REGEX.test(email);
}

// ═══════════════════════════════════════════════
// POST /api/auth/google — Google OAuth 登录
// ═══════════════════════════════════════════════

router.post('/google', async (req: Request, res: Response, next: NextFunction) => {
  try {
    // 区域守卫：仅海外版支持 Google 登录
    if (config.region !== 'intl' || !config.googleClientId) {
      res.status(501).json({
        code: 'NOT_IMPLEMENTED',
        message: 'Google 登录仅支持海外版 / Google login is only available in the international version',
      });
      return;
    }

    const { id_token }: GoogleLoginRequest = req.body;

    if (!id_token || typeof id_token !== 'string') {
      throw AppError.badRequest('缺少必填参数: id_token');
    }

    // 验证 Google ID Token
    let payload;
    try {
      const client = getGoogleClient();
      const ticket = await client.verifyIdToken({
        idToken: id_token,
        audience: config.googleClientId,
      });
      payload = ticket.getPayload();
    } catch (err: any) {
      console.error('[Google OAuth] Token verification failed:', err.message);
      throw AppError.unauthorized('Google 令牌验证失败: ' + (err.message || '未知错误'));
    }

    if (!payload || !payload.sub) {
      throw AppError.unauthorized('Google 令牌缺少用户标识');
    }

    const googleId = payload.sub;
    const email = payload.email || null;
    const avatarUrl = payload.picture || null;

    // 查找或创建用户
    let user = await findUserByGoogleId(googleId);
    if (!user) {
      user = await createUserWithGoogle(email, googleId, avatarUrl);
      console.log(`[OAuth] Google user registered: ${user.id} (${email || 'no-email'}, google:${googleId})`);
    } else {
      if (!user.is_active) {
        throw AppError.unauthorized('账号已被禁用');
      }
      console.log(`[OAuth] Google user logged in: ${user.id} (${email || 'no-email'})`);
    }

    // 生成 JWT
    const tokenPayload = {
      userId: user.id,
      sub: user.id,
      iat: Math.floor(Date.now() / 1000),
    };

    const accessToken = jwt.sign(tokenPayload, config.jwtSecret, {
      expiresIn: config.jwtExpiresIn,
    });

    const response: LoginResponse = {
      access_token: accessToken,
      token_type: 'Bearer',
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// POST /api/auth/email/send-code — 发送邮箱验证码
// ═══════════════════════════════════════════════

router.post('/email/send-code', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { email } = req.body;

    if (!email || !validateEmail(email)) {
      throw AppError.badRequest('邮箱格式无效');
    }

    // 频率限制（60 秒）
    const existing = emailCodeStore.get(email);
    if (existing && Date.now() < existing.expires - config.smsCodeExpiryMs + 60_000) {
      throw AppError.tooMany('验证码发送过于频繁，请 60 秒后再试');
    }

    // 检查是否已注册
    let user;
    try {
      user = await findUserByEmail(email);
    } catch (dbErr: any) {
      console.error('[send-code] findUserByEmail failed:', dbErr.message, dbErr.stack);
      throw AppError.internal('数据库查询失败: ' + dbErr.message);
    }
    if (user) {
      throw AppError.conflict('该邮箱已注册');
    }

    const code = String(Math.floor(100000 + Math.random() * 900000));
    emailCodeStore.set(email, { code, expires: Date.now() + config.smsCodeExpiryMs });

    try {
      await sendVerificationCode(email, code);
    } catch (mailErr: any) {
      console.error('[send-code] sendVerificationCode threw:', mailErr.message, mailErr.stack);
      // non-fatal: code is already stored, continue
    }

    res.json({ message: '验证码已发送' });
  } catch (err) {
    console.error('[send-code] Unexpected error:', err instanceof Error ? err.message : String(err));
    next(err);
  }
});

// ═══════════════════════════════════════════════
// POST /api/auth/email/register — 邮箱注册
// ═══════════════════════════════════════════════

router.post('/email/register', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { email, password, code }: EmailRegisterRequest & { code?: string } = req.body;

    if (!email || !validateEmail(email)) {
      throw AppError.badRequest('邮箱格式无效');
    }

    if (!password || password.length < 8) {
      throw AppError.badRequest('密码长度至少 8 位');
    }

    // 验证邮箱验证码
    if (!code || code.length !== 6) {
      throw AppError.badRequest('验证码格式无效');
    }

    if (!verifyEmailCode(email, code)) {
      throw AppError.badRequest('验证码无效或已过期');
    }

    emailCodeStore.delete(email);

    const existing = await findUserByEmail(email);
    if (existing) {
      throw AppError.conflict('该邮箱已注册');
    }

    const passwordHash = await bcrypt.hash(password, config.bcryptRounds);
    const user = await createUserWithEmail(email, passwordHash);

    console.log(`[OAuth] Email user registered: ${user.id} (${email})`);

    res.status(201).json({
      user_id: user.id,
      message: '注册成功',
    } as RegisterResponse);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// POST /api/auth/email/login — 邮箱登录
// ═══════════════════════════════════════════════

router.post('/email/login', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { email, password }: EmailLoginRequest = req.body;

    if (!email || !password) {
      throw AppError.badRequest('邮箱和密码不能为空');
    }

    // 查找用户
    const user = await findUserByEmail(email);
    if (!user || user.auth_provider !== 'email') {
      throw AppError.unauthorized('邮箱或密码错误');
    }

    // 验证密码
    const passwordHash = user.password_hash;
    if (!passwordHash) {
      throw AppError.internal('账号数据异常，请联系客服');
    }

    const isValid = await bcrypt.compare(password, passwordHash);
    if (!isValid) {
      throw AppError.unauthorized('邮箱或密码错误');
    }

    if (!user.is_active) {
      throw AppError.unauthorized('账号已被禁用');
    }

    // 生成 JWT
    const tokenPayload = {
      userId: user.id,
      sub: user.id,
      iat: Math.floor(Date.now() / 1000),
    };

    const accessToken = jwt.sign(tokenPayload, config.jwtSecret, {
      expiresIn: config.jwtExpiresIn,
    });

    console.log(`[OAuth] Email user logged in: ${user.id} (${email})`);

    const response: LoginResponse = {
      access_token: accessToken,
      token_type: 'Bearer',
    };

    res.json(response);
  } catch (err) {
    next(err);
  }
});

export default router;
