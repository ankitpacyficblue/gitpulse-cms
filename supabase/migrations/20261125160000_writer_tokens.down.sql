-- Removes writer tokens; posts and images they made stay.
DROP INDEX IF EXISTS idx_blog_plan_external;
ALTER TABLE blog_plan DROP COLUMN IF EXISTS external_id;
ALTER TABLE blog_plan DROP COLUMN IF EXISTS published_at;
ALTER TABLE blog_plan DROP COLUMN IF EXISTS writer_token_id;
ALTER TABLE media_files DROP COLUMN IF EXISTS writer_token_id;
DROP TABLE IF EXISTS writer_tokens;
