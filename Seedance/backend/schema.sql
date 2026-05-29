-- Seedance Studio Schema
-- 首次部署时在 lifespan 中自动执行（IF NOT EXISTS 保证幂等）

CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    email           TEXT UNIQUE,
    phone           TEXT,
    google_id       TEXT UNIQUE,
    github_id       TEXT UNIQUE,
    password_hash   TEXT NOT NULL DEFAULT '',
    auth_provider   TEXT NOT NULL DEFAULT 'email',
    avatar_url      TEXT DEFAULT '',
    balance_subunit INTEGER NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'USD',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    tx_id           TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(user_id),
    tx_type         TEXT NOT NULL,
    amount_subunit  INTEGER NOT NULL,
    balance_after   INTEGER NOT NULL,
    currency        TEXT NOT NULL,
    note            TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    data            JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_id          TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(user_id),
    key_hash        TEXT UNIQUE NOT NULL,
    key_prefix      TEXT NOT NULL,
    name            TEXT DEFAULT '',
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_apikey_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_apikey_hash ON api_keys(key_hash);

-- Add github_id column and unique index (idempotent)
ALTER TABLE users ADD COLUMN IF NOT EXISTS github_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS users_github_id_key ON users (github_id);

CREATE TABLE IF NOT EXISTS shares (
    share_id        TEXT PRIMARY KEY,
    video_url       TEXT NOT NULL,
    prompt_en       TEXT DEFAULT '',
    resolution      TEXT DEFAULT '1080p',
    duration        INTEGER DEFAULT 12,
    thumbnail_url   TEXT DEFAULT '',
    user_id         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
