// ─────────────────────────────────────────────
// Seedance Wizard API Server
// Express 入口 — 加载中间件、挂载路由、启动服务
// ─────────────────────────────────────────────

import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { v4 as uuidv4 } from 'uuid';

// 环境变量（优先加载）
dotenv.config();

import { config, validateConfig } from './config';
import { testConnection, query } from './db/pool';
import { runMigrations } from './db/migrate';
import { recoverOrphanedPolls } from './routes/video';
import { authMiddleware } from './middleware/auth';
import { rateLimiter } from './middleware/rateLimit';
import { errorHandler } from './middleware/errorHandler';

// 路由模块
import authRoutes from './routes/auth';
import keysRoutes from './routes/keys';
import balanceRoutes from './routes/balance';
import wizardRoutes from './routes/wizard';
import videoRoutes from './routes/video';
import estimateRoutes from './routes/estimate';
import oauthRoutes from './routes/oauth';
import paymentRoutes from './routes/payment';

// ── 创建 Express 应用 ────────────────────────

const app = express();

// ── 全局中间件 ────────────────────────────────

// CORS（允许 ComfyUI 侧边栏跨域）
app.use(
  cors({
    origin: true,
    credentials: true,
    maxAge: 86400,
  })
);

// JSON Body Parser（限制 50MB，支持 base64 图片上传）
app.use(express.json({ limit: '50mb' }));

// 请求 ID 注入（调试追踪）
app.use((req, _res, next) => {
  req.requestId = uuidv4();
  next();
});

// 请求日志
app.use((req, _res, next) => {
  const startTime = Date.now();
  const origEnd = _res.end;

  const origEndFn = origEnd as (...args: any[]) => any;
  _res.end = function (...args: any[]) {
    const elapsed = Date.now() - startTime;
    console.log(
      `[HTTP] ${req.method} ${req.path} ${_res.statusCode} ${elapsed}ms`
    );
    return origEndFn.apply(_res, args as any);
  } as any;

  next();
});

// 限流
app.use(rateLimiter);

// 健康检查（无需认证，必须在 authMiddleware 之前注册）
app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    service: 'seedance-wizard-api',
    version: '0.1.0',
    timestamp: new Date().toISOString(),
  });
});

// 认证（白名单 /api/auth/* 自动跳过）
app.use(authMiddleware);

// ── 路由挂载 ──────────────────────────────────

app.use('/api/auth', authRoutes);
app.use('/api/auth', oauthRoutes);
app.use('/api/keys', keysRoutes);
app.use('/api', balanceRoutes); // /api/balance, /api/usage
app.use('/api/wizard', wizardRoutes);
app.use('/api/video', videoRoutes);
app.use('/api/estimate', estimateRoutes);
app.use('/api/payment', paymentRoutes);

// ── 健康检查 ──────────────────────────────────

// 已在 auth 中间件之前注册

// ── 404 处理 ──────────────────────────────────

app.use((_req, res) => {
  res.status(404).json({
    code: 'NOT_FOUND',
    message: `接口不存在: ${_req.method} ${_req.path}`,
  });
});

// ── 统一错误处理 ──────────────────────────────

app.use(errorHandler);

// ── 启动服务 ──────────────────────────────────

const PORT = config.port;

async function start(): Promise<void> {
  console.log('╔══════════════════════════════════════════╗');
  console.log('║   Seedance Wizard API Server v0.1.0     ║');
  console.log('╚══════════════════════════════════════════╝');
  console.log('');

  // 配置校验
  const warnings = validateConfig();
  if (warnings.length > 0) {
    console.warn('[Config] Warnings:');
    warnings.forEach((w) => console.warn(`  - ${w}`));
    console.warn('');
  }

  // 数据库连接 & 迁移
  let dbConnected = false;
  try {
    dbConnected = await testConnection();
    if (dbConnected) {
      try {
        await runMigrations();
        console.log('[DB] Migrations applied successfully');
      } catch (migErr: any) {
        console.error('[DB] Migration error:', migErr.message);
        console.warn('[DB] Server will start without running migrations');
      }

      // 恢复上次运行时未完成的视频轮询（迁移失败也应恢复）
      try {
        const recovered = await recoverOrphanedPolls();
        if (recovered > 0) {
          console.log(`[Video] Recovered ${recovered} orphaned polls from previous run`);
        }
      } catch (recErr: any) {
        console.warn('[Video] Orphan recovery warning:', recErr.message);
      }
    } else {
      console.warn(
        '[DB] Database connection failed. ' +
        'Server will start but most endpoints will return errors. ' +
        'Please check DATABASE_URL in your .env file.'
      );
    }
  } catch (err: any) {
    console.error('[DB] Connection error:', err.message);
    console.warn('[DB] Server will start without database');
  }

  // 启动 HTTP 服务
  app.listen(PORT, () => {
    console.log('');
    console.log(`[Server] Listening on http://localhost:${PORT}`);
    console.log(`[Server] Health check: http://localhost:${PORT}/health`);
    console.log(`[Server] Database: ${dbConnected ? 'connected' : 'DISCONNECTED'}`);
    console.log('');

    if (!dbConnected) {
      console.warn(
        '[Server] WARNING: Running without database. ' +
        'Auth, wizard, video, and balance endpoints will fail.'
      );
    }
  });
}

// 优雅退出
process.on('SIGINT', async () => {
  console.log('\n[Server] Received SIGINT, shutting down...');
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.log('\n[Server] Received SIGTERM, shutting down...');
  process.exit(0);
});

// 未捕获异常处理
process.on('uncaughtException', (err) => {
  console.error('[Server] UNCAUGHT EXCEPTION:', err);
});

process.on('unhandledRejection', (reason) => {
  console.error('[Server] UNHANDLED REJECTION:', reason);
});

// 启动
start().catch((err) => {
  console.error('[Server] Fatal startup error:', err);
  process.exit(1);
});

export default app;
