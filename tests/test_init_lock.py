"""Schema setup must survive parallel cold starts.

The Postgres test needs a real server and is skipped without INIT_TEST_DATABASE_URL. It works only inside a
throwaway schema that it drops afterwards, and uses the session pooler (SET search_path needs a session)."""
import os
import secrets
import subprocess
import sys
import unittest
from unittest import mock

import tests._env  # noqa: F401
import database
import dbcompat
from engine import auth


class RetryTests(unittest.TestCase):
    def test_deadlock_is_retried(self):
        real, calls = database._apply_schema, []

        def flaky(conn):
            calls.append(1)
            if len(calls) == 1:
                raise Exception({"C": "40P01", "M": "deadlock detected"})
            real(conn)

        with mock.patch.object(database, "_apply_schema", flaky), mock.patch.object(database.time, "sleep"):
            database.init_db()
        self.assertEqual(len(calls), 2)

    def test_other_errors_are_not_retried(self):
        calls = []

        def broken(conn):
            calls.append(1)
            raise Exception("syntax error")

        with mock.patch.object(database, "_apply_schema", broken), self.assertRaises(Exception):
            database.init_db()
        self.assertEqual(len(calls), 1)

    def test_admin_bootstrap_runs_once(self):
        env = {"BOOTSTRAP_ADMIN_USERNAME": "init-lock-admin", "BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(16)}
        with mock.patch.dict(os.environ, env):
            self.assertIsNotNone(auth.init_db_and_admin())
            self.assertIsNone(auth.init_db_and_admin())


PG_URL = os.environ.get("INIT_TEST_DATABASE_URL", "")
WORKER = "from engine.auth import init_db_and_admin; print('created' if init_db_and_admin() else 'skipped')"


@unittest.skipUnless(PG_URL, "set INIT_TEST_DATABASE_URL to run against Postgres")
class ConcurrentPostgresTests(unittest.TestCase):
    WORKERS = 8

    def setUp(self):
        self.schema = "init_test_" + secrets.token_hex(4)
        self.env = dict(os.environ, DATABASE_URL=PG_URL, DATABASE_SCHEMA=self.schema, DATABASE_POOL_MODE="session",
                        BOOTSTRAP_ADMIN_USERNAME="init-admin", BOOTSTRAP_ADMIN_PASSWORD=secrets.token_urlsafe(16),
                        PYTHONPATH=tests._env.ROOT)
        patcher = mock.patch.dict(os.environ, {k: self.env[k] for k in ("DATABASE_URL", "DATABASE_POOL_MODE")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self._sql(f"CREATE SCHEMA {self.schema}")     # up front: concurrent CREATE SCHEMA is its own race
        self.addCleanup(self._sql, f"DROP SCHEMA {self.schema} CASCADE")

    def _sql(self, sql):
        raw = dbcompat._open_postgres()
        try:
            cur = raw.cursor()
            cur.execute(sql)
            rows = cur.fetchall() if cur.description else []
            raw.commit()
            return [list(r) for r in rows]
        finally:
            raw.close()

    def _cold_starts(self):
        procs = [subprocess.Popen([sys.executable, "-W", "ignore", "-c", WORKER], env=self.env, text=True,
                                  cwd=tests._env.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for _ in range(self.WORKERS)]
        results = [(p.communicate(timeout=300), p.returncode) for p in procs]
        for (_, err), code in results:
            # Only the last line: it names the error and never includes the URL.
            self.assertEqual(code, 0, (err.strip().splitlines() or [""])[-1])
        return sorted(out.strip() for (out, _), _ in results)

    def test_parallel_cold_starts_on_empty_schema_then_again(self):
        s = self.schema
        first = self._cold_starts()
        self.assertEqual(first, ["created"] + ["skipped"] * (self.WORKERS - 1))
        self.assertEqual(self._sql(f"SELECT COUNT(*) FROM {s}.schema_version"), [[1]])
        self.assertEqual(self._sql(f"SELECT COUNT(*) FROM {s}.users"), [[1]])
        unprotected = self._sql("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                                f"WHERE n.nspname = '{s}' AND c.relkind = 'r' AND NOT c.relrowsecurity")
        self.assertEqual(unprotected, [])
        self.assertEqual(self._cold_starts(), ["skipped"] * self.WORKERS)


if __name__ == "__main__":
    unittest.main()
