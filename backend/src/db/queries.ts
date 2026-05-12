// ─────────────────────────────────────────────
// 数据库查询封装 — 所有 DB 操作集中于此
// ─────────────────────────────────────────────

import { query, transaction } from './pool';
import {
  User,
  UserRecord,
  ApiKey,
  PricingConfig,
  WizardSessionRecord,
  VideoTaskRecord,
  ChatMessage,
  ServiceType,
  LogStatus,
} from '../types';

// ═══════════════════════════════════════════════
// 用户
// ═══════════════════════════════════════════════

export async function createUser(
  phone: string,
  passwordHash: string
): Promise<User> {
  // 读取新用户奖励配置
  const bonusResult = await query(
    `SELECT value->>'new_user_bonus_fen' AS bonus_fen
     FROM system_config WHERE key = 'new_user_bonus_fen'`
  );
  const bonusFen = bonusResult.rows.length > 0
    ? parseInt((bonusResult.rows[0] as any).bonus_fen || '0', 10)
    : 0;

  const result = await query<User>(
    `INSERT INTO users (phone, password_hash)
     VALUES ($1, $2)
     RETURNING id, phone, email, display_name, is_active,
               created_at::text AS created_at`,
    [phone, passwordHash]
  );
  const user = result.rows[0];

  // 如果有新用户奖励，更新余额（balances 表已由 trigger 创建为 0）
  if (bonusFen > 0) {
    await query(
      `UPDATE balances SET amount_fen = $1, updated_at = NOW()
       WHERE user_id = $2`,
      [bonusFen, user.id]
    );
  }

  return user;
}

export async function findUserByPhone(phone: string): Promise<User | null> {
  const result = await query<User>(
    `SELECT id, phone, email, display_name, is_active,
            password_hash,
            created_at::text AS created_at
     FROM users WHERE phone = $1`,
    [phone]
  );
  return result.rows[0] || null;
}

export async function findUserById(id: string): Promise<User | null> {
  const result = await query<User>(
    `SELECT id, phone, email, display_name, is_active,
            created_at::text AS created_at
     FROM users WHERE id = $1`,
    [id]
  );
  return result.rows[0] || null;
}

export async function findUserByEmail(email: string): Promise<UserRecord | null> {
  const result = await query<User>(
    `SELECT id, phone, email, google_id, avatar_url, display_name,
            password_hash, auth_provider, is_active,
            created_at::text AS created_at
     FROM users WHERE email = $1`,
    [email]
  );
  return result.rows[0] || null;
}

export async function findUserByGoogleId(googleId: string): Promise<UserRecord | null> {
  const result = await query<User>(
    `SELECT id, phone, email, google_id, avatar_url, display_name,
            password_hash, auth_provider, is_active,
            created_at::text AS created_at
     FROM users WHERE google_id = $1`,
    [googleId]
  );
  return result.rows[0] || null;
}

export async function createUserWithEmail(
  email: string,
  passwordHash: string
): Promise<UserRecord> {
  const bonusResult = await query(
    `SELECT value->>'new_user_bonus_fen' AS bonus_fen
     FROM system_config WHERE key = 'new_user_bonus_fen'`
  );
  const bonusFen = bonusResult.rows.length > 0
    ? parseInt((bonusResult.rows[0] as any).bonus_fen || '0', 10)
    : 0;

  const result = await query<User>(
    `INSERT INTO users (phone, email, password_hash, auth_provider)
     VALUES (NULL, $1, $2, 'email')
     RETURNING id, phone, email, google_id, avatar_url, display_name,
               auth_provider, is_active,
               created_at::text AS created_at`,
    [email, passwordHash]
  );
  const user = result.rows[0];

  if (bonusFen > 0) {
    await query(
      `UPDATE balances SET amount_fen = $1, updated_at = NOW()
       WHERE user_id = $2`,
      [bonusFen, user.id]
    );
  }

  return user;
}

