-- Phase 1b blog images and reject-with-note (additive).
ALTER TABLE blog_plan ADD COLUMN IF NOT EXISTS images TEXT NOT NULL DEFAULT '[]';
ALTER TABLE blog_plan ADD COLUMN IF NOT EXISTS rejected_note TEXT NOT NULL DEFAULT '';
ALTER TABLE blog_plan ADD COLUMN IF NOT EXISTS rejected_by INTEGER;
ALTER TABLE blog_plan ADD COLUMN IF NOT EXISTS rejected_at TEXT NOT NULL DEFAULT '';
ALTER TABLE blog_plan ADD COLUMN IF NOT EXISTS publish_origin TEXT NOT NULL DEFAULT '';
