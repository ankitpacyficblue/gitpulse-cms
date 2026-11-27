-- One set of posts: mark where a row came from, and allow one blog_plan row per posts row.
ALTER TABLE blog_plan ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_blog_plan_post ON blog_plan (post_id) WHERE post_id IS NOT NULL;
