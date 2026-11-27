-- Each website has its own address; empty means the account's address.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS website_url TEXT NOT NULL DEFAULT '';