export async function createUserWithGoogle(
  email: string | null,
  googleId: string,
  avatarUrl?: string | null
): Promise<UserRecord> {
  const bonusResult = await query(
    `SELECT value->>'new_user_bonus_fen' AS bonus_fen
     FROM system_config WHERE key = 'new_user_bonus_fen'`
  );
  const bonusFen = bonusResult.rows.length > 0
    ? parseInt((bonusResult.rows[0] as any).bonus_fen || '0', 10)
    : 0;

  const result = await query<User>(
    `INSERT INTO users (phone, email, google_id, avatar_url, password_hash, auth_provider)
     VALUES (NULL, $1, $2, $3, '', 'google')
     RETURNING id, phone, email, google_id, avatar_url, display_name,
               auth_provider, is_active,
               created_at::text AS created_at`,
    [email || null, googleId, avatarUrl || null]
  );
  const user = result.rows[0];

  if (bonusFen > 0) {
    await query(
      `UPDATE balances SET amount_fen = $1, updated_at = NOW()
       WHERE user_id = $2`,
      [bonusFen, user.id]
    );
  }

  return user;
}

// ═══════════════════════════════════════════════
// API Key
// ═══════════════════════════════════════════════

export async function createApiKey(
  userId: string,
  name: string,
  keyPrefix: string,
  keyHash: string
): Promise<ApiKey> {
  const result = await query<ApiKey>(
    `INSERT INTO api_keys (user_id, name, key_prefix, key_hash)
     VALUES ($1, $2, $3, $4)
     RETURNING id, name, key_prefix, is_active,
               created_at::text AS created_at,
               last_used_at::text AS last_used_at`,
    [userId, name, keyPrefix, keyHash]
  );
  return result.rows[0];
}

export async function verifyApiKey(
  keyHash: string
): Promise<{ userId: string; apiKeyId: string; balanceFen: number; isValid: boolean } | null> {
  const result = await query(
    `SELECT user_id, api_key_id, balance_fen, is_valid
     FROM verify_api_key($1)`,
    [keyHash]
  );
  if (result.rows.length === 0) return null;

  const row = result.rows[0] as any;
  if (!row.is_valid) return null;

  return {
    userId: row.user_id,
    apiKeyId: row.api_key_id,
    balanceFen: parseInt(row.balance_fen, 10),
    isValid: true,
  };
}

export async function listApiKeys(userId: string): Promise<ApiKey[]> {
  const result = await query<ApiKey>(
    `SELECT id, name, key_prefix, is_active,
            created_at::text AS created_at,
            last_used_at::text AS last_used_at
     FROM api_keys
     WHERE user_id = $1 AND is_active = TRUE
     ORDER BY created_at DESC`,
    [userId]
  );
  return result.rows;
}

export async function revokeApiKey(keyId: string, userId: string): Promise<boolean> {
  const result = await query(
    `UPDATE api_keys SET is_active = FALSE
     WHERE id = $1 AND user_id = $2 AND is_active = TRUE`,
    [keyId, userId]
  );
  return (result.rowCount ?? 0) > 0;
}

// ═══════════════════════════════════════════════
// 余额
// ═══════════════════════════════════════════════

export async function getBalance(userId: string): Promise<number> {
  const result = await query(
    `SELECT amount_fen FROM balances WHERE user_id = $1`,
    [userId]
  );
  if (result.rows.length === 0) return 0;
  return parseInt((result.rows[0] as any).amount_fen, 10);
}

export async function deductBalance(
  userId: string,
  amountFen: number
): Promise<boolean> {
  const result = await query(
    `SELECT deduct_balance($1, $2) AS success`,
    [userId, amountFen]
  );
  return (result.rows[0] as any).success === true;
}

export async function refundBalance(
  userId: string,
  amountFen: number,
  logId: string
): Promise<void> {
  await query(
    `SELECT refund_balance($1, $2, $3)`,
    [userId, amountFen, logId]
  );
}

// ═══════════════════════════════════════════════
// 用量日志
// ═══════════════════════════════════════════════

