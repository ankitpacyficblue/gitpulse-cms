# Scheduler (every 3 hours)

Approved posts publish on the first run at or after their time, so within 3 hours of it.
Supabase `pg_cron` + `pg_net` call `/api/internal/tick`. The daily Vercel cron in `vercel.json` stays as a fallback.

## Switch on (a person, once; after CRON_SECRET is set in Vercel Production and this code is in production)

Paste into the Supabase SQL editor, putting the CRON_SECRET value in the third line. Do not commit that value.

```sql
create extension if not exists pg_cron;
create extension if not exists pg_net;
select vault.create_secret('<CRON_SECRET value>', 'gitpulse_cron_secret');
select cron.schedule('gitpulse-tick', '0 */3 * * *', $$
  select net.http_post(
    url := 'https://gitpulsecms.vercel.app/api/internal/tick',
    headers := jsonb_build_object('X-Cron-Secret',
      (select decrypted_secret from vault.decrypted_secrets where name = 'gitpulse_cron_secret')),
    timeout_milliseconds := 60000)
$$);
```

## Check

```sql
select status, return_message, start_time from cron.job_run_details order by start_time desc limit 5;
select status_code, created from net._http_response order by created desc limit 5;  -- expect 200
```

## Switch off

```sql
select cron.unschedule('gitpulse-tick');
```
