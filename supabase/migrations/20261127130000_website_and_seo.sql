-- Website address per account and an optional search title per planned post (additive).
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS website_url TEXT NOT NULL DEFAULT '';
ALTER TABLE blog_plan ADD COLUMN IF NOT EXISTS seo_title TEXT NOT NULL DEFAULT '';
