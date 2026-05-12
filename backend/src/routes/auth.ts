// ─────────────────────────────────────────────
// 认证路由: /api/auth/*
// POST /api/auth/register  — 手机号注册
// POST /api/auth/login     — 登录获取 Token
// POST /api/auth/sms       — 发送短信验证码
// 注意：此路由在白名单中，不需要 Bearer token
// ─────────────────────────────────────────────

import { Router, Request, Response, NextFunction } from 'express';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import crypto from 'crypto';
import { config } from '../config';
import { createUser, findUserByPhone, createApiKey, getBalance } from '../db/queries';
import { RegisterRequest, RegisterResponse, LoginRequest, LoginResponse } from '../types';
import { AppError } from '../middleware/errorHandler';
import { sendSmsCode } from '../services/sms';

const router = Router();

// ═══════════════════════════════════════════════
// 短信验证码内存存储（Mock）
// ═══════════════════════════════════════════════

interface SmsEntry {
  code: string;
  expires: number;
}

const smsStore = new Map<string, SmsEntry>();

// 定期清理过期验证码
setInterval(() => {
  const now = Date.now();
  for (const [key, entry] of smsStore.entries()) {
    if (now > entry.expires) {
      smsStore.delete(key);
    }
  }
}, 60_000);

function verifySmsCode(phone: string, code: string): boolean {
  const entry = smsStore.get(phone);
  if (!entry) return false;
  if (Date.now() > entry.expires) {
    smsStore.delete(phone);
    return false;
  }
  return entry.code === code;
}

// ═══════════════════════════════════════════════
// POST /api/auth/sms — 发送短信验证码
// ═══════════════════════════════════════════════

router.post('/sms', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { phone } = req.body;

    if (!phone || !/^1[3-9]\d{9}$/.test(phone)) {
      throw AppError.badRequest('手机号格式无效');
    }

    // 检查发送频率（60 秒内只能发一次）
    const existing = smsStore.get(phone);
    if (existing && Date.now() < existing.expires - config.smsCodeExpiryMs + 60_000) {
      throw AppError.tooMany('验证码发送过于频繁，请 60 秒后再试');
    }

    // 生成 6 位随机验证码
    const code = String(Math.floor(100000 + Math.random() * 900000));

    // 存储验证码
    smsStore.set(phone, {
      code,
      expires: Date.now() + config.smsCodeExpiryMs,
    });

    // 调用真实短信服务（未配置时自动 fallback 到 console）
    await sendSmsCode(phone, code);

    res.json({ message: '验证码已发送' });
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// POST /api/auth/register — 手机号注册
// ═══════════════════════════════════════════════

router.post('/register', async (req: Request, res: Response, next: NextFunction) => {
  try {
    // 海外版区域守卫
    if (config.region === 'intl') {
      res.status(400).json({
        code: 'BAD_REQUEST',
        message: '海外版请使用邮箱或 Google 登录 / Please use email or Google login for international version',
      });
      return;
    }

    const { phone, password, sms_code }: RegisterRequest = req.body;

    // 参数验证
    if (!phone || !/^1[3-9]\d{9}$/.test(phone)) {
      throw AppError.badRequest('手机号格式无效');
    }

    if (!password || password.length < 8) {
      throw AppError.badRequest('密码长度至少 8 位');
    }

    if (!sms_code || sms_code.length !== 6) {
      throw AppError.badRequest('验证码格式无效');
    }

    // 验证短信验证码
    if (!verifySmsCode(phone, sms_code)) {
      throw AppError.badRequest('验证码无效或已过期');
    }

    // 删除已使用的验证码
    smsStore.delete(phone);

    // 检查手机号是否已注册
    const existing = await findUserByPhone(phone);
    if (existing) {
      throw AppError.conflict('该手机号已注册');
    }

    // 密码哈希
    const passwordHash = await bcrypt.hash(password, config.bcryptRounds);

    // 创建用户（balances 表由 DB trigger 自动创建）
    const user = await createUser(phone, passwordHash);

    console.log(`[Auth] User registered: ${user.id} (${phone})`);

    const response: RegisterResponse = {
      user_id: user.id,
      message: '注册成功',
    };

    res.status(201).json(response);
  } catch (err) {
    next(err);
  }
});

// ═══════════════════════════════════════════════
// POST /api/auth/login — 登录
// ═══════════════════════════════════════════════

router.post('/login', async (req: Request, res: Response, next: NextFunction) => {
  try {
    // 海外版区域守卫
    if (config.region === 'intl') {
      res.status(400).json({
        code: 'BAD_REQUEST',
        message: '海外版请使用邮箱或 Google 登录 / Please use email or Google login for international version',
      });
      return;
    }

    const { phone, password }: LoginRequest = req.body;

    if (!phone || !password) {
      throw AppError.badRequest('手机号和密码不能为空');
    }

    // 查找用户
    const user = await findUserByPhone(phone);
    if (!user) {
      throw AppError.unauthorized('手机号或密码错误');
    }

    // 验证密码
    const passwordHash = (user as any).password_hash;
    if (!passwordHash) {
      throw AppError.internal('账号数据异常，请联系客服');
    }

    const isValid = await bcrypt.compare(password, passwordHash);
    if (!isValid) {
      throw AppError.unauthorized('手机号或密码错误');
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

    console.log(`[Auth] User logged in: ${user.id} (${phone})`);

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
