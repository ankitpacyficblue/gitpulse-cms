-- Deletes custom fields, their values and link source/campaign.
ALTER TABLE entry_links DROP COLUMN IF EXISTS source;
ALTER TABLE entry_links DROP COLUMN IF EXISTS campaign;
ALTER TABLE contacts DROP COLUMN IF EXISTS campaign;
ALTER TABLE contacts DROP COLUMN IF EXISTS entry_code;
ALTER TABLE contacts DROP COLUMN IF EXISTS custom;
DROP TABLE IF EXISTS contact_fields;
