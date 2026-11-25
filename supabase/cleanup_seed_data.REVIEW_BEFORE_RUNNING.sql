-- Removes the demo rows the old seed functions inserted. NOT RUN by the agent, and never run
-- automatically. Run on a copy first. Each statement is limited to the exact seed values;
-- nothing here deletes by account. Check the SELECT counts first.

-- Preview
SELECT 'projects' AS t, count(*) FROM public.projects WHERE github_repo IN
  ('cloudscale-ops/documentation-portal','ai-pulse-community/engineering-blog')
UNION ALL SELECT 'contacts', count(*) FROM public.contacts WHERE email IN ('sarah.jenkins@cloudscale.io','arivera@aipulse.dev')
UNION ALL SELECT 'whatsapp_configs', count(*) FROM public.whatsapp_configs WHERE phone_number_id = '109876543210123';

-- Delete (uncomment after reviewing the preview). Child rows go with their parent via the existing cascades.
-- BEGIN;
-- DELETE FROM public.projects WHERE github_repo IN ('cloudscale-ops/documentation-portal','ai-pulse-community/engineering-blog');
-- DELETE FROM public.contacts WHERE email IN ('sarah.jenkins@cloudscale.io','arivera@aipulse.dev');
-- DELETE FROM public.whatsapp_configs WHERE phone_number_id = '109876543210123';
-- COMMIT;
-- Also review by hand: the default admin user 'admin' (password was the published default
-- 'GitPulse@Admin2026!'): disable it with  UPDATE public.users SET is_active = false WHERE username = 'admin';
