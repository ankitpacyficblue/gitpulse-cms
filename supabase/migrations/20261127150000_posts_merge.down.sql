DELETE FROM blog_plan WHERE origin = 'legacy';
DROP INDEX IF EXISTS idx_blog_plan_post;
ALTER TABLE blog_plan DROP COLUMN IF EXISTS origin;
