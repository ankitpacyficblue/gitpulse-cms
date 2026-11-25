-- Phase 1b media library (additive).
CREATE TABLE IF NOT EXISTS media_files (
    id SERIAL PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL DEFAULT 0, path TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'pending', source TEXT NOT NULL DEFAULT 'library',
    is_public INTEGER NOT NULL DEFAULT 0, created_by INTEGER, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_media_acct ON media_files (account_id, status);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_id INTEGER;
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS media_id INTEGER;
ALTER TABLE wa_templates ADD COLUMN IF NOT EXISTS header_format TEXT NOT NULL DEFAULT '';
ALTER TABLE media_files ENABLE ROW LEVEL SECURITY;
