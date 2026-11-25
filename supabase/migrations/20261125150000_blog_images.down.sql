-- Forgets attached images and rejection notes.
ALTER TABLE blog_plan DROP COLUMN IF EXISTS images;
ALTER TABLE blog_plan DROP COLUMN IF EXISTS rejected_note;
ALTER TABLE blog_plan DROP COLUMN IF EXISTS rejected_by;
ALTER TABLE blog_plan DROP COLUMN IF EXISTS rejected_at;
ALTER TABLE blog_plan DROP COLUMN IF EXISTS publish_origin;
