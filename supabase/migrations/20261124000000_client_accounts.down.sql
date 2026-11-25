-- Rollback for 20261124000000_client_accounts.sql. Not applied by the agent.
-- Removes only objects the migration created; original columns and data are untouched.
BEGIN;
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['contacts','conversations','messages','deals','broadcasts','automations','system_logs','accounts'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', t);
  END LOOP;
END $$;
DROP TABLE IF EXISTS public.account_settings;
DROP INDEX IF EXISTS public.idx_conv_one_per_contact;
ALTER TABLE public.conversations DROP COLUMN IF EXISTS assigned_user_id;
ALTER TABLE public.whatsapp_accounts DROP COLUMN IF EXISTS last_webhook_at, DROP COLUMN IF EXISTS last_test_at, DROP COLUMN IF EXISTS last_test_ok, DROP COLUMN IF EXISTS last_test_message;
ALTER TABLE public.accounts DROP COLUMN IF EXISTS default_currency;
ALTER TABLE public.users DROP COLUMN IF EXISTS must_change_password, DROP COLUMN IF EXISTS temp_password_expires, DROP COLUMN IF EXISTS sessions_valid_after_ms;
DROP TABLE IF EXISTS public.whatsapp_accounts;
DROP TABLE IF EXISTS public.memberships;
ALTER TABLE public.messages      DROP CONSTRAINT IF EXISTS messages_conversation_same_account, DROP CONSTRAINT IF EXISTS messages_contact_same_account;
ALTER TABLE public.deals         DROP CONSTRAINT IF EXISTS deals_contact_same_account;
ALTER TABLE public.conversations DROP CONSTRAINT IF EXISTS conversations_contact_same_account, DROP CONSTRAINT IF EXISTS conversations_id_account_uq;
ALTER TABLE public.contacts      DROP CONSTRAINT IF EXISTS contacts_id_account_uq;
DROP INDEX IF EXISTS public.contacts_account_phone_uq, public.conversations_account_contact_uq;
ALTER TABLE public.contacts DROP COLUMN IF EXISTS phone_norm;
ALTER TABLE public.projects      DROP COLUMN IF EXISTS account_id;
ALTER TABLE public.system_logs   DROP COLUMN IF EXISTS account_id;
ALTER TABLE public.contacts      DROP COLUMN IF EXISTS account_id;
ALTER TABLE public.conversations DROP COLUMN IF EXISTS account_id;
ALTER TABLE public.messages      DROP COLUMN IF EXISTS account_id;
ALTER TABLE public.deals         DROP COLUMN IF EXISTS account_id;
ALTER TABLE public.broadcasts    DROP COLUMN IF EXISTS account_id;
ALTER TABLE public.automations   DROP COLUMN IF EXISTS account_id;
ALTER TABLE public.users DROP COLUMN IF EXISTS email, DROP COLUMN IF EXISTS is_active, DROP COLUMN IF EXISTS is_platform_admin;
DROP TABLE IF EXISTS public.accounts;
-- Column-level grants on projects and the RLS enablement on users/sessions are left as the safer state.
COMMIT;
