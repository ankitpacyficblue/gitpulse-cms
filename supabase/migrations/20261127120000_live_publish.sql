-- GitPulse as the live source of posts (additive). Git publishing is off unless switched on.
ALTER TABLE account_settings ADD COLUMN IF NOT EXISTS publish_via_git INTEGER NOT NULL DEFAULT 0;
ALTER TABLE account_settings ADD COLUMN IF NOT EXISTS site_url TEXT NOT NULL DEFAULT '';
ALTER TABLE account_settings ADD COLUMN IF NOT EXISTS revalidate_secret_enc TEXT NOT NULL DEFAULT '';
