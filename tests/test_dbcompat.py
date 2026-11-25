"""SQL translation and the Postgres connection wrapper (no live Postgres needed)."""
import unittest

import tests._env  # noqa: F401
import dbcompat
from dbcompat import PGConnection, translate


class FakeRaw:
    """Stands in for a pg8000 DB-API cursor."""
    def __init__(self):
        self.calls, self.rowcount, self.description, self._rows = [], 1, None, []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql.upper().startswith("INSERT") and "RETURNING id" in sql:
            self.description, self._rows = [("id",)], [(42,)]
        elif sql.upper().startswith("SELECT"):
            self.description, self._rows = [("id",), ("name",)], [(1, "a"), (2, "b")]
        else:
            self.description, self._rows = None, []

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self):
        self.raw, self.events = FakeRaw(), []

    def cursor(self):
        return self.raw

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")

    def close(self):
        self.events.append("close")


class TranslateTests(unittest.TestCase):
    def test_placeholders_and_percent(self):
        self.assertEqual(translate("SELECT * FROM t WHERE a = ? AND b LIKE ?"),
                         "SELECT * FROM t WHERE a = %s AND b ILIKE %s")
        self.assertEqual(translate("SELECT '100%' , ?"), "SELECT '100%%' , %s")

    def test_question_mark_inside_literal_is_kept(self):
        self.assertEqual(translate("SELECT 'what?' WHERE a = ?"), "SELECT 'what?' WHERE a = %s")

    def test_ddl(self):
        out = translate("CREATE TABLE x (id INTEGER PRIMARY KEY AUTOINCREMENT, v REAL NOT NULL)")
        self.assertIn("SERIAL PRIMARY KEY", out)
        self.assertIn("DOUBLE PRECISION", out)
        self.assertNotIn("AUTOINCREMENT", out)

    def test_add_column_is_idempotent(self):
        self.assertIn("ADD COLUMN IF NOT EXISTS", translate("ALTER TABLE users ADD COLUMN email TEXT"))

    def test_pragma(self):
        self.assertIsNone(translate("PRAGMA journal_mode=WAL"))
        info = translate("PRAGMA table_info(users)")
        self.assertIn("information_schema.columns", info)
        self.assertIn("'users'", info)

    def test_insert_table_detection(self):
        self.assertEqual(dbcompat.insert_table("INSERT INTO contacts (a) VALUES (?)"), "contacts")
        self.assertIsNone(dbcompat.insert_table("INSERT INTO accounts (id) VALUES (?)"))
        self.assertIsNone(dbcompat.insert_table("INSERT INTO contacts (a) VALUES (?) RETURNING id"))


class WrapperTests(unittest.TestCase):
    def test_insert_returns_lastrowid(self):
        c = FakeConn()
        cur = PGConnection(c).execute("INSERT INTO contacts (name) VALUES (?)", ("x",))
        self.assertEqual(cur.lastrowid, 42)
        self.assertTrue(c.raw.calls[0][0].endswith("RETURNING id"))

    def test_rows_support_index_name_and_dict(self):
        c = FakeConn()
        rows = PGConnection(c).execute("SELECT id, name FROM t").fetchall()
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0]["name"], "a")
        self.assertEqual(dict(rows[1]), {"id": 2, "name": "b"})
        self.assertEqual(tuple(rows[1]), (2, "b"))

    def test_context_commits_then_closes_and_rolls_back_on_error(self):
        c = FakeConn()
        with PGConnection(c) as conn:
            conn.execute("SELECT 1")
        self.assertEqual(c.events, ["commit", "close"])
        c2 = FakeConn()
        with self.assertRaises(ValueError):
            with PGConnection(c2):
                raise ValueError("boom")
        self.assertEqual(c2.events, ["rollback", "close"])

    def test_sqlite_is_default_without_database_url(self):
        import os
        old = os.environ.pop("DATABASE_URL", None)
        try:
            self.assertFalse(dbcompat.is_postgres())
        finally:
            if old is not None:
                os.environ["DATABASE_URL"] = old


class PoolTests(unittest.TestCase):
    def test_connection_reused_and_nested_use_gets_separate_one(self):
        import threading
        opened = []

        class Raw(FakeConn):
            def __init__(self):
                super().__init__()
                opened.append(self)

        dbcompat._cache = threading.local()
        orig = dbcompat._open_postgres
        dbcompat._open_postgres = lambda: Raw()
        try:
            with dbcompat.connect_postgres() as a:
                with dbcompat.connect_postgres() as b:      # nested: must not share a's transaction
                    self.assertIsNot(a._raw, b._raw)
            with dbcompat.connect_postgres() as c:          # sequential: reuses the cached connection
                self.assertIs(c._raw, a._raw)
            self.assertEqual(len(opened), 2)
            self.assertNotIn("close", a._raw.events)        # cached connection is not closed
            self.assertIn("close", b._raw.events)           # non-cached one is
        finally:
            dbcompat._open_postgres = orig
            dbcompat._cache = threading.local()