export interface CreateUsageLogParams {
  userId: string;
  apiKeyId?: string | null;
  service: ServiceType;
  units: number;
  costFen: number;
  preCostFen?: number;
  status?: LogStatus;
  upstreamTaskId?: string | null;
  requestMeta?: Record<string, any> | null;
}

export async function createUsageLog(
  params: CreateUsageLogParams
): Promise<string> {
  const result = await query<{ id: string }>(
    `INSERT INTO usage_logs
       (user_id, api_key_id, service, units, cost_fen, pre_cost_fen,
        status, upstream_task_id, request_meta)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
     RETURNING id`,
    [
      params.userId,
      params.apiKeyId || null,
      params.service,
      params.units,
      params.costFen,
      params.preCostFen || 0,
      params.status || 'pending',
      params.upstreamTaskId || null,
      params.requestMeta ? JSON.stringify(params.requestMeta) : null,
    ]
  );
  return result.rows[0].id;
}

export async function updateUsageLogStatus(
  logId: string,
  status: LogStatus,
  costFen?: number,
  errorMessage?: string
): Promise<void> {
  const fields: string[] = ['status = $2'];
  const values: any[] = [logId, status];
  let idx = 3;

  if (costFen !== undefined) {
    fields.push(`cost_fen = $${idx++}`);
    values.push(costFen);
  }
  if (errorMessage !== undefined) {
    fields.push(`error_message = $${idx++}`);
    values.push(errorMessage);
  }
  fields.push(`completed_at = NOW()`);

  await query(
    `UPDATE usage_logs SET ${fields.join(', ')} WHERE id = $1`,
    values
  );
}

export async function getUsageLogs(
  userId: string,
  page: number = 1,
  pageSize: number = 20,
  service?: ServiceType
): Promise<{ total: number; items: any[] }> {
  const offset = (page - 1) * pageSize;
  const conditions = ['user_id = $1'];
  const params: any[] = [userId];
  let idx = 2;

  if (service) {
    conditions.push(`service = $${idx++}`);
    params.push(service);
  }

  const whereClause = conditions.join(' AND ');

  const countResult = await query(
    `SELECT COUNT(*) AS total FROM usage_logs WHERE ${whereClause}`,
    params
  );
  const total = parseInt((countResult.rows[0] as any).total, 10);

  const itemsResult = await query(
    `SELECT id, service, units::text AS units, cost_fen,
            status, created_at::text AS created_at
     FROM usage_logs
     WHERE ${whereClause}
     ORDER BY created_at DESC
     LIMIT $${idx++} OFFSET $${idx++}`,
    [...params, pageSize, offset]
  );

  return {
    total,
    items: itemsResult.rows.map((row: any) => ({
      ...row,
      units: parseFloat(row.units),
    })),
  };
}

// ═══════════════════════════════════════════════
// 向导会话
// ═══════════════════════════════════════════════

export async function createWizardSession(
  userId: string,
  messages: ChatMessage[],
  currentPrompt?: string,
  imageRef?: string
): Promise<string> {
  const result = await query<{ id: string }>(
    `INSERT INTO wizard_sessions (user_id, messages, current_prompt, image_ref)
     VALUES ($1, $2, $3, $4)
     RETURNING id`,
    [userId, JSON.stringify(messages), currentPrompt || null, imageRef || null]
  );
  return result.rows[0].id;
}

export async function updateWizardSession(
  sessionId: string,
  messages: ChatMessage[],
  currentPrompt?: string
): Promise<void> {
  await query(
    `UPDATE wizard_sessions
     SET messages = $2, current_prompt = $3, updated_at = NOW()
     WHERE id = $1`,
    [sessionId, JSON.stringify(messages), currentPrompt || null]
  );
}

