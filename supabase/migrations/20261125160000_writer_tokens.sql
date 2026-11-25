-- Phase 1b AI writer tokens and published time (additive).
CREATE TABLE IF NOT EXISTS writer_tokens (
    id SERIAL PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, hint TEXT NOT NULL DEFAULT '', created_by INTEGER,
    created_at TEXT NOT NULL, last_used_at TEXT NOT NULL DEFAULT '', revoked_at TEXT NOT NULL DEFAULT ''
);
ALTER TABLE media_files ADD COLUMN IF NOT EXISTS writer_token_id INTEGER;
ALTER TABLE blog_plan ADD COLUMN IF NOT EXISTS writer_token_id INTEGER;
ALTER TABLE blog_plan ADD COLUMN IF NOT EXISTS published_at TEXT NOT NULL DEFAULT '';
ALTER TABLE writer_tokens ENABLE ROW LEVEL SECURITY;
