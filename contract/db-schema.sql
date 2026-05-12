-- ============================================================
-- Seedance Wizard 数据库 Schema（国内版 + 海外版）
-- 数据库：PostgreSQL 14+
-- 字符集：UTF-8
-- 货币单位：国内版 分(fen) / 海外版 USD cents(subunit)
-- 区域：DEPLOYMENT_REGION=cn|intl 控制行为分支
-- ============================================================

-- 启用 UUID 扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─────────────────────────────────────────
-- 用户表
-- ─────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone           VARCHAR(20)  UNIQUE,                        -- 手机号（国内版必填，海外版可选）
    email           VARCHAR(255) UNIQUE,                        -- 邮箱（海外版必填，国内版可选）
    google_id        VARCHAR(255) UNIQUE,                       -- Google OAuth sub（海外版）
    avatar_url      TEXT,                                       -- 头像 URL（Google 登录获取）
    password_hash   VARCHAR(255) NOT NULL,                      -- bcrypt hash（Google 登录可为空）
    display_name    VARCHAR(100),
    auth_provider   VARCHAR(20) NOT NULL DEFAULT 'phone',       -- phone | email | google
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT users_auth_check CHECK (
        (auth_provider = 'phone' AND phone IS NOT NULL) OR
        (auth_provider = 'email' AND email IS NOT NULL) OR
        (auth_provider = 'google' AND google_id IS NOT NULL)
    )
);

CREATE INDEX idx_users_phone ON users(phone) WHERE phone IS NOT NULL;
CREATE INDEX idx_users_email ON users(email) WHERE email IS NOT NULL;
CREATE INDEX idx_users_google_id ON users(google_id) WHERE google_id IS NOT NULL;

COMMENT ON TABLE users IS '用户账号表（国内版手机号 + 海外版邮箱/Google OAuth）';
COMMENT ON COLUMN users.password_hash IS 'bcrypt，cost=12。Google 登录用户可为空';
COMMENT ON COLUMN users.auth_provider IS '认证方式: phone(国内默认) | email(海外邮箱) | google(海外Google)';

-- ─────────────────────────────────────────
-- API Key 表
-- ─────────────────────────────────────────
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL DEFAULT 'My Key',  -- 用户自定义名称
    key_prefix      VARCHAR(16) NOT NULL,                    -- 明文前缀，如 "sk-seed-ab12"，供展示识别
    key_hash        VARCHAR(255) NOT NULL UNIQUE,            -- SHA-256 of full key，用于验证
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ                              -- NULL = 永不过期
);

CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_active ON api_keys(is_active) WHERE is_active = TRUE;

COMMENT ON TABLE api_keys IS 'API Key 管理表。完整 Key 只在创建时返回一次，之后只存 hash。';
COMMENT ON COLUMN api_keys.key_prefix IS '明文前缀，格式: sk-seed-{8位随机字符}，安全展示用';
COMMENT ON COLUMN api_keys.key_hash IS 'SHA-256(full_key)，用于每次请求的快速验证';