export async function getWizardSession(
  sessionId: string
): Promise<WizardSessionRecord | null> {
  const result = await query(
    `SELECT id, user_id, messages, current_prompt, image_ref,
            last_task_id, created_at::text AS created_at,
            updated_at::text AS updated_at,
            expires_at::text AS expires_at
     FROM wizard_sessions WHERE id = $1`,
    [sessionId]
  );
  if (result.rows.length === 0) return null;

  const row = result.rows[0] as any;
  return {
    id: row.id,
    user_id: row.user_id,
    messages: typeof row.messages === 'string'
      ? JSON.parse(row.messages)
      : row.messages,
    current_prompt: row.current_prompt,
    image_ref: row.image_ref,
    last_task_id: row.last_task_id,
    created_at: row.created_at,
    updated_at: row.updated_at,
    expires_at: row.expires_at,
  };
}

export async function updateWizardLastTask(
  sessionId: string,
  taskId: string
): Promise<void> {
  await query(
    `UPDATE wizard_sessions SET last_task_id = $2, updated_at = NOW()
     WHERE id = $1`,
    [sessionId, taskId]
  );
}

// ═══════════════════════════════════════════════
// 视频任务
// ═══════════════════════════════════════════════

export interface CreateVideoTaskParams {
  userId: string;
  usageLogId: string;
  upstreamTaskId: string;
  mode: string;
  prompt: string;
  aspectRatio: string;
  durationSeconds: number;
  quality: string;
  estimatedCostFen: number;
}

export async function createVideoTask(
  params: CreateVideoTaskParams
): Promise<VideoTaskRecord> {
  const result = await query<VideoTaskRecord>(
    `INSERT INTO video_tasks
       (user_id, usage_log_id, upstream_task_id, mode, prompt,
        aspect_ratio, duration_seconds, quality, estimated_cost_fen)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
     RETURNING *`,
    [
      params.userId,
      params.usageLogId,
      params.upstreamTaskId,
      params.mode,
      params.prompt,
      params.aspectRatio,
      params.durationSeconds,
      params.quality,
      params.estimatedCostFen,
    ]
  );
  return result.rows[0];
}

export async function updateVideoTask(
  taskId: string,
  updates: {
    status?: string;
    progress?: number;
    videoUrl?: string | null;
    errorMessage?: string | null;
    actualCostFen?: number;
  }
): Promise<void> {
  const setClauses: string[] = [];
  const values: any[] = [];
  let idx = 1;

  if (updates.status !== undefined) {
    setClauses.push(`status = $${idx++}`);
    values.push(updates.status);
  }
  if (updates.progress !== undefined) {
    setClauses.push(`progress = $${idx++}`);
    values.push(updates.progress);
  }
  if (updates.videoUrl !== undefined) {
    setClauses.push(`video_url = $${idx++}`);
    values.push(updates.videoUrl);
  }
  if (updates.errorMessage !== undefined) {
    setClauses.push(`error_message = $${idx++}`);
    values.push(updates.errorMessage);
  }
  if (updates.actualCostFen !== undefined) {
    setClauses.push(`actual_cost_fen = $${idx++}`);
    values.push(updates.actualCostFen);
  }

  if (updates.status === 'completed' || updates.status === 'failed') {
    setClauses.push(`completed_at = NOW()`);
  }

  if (setClauses.length === 0) return;

  values.push(taskId);
  await query(
    `UPDATE video_tasks SET ${setClauses.join(', ')} WHERE id = $${idx}`,
    values
  );
}

export async function getVideoTask(
  taskId: string
): Promise<VideoTaskRecord | null> {
  const result = await query(
    `SELECT id, user_id, usage_log_id, upstream_task_id, status,
            progress, mode, prompt, aspect_ratio, duration_seconds,
            quality, video_url, error_message, estimated_cost_fen,
            actual_cost_fen, created_at::text AS created_at,
            completed_at::text AS completed_at
     FROM video_tasks WHERE id = $1`,
    [taskId]
  );
  if (result.rows.length === 0) return null;
  return result.rows[0] as VideoTaskRecord;
}

