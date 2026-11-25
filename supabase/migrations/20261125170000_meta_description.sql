-- Optional meta description on planned posts (additive).
ALTER TABLE blog_plan ADD COLUMN IF NOT EXISTS meta_description TEXT NOT NULL DEFAULT '';