-- ─────────────────────────────────────────
-- 余额表（每用户一行）
-- ─────────────────────────────────────────
CREATE TABLE balances (
    user_id         UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    amount_fen      BIGINT NOT NULL DEFAULT 0,               -- 单位：分。新用户默认 0
    currency        VARCHAR(3) NOT NULL DEFAULT 'CNY',       -- CNY(国内) | USD(海外)
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE balances IS '用户余额表。国内版 CNY/分，海外版 USD/cents。';
COMMENT ON COLUMN balances.amount_fen IS '余额（最小子单位：国内分，海外 cents）。最小值 0';
COMMENT ON COLUMN balances.currency IS '货币代码：CNY(人民币) | USD(美元)';

-- 新用户注册时自动创建余额记录（Trigger）
CREATE OR REPLACE FUNCTION create_user_balance()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO balances (user_id, amount_fen) VALUES (NEW.id, 0);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_create_balance_on_register
    AFTER INSERT ON users
    FOR EACH ROW EXECUTE FUNCTION create_user_balance();

-- ─────────────────────────────────────────
-- 用量日志表（所有 API 调用记录）
-- ─────────────────────────────────────────
CREATE TYPE service_type AS ENUM (
    'deepseek',       -- DeepSeek 导演对话（按 token 计费）
    'qwen_vl',        -- Qwen VL 图像分析（按 token 计费）
    'flux_preview',   -- Flux 预览图生成（按张计费）
    'seedance_t2v',   -- Seedance 文生视频（按秒计费）
    'seedance_i2v'    -- Seedance 图生视频（按秒计费）
);

CREATE TYPE log_status AS ENUM (
    'pending',    -- 已提交，等待结果（异步任务用）
    'success',    -- 成功完成并扣费
    'failed',     -- 失败，不扣费（或已退款）
    'refunded'    -- 已退款（预扣后失败）
);

CREATE TABLE usage_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id),
    api_key_id      UUID REFERENCES api_keys(id),            -- 使用的 Key（删 Key 后置 NULL）
    service         service_type NOT NULL,
    -- 计量单位（根据 service 类型含义不同）
    -- deepseek/qwen_vl: input_tokens + output_tokens
    -- flux_preview: 生成张数（通常=1）
    -- seedance_*: 视频时长（秒）
    units           NUMERIC(10, 4) NOT NULL,
    -- 费用（最小子单位：国内分 / 海外 cents）
    cost_fen        BIGINT NOT NULL DEFAULT 0,               -- 实际扣费（失败时=0）
    pre_cost_fen    BIGINT NOT NULL DEFAULT 0,               -- 预扣费用（用于异步任务）
    currency        VARCHAR(3) NOT NULL DEFAULT 'CNY',       -- CNY | USD
    status          log_status NOT NULL DEFAULT 'pending',
    -- 关联的上游任务 ID（Seedance task_id / muapi task_id 等）
    upstream_task_id VARCHAR(255),
    -- 请求元数据（调试用）
    request_meta    JSONB,                                   -- 如 {model, duration, quality, aspect_ratio}
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_usage_logs_user_id ON usage_logs(user_id);
CREATE INDEX idx_usage_logs_api_key_id ON usage_logs(api_key_id);
CREATE INDEX idx_usage_logs_created_at ON usage_logs(created_at DESC);
CREATE INDEX idx_usage_logs_service ON usage_logs(service);
CREATE INDEX idx_usage_logs_status ON usage_logs(status) WHERE status = 'pending';
CREATE INDEX idx_usage_logs_upstream_task ON usage_logs(upstream_task_id) WHERE upstream_task_id IS NOT NULL;

COMMENT ON TABLE usage_logs IS '所有 API 调用的用量记录，支持计费审计和用户用量查询。';
COMMENT ON COLUMN usage_logs.units IS 'deepseek/qwen_vl=tokens; flux_preview=张数; seedance=秒数';
COMMENT ON COLUMN usage_logs.pre_cost_fen IS '异步任务（Seedance 出片）先预扣，完成后结算实际费用';
COMMENT ON COLUMN usage_logs.request_meta IS 'JSON 元数据，如 {"model":"seedance-2.0","duration":5,"quality":"high"}';

-- ─────────────────────────────────────────
-- 向导会话表（DeepSeek 对话历史）
-- ─────────────────────────────────────────
CREATE TABLE wizard_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id),
    -- 对话历史（OpenAI messages 格式的 JSON 数组）
    messages        JSONB NOT NULL DEFAULT '[]',
    -- DeepSeek 当前生成的最终 Prompt
    current_prompt  TEXT,
    -- Qwen VL 分析后存储的图片引用（base64 或 URL）
    image_ref       TEXT,
    -- 最后一次生成的视频任务 ID
    last_task_id    VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- 会话 7 天不活跃后可清理
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days')
);

CREATE INDEX idx_wizard_sessions_user_id ON wizard_sessions(user_id);
CREATE INDEX idx_wizard_sessions_expires ON wizard_sessions(expires_at);

COMMENT ON TABLE wizard_sessions IS 'DeepSeek 导演对话会话，存储多轮消息历史和当前 Prompt。';
COMMENT ON COLUMN wizard_sessions.messages IS 'OpenAI messages 格式: [{role:"user"|"assistant"|"tool", content:"..."}]';

-- ─────────────────────────────────────────
-- 视频任务表（Seedance 异步任务状态）
-- ─────────────────────────────────────────
CREATE TYPE task_status AS ENUM (
    'queued',
    'processing',
    'completed',
    'failed'
);