class PortTests(unittest.TestCase):
    def test_supabase_pooler_session_port_switches_to_transaction_port(self):
        import os
        os.environ.pop("DATABASE_POOL_MODE", None)
        self.assertEqual(dbcompat.effective_port("postgresql://u:p@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"), 6543)
        self.assertEqual(dbcompat.effective_port("postgresql://u:p@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"), 6543)
        self.assertEqual(dbcompat.effective_port("postgresql://u:p@db.example.com:5432/x"), 5432)
        self.assertEqual(dbcompat.effective_port("postgresql://u:p@db.example.com/x"), 5432)
        os.environ["DATABASE_POOL_MODE"] = "session"
        try:
            self.assertEqual(dbcompat.effective_port("postgresql://u:p@aws-0-x.pooler.supabase.com:5432/postgres"), 5432)
        finally:
            os.environ.pop("DATABASE_POOL_MODE", None)


class RetryTests(unittest.TestCase):
    def test_first_statement_on_dead_connection_is_retried_once(self):
        class Dead(FakeRaw):
            def execute(self, sql, params=()):
                raise OSError("socket closed")

        class DeadConn(FakeConn):
            def __init__(self):
                super().__init__()
                self.raw = Dead()

        fresh = FakeConn()
        orig = dbcompat._open_postgres
        dbcompat._open_postgres = lambda: fresh
        try:
            conn = PGConnection(DeadConn())
            rows = conn.execute("SELECT id, name FROM t").fetchall()
            self.assertEqual(len(rows), 2)
        finally:
            dbcompat._open_postgres = orig

    def test_is_transient(self):
        self.assertTrue(dbcompat.is_transient(OSError("x")))
        self.assertTrue(dbcompat.is_transient(Exception("(EMAXCONNSESSION) max clients reached")))
        self.assertFalse(dbcompat.is_transient(ValueError("bad")))


class UniqueTests(unittest.TestCase):
    def test_detects_sqlite_and_postgres(self):
        self.assertTrue(dbcompat.is_unique_violation(Exception("UNIQUE constraint failed: contacts.phone_norm")))
        self.assertTrue(dbcompat.is_unique_violation(Exception("{'C': '23505', 'M': 'duplicate key value violates unique constraint'}")))
        self.assertFalse(dbcompat.is_unique_violation(Exception("syntax error")))


class SslTests(unittest.TestCase):
    def setUp(self):
        import os
        self._old = os.environ.pop("DATABASE_SSL_ROOT_CERT", None)

    def tearDown(self):
        import os
        os.environ.pop("DATABASE_SSL_ROOT_CERT", None)
        if self._old is not None:
            os.environ["DATABASE_SSL_ROOT_CERT"] = self._old

    def test_default_remote_is_encrypted_without_verification(self):
        import ssl
        ctx = dbcompat.ssl_context("postgresql://u:p@db.example.com:5432/postgres")
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)
        self.assertFalse(ctx.check_hostname)

    def test_localhost_and_disable_use_no_tls(self):
        self.assertIsNone(dbcompat.ssl_context("postgresql://u:p@localhost/postgres"))
        self.assertIsNone(dbcompat.ssl_context("postgresql://u:p@db.example.com/x?sslmode=disable"))

    def test_verify_modes(self):
        import ssl
        c = dbcompat.ssl_context("postgresql://u:p@h/x?sslmode=verify-full")
        self.assertEqual(c.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(c.check_hostname)
        c = dbcompat.ssl_context("postgresql://u:p@h/x?sslmode=verify-ca")
        self.assertEqual(c.verify_mode, ssl.CERT_REQUIRED)
        self.assertFalse(c.check_hostname)

    def test_unknown_mode_rejected_without_leaking_url(self):
        with self.assertRaises(ValueError) as e:
            dbcompat.ssl_context("postgresql://u:secret@h/x?sslmode=bogus")
        self.assertNotIn("secret", str(e.exception))

    def test_root_cert_env_forces_verify_full(self):
        import os, ssl, subprocess, tempfile
        d = tempfile.mkdtemp()
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", d + "/k.pem",
                        "-out", d + "/c.pem", "-days", "1", "-subj", "/CN=t"], check=True, capture_output=True)
        os.environ["DATABASE_SSL_ROOT_CERT"] = open(d + "/c.pem").read()
        c = dbcompat.ssl_context("postgresql://u:p@db.example.com/x")
        self.assertEqual(c.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(c.check_hostname)


class RlsTests(unittest.TestCase):
    def test_every_table_the_app_creates_is_in_the_rls_list(self):
        import re, database, crm_store, inspect
        src = inspect.getsource(database._apply_schema) + inspect.getsource(crm_store.init_schema)
        created = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", src))
        covered = dbcompat.AUTOID_TABLES | dbcompat.OTHER_TABLES
        self.assertEqual(created - covered, set(), "tables created without an RLS entry")


if __name__ == "__main__":
    unittest.main()
