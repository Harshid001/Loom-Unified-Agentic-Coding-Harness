-- Migration 005: PostgreSQL API Token Registry table and indexes
CREATE TABLE IF NOT EXISTS api_tokens (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    org_id VARCHAR(128) NOT NULL DEFAULT 'default',
    label VARCHAR(255) DEFAULT '',
    token_hash VARCHAR(64) NOT NULL,
    prefix VARCHAR(32) DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    revoked_at DOUBLE PRECISION,
    created_at DOUBLE PRECISION NOT NULL,
    expires_at DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_token_hash ON api_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_api_tokens_org_user ON api_tokens(org_id, user_id);
CREATE INDEX IF NOT EXISTS idx_api_tokens_active ON api_tokens(active);
