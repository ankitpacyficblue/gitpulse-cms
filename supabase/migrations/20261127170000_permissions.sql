-- Section permissions. Additive: existing columns and rows are not changed.
ALTER TABLE memberships ADD COLUMN IF NOT EXISTS role_key TEXT;
ALTER TABLE memberships ADD COLUMN IF NOT EXISTS role_key_base TEXT;
CREATE TABLE IF NOT EXISTS role_permissions (
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    role_key TEXT NOT NULL, section TEXT NOT NULL, level TEXT NOT NULL,
    PRIMARY KEY (account_id, role_key, section));
CREATE TABLE IF NOT EXISTS permission_overrides (
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    user_id INTEGER NOT NULL, section TEXT NOT NULL, level TEXT NOT NULL,
    PRIMARY KEY (account_id, user_id, section));
CREATE TABLE IF NOT EXISTS automation_runs (
    id SERIAL PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    automation_id INTEGER NOT NULL, ok INTEGER NOT NULL DEFAULT 1, error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_autoruns_acct ON automation_runs (account_id, created_at);
ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE permission_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_runs ENABLE ROW LEVEL SECURITY;