CREATE TABLE video_tasks (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id),
    usage_log_id        UUID REFERENCES usage_logs(id),
    -- muapi.ai 返回的上游 task id
    upstream_task_id    VARCHAR(255) NOT NULL,
    status              task_status NOT NULL DEFAULT 'queued',
    progress            SMALLINT NOT NULL DEFAULT 0,          -- 0-100
    -- 出片参数
    mode                VARCHAR(20) NOT NULL,                  -- text_to_video | image_to_video
    prompt              TEXT NOT NULL,
    aspect_ratio        VARCHAR(10) NOT NULL DEFAULT '16:9',
    duration_seconds    SMALLINT NOT NULL DEFAULT 5,
    quality             VARCHAR(10) NOT NULL DEFAULT 'high',
    -- 结果
    video_url           TEXT,                                  -- 最终视频 CDN URL
    error_message       TEXT,
    estimated_cost_fen  BIGINT NOT NULL DEFAULT 0,
    actual_cost_fen     BIGINT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX idx_video_tasks_user_id ON video_tasks(user_id);
CREATE INDEX idx_video_tasks_upstream ON video_tasks(upstream_task_id);
CREATE INDEX idx_video_tasks_status ON video_tasks(status) WHERE status IN ('queued', 'processing');

COMMENT ON TABLE video_tasks IS 'Seedance 视频生成异步任务状态表，供轮询接口使用。';

-- ─────────────────────────────────────────
-- 系统配置表（后台运营用）
-- ─────────────────────────────────────────
CREATE TABLE system_config (
    key             VARCHAR(100) PRIMARY KEY,
    value           JSONB NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 初始定价配置
INSERT INTO system_config (key, value, description) VALUES
(
    'pricing',
    '{
        "deepseek_input_per_1m_fen": 364,
        "deepseek_output_per_1m_fen": 1456,
        "qwen_vl_per_1m_fen": 583,
        "flux_preview_per_image_fen": 1,
        "seedance_t2v_basic_per_sec_fen": 31,
        "seedance_t2v_high_per_sec_fen": 63,
        "seedance_i2v_basic_per_sec_fen": 31,
        "seedance_i2v_high_per_sec_fen": 63
    }',
    '各服务计费单价（单位：分）。基于 muapi.ai 渠道价 + 我们的毛利。可随时调整。'
),
(
    'new_user_bonus_fen',
    '0',
    '新用户注册赠送余额（分），0=不赠送。上线初期可改为100（赠1元）做冷启动'
);

COMMENT ON TABLE system_config IS '系统级配置，支持不停服热更新定价等参数。';

-- ─────────────────────────────────────────
-- 常用视图
-- ─────────────────────────────────────────

-- 用户余额 + 用量汇总视图（供后台管理和 API 使用）
CREATE VIEW user_summary AS
SELECT
    u.id,
    u.phone,
    u.display_name,
    u.created_at,
    b.amount_fen AS balance_fen,
    ROUND(b.amount_fen::numeric / 100, 2) AS balance_yuan,
    COUNT(DISTINCT ak.id) AS active_key_count,
    COUNT(DISTINCT ul.id) AS total_requests,
    COALESCE(SUM(ul.cost_fen), 0) AS total_spent_fen
FROM users u
LEFT JOIN balances b ON b.user_id = u.id
LEFT JOIN api_keys ak ON ak.user_id = u.id AND ak.is_active = TRUE
LEFT JOIN usage_logs ul ON ul.user_id = u.id AND ul.status = 'success'
GROUP BY u.id, u.phone, u.display_name, u.created_at, b.amount_fen;

COMMENT ON VIEW user_summary IS '用户余额和用量汇总，供后台管理和余额 API 使用。';

