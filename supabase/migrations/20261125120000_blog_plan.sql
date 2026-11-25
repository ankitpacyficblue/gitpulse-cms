-- Phase 1b blog plan (additive).
CREATE TABLE IF NOT EXISTS blog_plan (
        id SERIAL PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
        project_id INTEGER, title TEXT NOT NULL, topic TEXT NOT NULL DEFAULT '', keyword TEXT NOT NULL DEFAULT '',
        publish_at TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft', body TEXT NOT NULL DEFAULT '',
        assignee_id INTEGER, post_url TEXT NOT NULL DEFAULT '', post_id INTEGER, error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
CREATE INDEX IF NOT EXISTS idx_blog_plan_acct ON blog_plan (account_id, publish_at);
ALTER TABLE blog_plan ENABLE ROW LEVEL SECURITY;
