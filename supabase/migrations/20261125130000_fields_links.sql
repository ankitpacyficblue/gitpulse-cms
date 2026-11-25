-- Phase 1b custom contact fields and entry link source/campaign (additive).
CREATE TABLE IF NOT EXISTS contact_fields (
        id SERIAL PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
        name TEXT NOT NULL, type TEXT NOT NULL, options TEXT NOT NULL DEFAULT '[]', archived INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
ALTER TABLE entry_links ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'website';
ALTER TABLE entry_links ADD COLUMN IF NOT EXISTS campaign TEXT NOT NULL DEFAULT '';
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS campaign TEXT NOT NULL DEFAULT '';
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS entry_code TEXT NOT NULL DEFAULT '';
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS custom TEXT NOT NULL DEFAULT '{}';
ALTER TABLE contact_fields ENABLE ROW LEVEL SECURITY;