-- ─────────────────────────────────────────
-- 函数：验证 API Key 并返回用户信息
-- （Node.js 后端中间件调用，避免多次查询）
-- ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION verify_api_key(p_key_hash VARCHAR)
RETURNS TABLE (
    user_id     UUID,
    api_key_id  UUID,
    balance_fen BIGINT,
    is_valid    BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.id AS user_id,
        ak.id AS api_key_id,
        b.amount_fen AS balance_fen,
        (u.is_active AND ak.is_active AND (ak.expires_at IS NULL OR ak.expires_at > NOW())) AS is_valid
    FROM api_keys ak
    JOIN users u ON u.id = ak.user_id
    JOIN balances b ON b.user_id = u.id
    WHERE ak.key_hash = p_key_hash;

    -- 更新最后使用时间
    UPDATE api_keys SET last_used_at = NOW()
    WHERE key_hash = p_key_hash;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION verify_api_key IS
'验证 API Key 并返回用户ID、余额等信息。Node.js 中间件每次请求调用一次。';

-- ─────────────────────────────────────────
-- 函数：扣费（带余额检查，原子操作）
-- ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION deduct_balance(
    p_user_id   UUID,
    p_amount_fen BIGINT
) RETURNS BOOLEAN AS $$
DECLARE
    v_current BIGINT;
BEGIN
    SELECT amount_fen INTO v_current FROM balances WHERE user_id = p_user_id FOR UPDATE;

    IF v_current < p_amount_fen THEN
        RETURN FALSE;  -- 余额不足
    END IF;

    UPDATE balances
    SET amount_fen = amount_fen - p_amount_fen,
        updated_at = NOW()
    WHERE user_id = p_user_id;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION deduct_balance IS
'原子扣费操作，带余额不足检查。返回 TRUE=扣成功，FALSE=余额不足。';

-- ─────────────────────────────────────────
-- 函数：退款（任务失败时调用）
-- ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION refund_balance(
    p_user_id    UUID,
    p_amount_fen BIGINT,
    p_log_id     UUID
) RETURNS VOID AS $$
BEGIN
    UPDATE balances
    SET amount_fen = amount_fen + p_amount_fen,
        updated_at = NOW()
    WHERE user_id = p_user_id;

    UPDATE usage_logs
    SET status = 'refunded',
        cost_fen = 0
    WHERE id = p_log_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refund_balance IS
'任务失败时退还预扣费用，并将 usage_log 状态更新为 refunded。';

-- ═══════════════════════════════════════════════
-- Migration v2: 海外版字段增量（幂等，可重复执行）
-- ═══════════════════════════════════════════════

-- 用户表扩展
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) DEFAULT 'phone';
ALTER TABLE users ALTER COLUMN phone DROP NOT NULL;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_auth_check;
ALTER TABLE users ADD CONSTRAINT users_auth_check CHECK (
    (auth_provider = 'phone' AND phone IS NOT NULL) OR
    (auth_provider = 'email' AND email IS NOT NULL) OR
    (auth_provider = 'google' AND google_id IS NOT NULL)
);

-- 余额表扩展
ALTER TABLE balances ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'CNY';

-- 用量日志表扩展
ALTER TABLE usage_logs ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'CNY';

-- 海外版定价（USD cents，仅当 pricing 键不存在时插入）
INSERT INTO system_config (key, value, description)
VALUES (
    'pricing_intl',
    '{
        "deepseek_input_per_1m_subunit": 200,
        "deepseek_output_per_1m_subunit": 600,
        "qwen_vl_per_1m_subunit": 400,
        "flux_preview_per_image_subunit": 15,
        "seedance_t2v_basic_per_sec_subunit": 5,
        "seedance_t2v_high_per_sec_subunit": 8,
        "seedance_i2v_basic_per_sec_subunit": 7,
        "seedance_i2v_high_per_sec_subunit": 10
    }',
    '海外版各服务计费单价（单位：USD cents）。基于 muapi.ai 渠道价 + 毛利。'
)
ON CONFLICT (key) DO NOTHING;

-- 更新索引（对已存在的数据库）
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id) WHERE google_id IS NOT NULL;

-- 迁移现有数据
UPDATE balances SET currency = 'CNY' WHERE currency IS NULL;
UPDATE usage_logs SET currency = 'CNY' WHERE currency IS NULL;

-- ─────────────────────────────────────────
-- Migration v3: 支付订单表
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payment_orders (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID        NOT NULL REFERENCES users(id),
    out_trade_no  VARCHAR(64) UNIQUE NOT NULL,
    package_key   VARCHAR(32) NOT NULL,
    amount_yuan   NUMERIC(10,2) NOT NULL,
    fen_amount    INTEGER     NOT NULL,
    status        VARCHAR(16) NOT NULL DEFAULT 'pending',
    paid_at       TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_payment_orders_user ON payment_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_payment_orders_out_trade_no ON payment_orders(out_trade_no);
