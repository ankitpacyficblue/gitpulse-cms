-- Forgets the library and which messages carried files. The files stay in the storage bucket.
ALTER TABLE wa_templates DROP COLUMN IF EXISTS header_format;
ALTER TABLE broadcasts DROP COLUMN IF EXISTS media_id;
ALTER TABLE messages DROP COLUMN IF EXISTS media_id;
DROP TABLE IF EXISTS media_files;
