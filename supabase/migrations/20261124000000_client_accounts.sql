-- ============================================================================
-- GitPulse CMS: client accounts (multi-tenant), memberships, per-account WhatsApp
-- Migration 20261124000000. ADDITIVE and reviewable. NOT APPLIED by the agent.
-- Apply only after human review, first to a Supabase branch / staging project.
--
-- What it does
--   1. accounts + memberships (users belong to many accounts, one role each)
--   2. account_id NOT NULL on every tenant table, ON DELETE RESTRICT (a deleted
--      account never turns rows global; app soft-deletes via accounts.status)
--   3. composite FKs so a message/conversation/deal cannot point at another
--      account's contact
--   4. whatsapp_accounts (credentials are written ENCRYPTED by the app; this
--      migration never copies plaintext tokens)
--   5. RLS on tenant tables as defence in depth (the server uses the service role)
--   6. closes a leak: anon could read projects.github_token / webhook_secret
--
-- What it does NOT do: delete any row, drop any column, or create memberships for
-- existing users. Old client_id columns and legacy tables stay until a later
-- "contract" migration. Existing users get NO access until an operator adds
-- memberships (see section 9) after reviewing who they are.
-- ============================================================================

BEGIN;

-- 1. Accounts ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.accounts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    contact_email TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Existing blog tenants keep their ids as account ids.
INSERT INTO public.accounts (id, name, contact_email, created_at)
SELECT id, name, COALESCE(contact_email, ''), COALESCE(created_at, now()) FROM public.clients
ON CONFLICT (id) DO NOTHING;

-- Holding account for rows that had no client. Nobody has access until assigned.
INSERT INTO public.accounts (id, name, status)
VALUES ('00000000-0000-0000-0000-000000000001', 'Legacy (unassigned rows)', 'suspended')
ON CONFLICT (id) DO NOTHING;

