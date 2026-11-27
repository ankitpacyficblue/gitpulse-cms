DROP TABLE IF EXISTS automation_runs;
DROP TABLE IF EXISTS permission_overrides;
DROP TABLE IF EXISTS role_permissions;
ALTER TABLE memberships DROP COLUMN IF EXISTS role_key_base;
ALTER TABLE memberships DROP COLUMN IF EXISTS role_key;