/** 按状态查询视频任务（用于恢复孤儿轮询） */
export async function getVideoTasksByStatus(
  statuses: string[]
): Promise<VideoTaskRecord[]> {
  const placeholders = statuses.map((_, i) => `$${i + 1}`).join(', ');
  const result = await query(
    `SELECT id, user_id, usage_log_id, upstream_task_id, status,
            progress, mode, prompt, aspect_ratio, duration_seconds,
            quality, video_url, error_message, estimated_cost_fen,
            actual_cost_fen, created_at::text AS created_at,
            completed_at::text AS completed_at
     FROM video_tasks WHERE status IN (${placeholders})`,
    statuses
  );
  return result.rows as VideoTaskRecord[];
}

export async function getVideoTasksByUser(
  userId: string,
  page: number = 1,
  pageSize: number = 20
): Promise<{ total: number; items: VideoTaskRecord[] }> {
  const offset = (page - 1) * pageSize;

  const countResult = await query(
    `SELECT COUNT(*) AS total FROM video_tasks WHERE user_id = $1`,
    [userId]
  );
  const total = parseInt((countResult.rows[0] as any).total, 10);

  const itemsResult = await query(
    `SELECT id, upstream_task_id, status, progress, mode, prompt,
            aspect_ratio, duration_seconds, quality, video_url,
            error_message, estimated_cost_fen, actual_cost_fen,
            created_at::text AS created_at,
            completed_at::text AS completed_at
     FROM video_tasks
     WHERE user_id = $1
     ORDER BY created_at DESC
     LIMIT $2 OFFSET $3`,
    [userId, pageSize, offset]
  );

  return { total, items: itemsResult.rows as VideoTaskRecord[] };
}

// ═══════════════════════════════════════════════
// 定价
// ═══════════════════════════════════════════════

let cachedPricing: PricingConfig | null = null;
let pricingCacheTime = 0;

export async function getPricing(): Promise<PricingConfig> {
  const now = Date.now();
  // 缓存 60 秒
  if (cachedPricing && now - pricingCacheTime < 60_000) {
    return cachedPricing;
  }

  const result = await query(
    `SELECT value FROM system_config WHERE key = 'pricing'`
  );
  if (result.rows.length === 0) {
    throw new Error('Pricing configuration not found in system_config');
  }

  const raw = (result.rows[0] as any).value;
  cachedPricing = (typeof raw === 'string' ? JSON.parse(raw) : raw) as PricingConfig;
  pricingCacheTime = now;
  return cachedPricing;
}

export async function getNewUserBonusFen(): Promise<number> {
  const result = await query(
    `SELECT value FROM system_config WHERE key = 'new_user_bonus_fen'`
  );
  if (result.rows.length === 0) return 0;
  return parseInt((result.rows[0] as any).value, 10) || 0;
}

// ═══════════════════════════════════════════════
// 支付订单
// ═══════════════════════════════════════════════

export async function createPaymentOrder(
  userId: string,
  outTradeNo: string,
  packageKey: string,
  amountYuan: number,
  fenAmount: number
): Promise<void> {
  await query(
    `INSERT INTO payment_orders (user_id, out_trade_no, package_key, amount_yuan, fen_amount, status)
     VALUES ($1, $2, $3, $4, $5, 'pending')
     ON CONFLICT (out_trade_no) DO NOTHING`,
    [userId, outTradeNo, packageKey, amountYuan, fenAmount]
  );
}

export async function fulfillPaymentOrder(outTradeNo: string): Promise<boolean> {
  const result = await query(
    `UPDATE payment_orders SET status='paid', paid_at=NOW()
     WHERE out_trade_no=$1 AND status='pending'
     RETURNING user_id, fen_amount`,
    [outTradeNo]
  );
  if (result.rows.length === 0) return false;
  const { user_id, fen_amount } = result.rows[0] as any;
  await query(
    `UPDATE balances SET amount_fen = amount_fen + $1, updated_at=NOW()
     WHERE user_id = $2`,
    [fen_amount, user_id]
  );
  return true;
}