-- 2. Users and memberships --------------------------------------------------
ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS email             TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS is_active         BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS is_platform_admin BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS public.memberships (
    account_id UUID   NOT NULL REFERENCES public.accounts(id) ON DELETE RESTRICT,
    user_id    BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    role       TEXT   NOT NULL CHECK (role IN ('owner', 'admin', 'agent', 'viewer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_memberships_user ON public.memberships (user_id);

-- 3. account_id on tenant tables: add nullable, backfill, then enforce ----------
ALTER TABLE public.projects      ADD COLUMN IF NOT EXISTS account_id UUID;
ALTER TABLE public.system_logs   ADD COLUMN IF NOT EXISTS account_id UUID;
ALTER TABLE public.contacts      ADD COLUMN IF NOT EXISTS account_id UUID;
ALTER TABLE public.conversations ADD COLUMN IF NOT EXISTS account_id UUID;
ALTER TABLE public.messages      ADD COLUMN IF NOT EXISTS account_id UUID;
ALTER TABLE public.deals         ADD COLUMN IF NOT EXISTS account_id UUID;
ALTER TABLE public.broadcasts    ADD COLUMN IF NOT EXISTS account_id UUID;
ALTER TABLE public.automations   ADD COLUMN IF NOT EXISTS account_id UUID;

UPDATE public.projects      SET account_id = COALESCE(client_id, '00000000-0000-0000-0000-000000000001') WHERE account_id IS NULL;
UPDATE public.contacts      SET account_id = COALESCE(client_id, '00000000-0000-0000-0000-000000000001') WHERE account_id IS NULL;
UPDATE public.deals         SET account_id = COALESCE(client_id, '00000000-0000-0000-0000-000000000001') WHERE account_id IS NULL;
UPDATE public.broadcasts    SET account_id = COALESCE(client_id, '00000000-0000-0000-0000-000000000001') WHERE account_id IS NULL;
UPDATE public.automations   SET account_id = COALESCE(client_id, '00000000-0000-0000-0000-000000000001') WHERE account_id IS NULL;
-- Children inherit from their parent, never from client_id, so they cannot disagree with it.
UPDATE public.conversations cv SET account_id = c.account_id FROM public.contacts c
    WHERE cv.contact_id = c.id AND cv.account_id IS NULL;
UPDATE public.messages m SET account_id = cv.account_id FROM public.conversations cv
    WHERE m.conversation_id = cv.id AND m.account_id IS NULL;
UPDATE public.system_logs l SET account_id = p.account_id FROM public.projects p
    WHERE l.project_id = p.id AND l.account_id IS NULL;
UPDATE public.system_logs SET account_id = '00000000-0000-0000-0000-000000000001' WHERE account_id IS NULL;

ALTER TABLE public.projects      ALTER COLUMN account_id SET NOT NULL;
ALTER TABLE public.system_logs   ALTER COLUMN account_id SET NOT NULL;
ALTER TABLE public.contacts      ALTER COLUMN account_id SET NOT NULL;
ALTER TABLE public.conversations ALTER COLUMN account_id SET NOT NULL;
ALTER TABLE public.messages      ALTER COLUMN account_id SET NOT NULL;
ALTER TABLE public.deals         ALTER COLUMN account_id SET NOT NULL;
ALTER TABLE public.broadcasts    ALTER COLUMN account_id SET NOT NULL;
ALTER TABLE public.automations   ALTER COLUMN account_id SET NOT NULL;

ALTER TABLE public.projects      ADD CONSTRAINT projects_account_fk      FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE RESTRICT;
ALTER TABLE public.system_logs   ADD CONSTRAINT system_logs_account_fk   FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE RESTRICT;
ALTER TABLE public.contacts      ADD CONSTRAINT contacts_account_fk      FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE RESTRICT;
ALTER TABLE public.conversations ADD CONSTRAINT conversations_account_fk FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE RESTRICT;
ALTER TABLE public.messages      ADD CONSTRAINT messages_account_fk      FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE RESTRICT;
ALTER TABLE public.deals         ADD CONSTRAINT deals_account_fk         FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE RESTRICT;
ALTER TABLE public.broadcasts    ADD CONSTRAINT broadcasts_account_fk    FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE RESTRICT;
ALTER TABLE public.automations   ADD CONSTRAINT automations_account_fk   FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE RESTRICT;

-- 4. Same-account guarantees (composite foreign keys) ---------------------------
ALTER TABLE public.contacts      ADD CONSTRAINT contacts_id_account_uq      UNIQUE (id, account_id);
ALTER TABLE public.conversations ADD CONSTRAINT conversations_id_account_uq UNIQUE (id, account_id);
ALTER TABLE public.conversations ADD CONSTRAINT conversations_contact_same_account
    FOREIGN KEY (contact_id, account_id) REFERENCES public.contacts (id, account_id) ON DELETE CASCADE;
ALTER TABLE public.messages ADD CONSTRAINT messages_conversation_same_account
    FOREIGN KEY (conversation_id, account_id) REFERENCES public.conversations (id, account_id) ON DELETE CASCADE;
ALTER TABLE public.messages ADD CONSTRAINT messages_contact_same_account
    FOREIGN KEY (contact_id, account_id) REFERENCES public.contacts (id, account_id) ON DELETE CASCADE;
ALTER TABLE public.deals ADD CONSTRAINT deals_contact_same_account
    FOREIGN KEY (contact_id, account_id) REFERENCES public.contacts (id, account_id) ON DELETE SET NULL (contact_id);

-- Phone numbers are unique per account (not globally). Fails, and rolls the whole
-- migration back, if an account already holds duplicates: dedupe first.
ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS phone_norm TEXT;
UPDATE public.contacts SET phone_norm = regexp_replace(phone, '\D', '', 'g') WHERE phone_norm IS NULL;
ALTER TABLE public.contacts ALTER COLUMN phone_norm SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS contacts_account_phone_uq ON public.contacts (account_id, phone_norm);
CREATE UNIQUE INDEX IF NOT EXISTS conversations_account_contact_uq ON public.conversations (account_id, contact_id);

CREATE INDEX IF NOT EXISTS idx_projects_account      ON public.projects (account_id);
CREATE INDEX IF NOT EXISTS idx_logs_account          ON public.system_logs (account_id, id);
CREATE INDEX IF NOT EXISTS idx_contacts_account      ON public.contacts (account_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_conversations_account ON public.conversations (account_id, last_message_at);
CREATE INDEX IF NOT EXISTS idx_messages_account_conv ON public.messages (account_id, conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_account_wa   ON public.messages (account_id, wa_message_id);
CREATE INDEX IF NOT EXISTS idx_deals_account         ON public.deals (account_id, stage);
CREATE INDEX IF NOT EXISTS idx_broadcasts_account    ON public.broadcasts (account_id);
CREATE INDEX IF NOT EXISTS idx_automations_account   ON public.automations (account_id);

-- 5. Per-account WhatsApp credentials ---------------------------------------
-- access_token_enc / app_secret_enc hold AES-256-GCM ciphertext written by the app
-- (key: CREDENTIAL_ENC_KEY, never stored in the database). verify_token_hash is a
-- SHA-256 hash. Plaintext tokens from whatsapp_configs are NOT copied.
CREATE TABLE IF NOT EXISTS public.whatsapp_accounts (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id        UUID NOT NULL UNIQUE REFERENCES public.accounts(id) ON DELETE RESTRICT,
    phone_number_id   TEXT NOT NULL DEFAULT '',
    waba_id           TEXT NOT NULL DEFAULT '',
    business_name     TEXT NOT NULL DEFAULT '',
    phone_number      TEXT NOT NULL DEFAULT '',
    access_token_enc  TEXT NOT NULL DEFAULT '',
    app_secret_enc    TEXT NOT NULL DEFAULT '',
    verify_token_hash TEXT NOT NULL DEFAULT '',
    needs_rekey       BOOLEAN NOT NULL DEFAULT false,
    is_active         BOOLEAN NOT NULL DEFAULT true,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS whatsapp_accounts_phone_number_id_uq
    ON public.whatsapp_accounts (phone_number_id) WHERE phone_number_id <> '';

-- Carry over real (non-demo) connection details so owners only re-enter secrets.
INSERT INTO public.whatsapp_accounts (account_id, phone_number_id, waba_id, business_name, phone_number, needs_rekey, is_active)
SELECT w.client_id, w.phone_number_id, w.waba_id, w.business_name, w.phone_number, true, false
FROM public.whatsapp_configs w
WHERE w.client_id IS NOT NULL
  AND w.access_token NOT LIKE 'mock%'
  AND w.phone_number_id <> '109876543210123'            -- demo seed value
ON CONFLICT (account_id) DO NOTHING;

-- 6. Row level security (defence in depth; the server connects with the service role)
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['contacts','conversations','messages','deals','broadcasts','automations',
                           'system_logs','whatsapp_accounts','memberships'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON public.%I
                      USING (account_id = NULLIF(current_setting('app.account_id', true), '')::uuid)
                      WITH CHECK (account_id = NULLIF(current_setting('app.account_id', true), '')::uuid)$p$, t);
  END LOOP;
END $$;
ALTER TABLE public.accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.accounts;
CREATE POLICY tenant_isolation ON public.accounts
    USING (id = NULLIF(current_setting('app.account_id', true), '')::uuid);
-- users and sessions hold password hashes and session tokens: no client access at all.
ALTER TABLE public.users    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.login_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.settings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.users, public.sessions, public.login_attempts, public.settings FROM anon, authenticated;

-- 7. Close the secret leak on public project reads ---------------------------
-- Policy "Public can view active projects" let anon SELECT every column, including
-- github_token and webhook_secret. Keep public read, but only of non-secret columns.
REVOKE SELECT ON public.projects FROM anon, authenticated;
GRANT SELECT (id, name, github_repo, github_branch, target_framework, content_dir, file_extension, topic,
              target_audience, tone, keywords, author_name, publishing_mode, publish_time, is_active,
              zero_redeploy_enabled, blog_page_path, created_at, updated_at)
    ON public.projects TO anon, authenticated;
DROP POLICY IF EXISTS "Public can view active projects" ON public.projects;
CREATE POLICY "Public can view active projects" ON public.projects FOR SELECT USING (is_active = true);

-- 8. Legacy tables ------------------------------------------------------------
-- whatsapp_configs held plaintext access tokens and a shared default verify token.
-- Left in place (no data loss) but locked; drop it in the contract migration after
-- owners have re-entered credentials.
ALTER TABLE public.whatsapp_configs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.whatsapp_configs FROM anon, authenticated;

-- 9. After review, an operator grants access, for example (NOT run here):
--   INSERT INTO public.memberships (account_id, user_id, role) VALUES ('<account uuid>', <user id>, 'owner');
--   UPDATE public.users SET is_platform_admin = true WHERE username = '<operator>';

COMMIT;
