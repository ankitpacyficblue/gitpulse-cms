"""
GitPulse CMS - database driver switch.

The app writes SQLite-flavoured SQL (`?` placeholders, INTEGER PRIMARY KEY
AUTOINCREMENT). When DATABASE_URL is set (postgres://...), connections go to
Postgres through pg8000 (pure Python, works on Vercel) and every statement is
translated by `translate()`. With no DATABASE_URL the app uses SQLite, which
is what the tests and local runs use.

The DATABASE_URL is a secret: it is never logged or put in an error message.
"""

import os
import re
import sqlite3
import ssl
from typing import Any, List, Optional, Sequence
from urllib.parse import parse_qs, unquote, urlparse

# Tables whose primary key is a generated integer `id` (INSERT returns it).
# Tables with a non-integer primary key (RLS is enabled on these too, see database.init_db).
OTHER_TABLES = {"accounts", "memberships", "sessions", "settings", "account_settings"}
AUTOID_TABLES = {
    "clients", "projects", "posts", "system_logs", "users", "login_attempts", "post_views",
    "whatsapp_accounts", "contacts", "conversations", "messages", "deals", "broadcasts", "automations",
}


def is_unique_violation(exc: Exception) -> bool:
    """True for a unique-constraint error from SQLite ("UNIQUE constraint failed") or Postgres (23505)."""
    t = str(exc)
    return "UNIQUE" in t or "23505" in t or "duplicate key" in t.lower()


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def is_postgres() -> bool:
    return database_url().lower().startswith(("postgres://", "postgresql://"))


# --------------------------------------------------------------------------
# SQL translation (pure, unit tested)
# --------------------------------------------------------------------------
_PRAGMA_INFO = re.compile(r"^\s*PRAGMA\s+table_info\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;?\s*$", re.I)
_PRAGMA = re.compile(r"^\s*PRAGMA\b", re.I)
_INSERT = re.compile(r"^\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)


def _split_literals(sql: str) -> List[tuple]:
    """Split SQL into (is_literal, text) parts so rewrites skip '...' strings."""
    parts, buf, i, n = [], [], 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            if buf:
                parts.append((False, "".join(buf)))
                buf = []
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            parts.append((True, sql[i:j + 1]))
            i = j + 1
        else:
            buf.append(ch)
            i += 1
    if buf:
        parts.append((False, "".join(buf)))
    return parts


def translate(sql: str) -> Optional[str]:
    """SQLite-flavoured SQL -> Postgres SQL. None means "run nothing"."""
    m = _PRAGMA_INFO.match(sql)
    if m:
        return ("SELECT ordinal_position - 1 AS cid, column_name AS name FROM information_schema.columns "
                f"WHERE table_schema = current_schema() AND table_name = '{m.group(1).lower()}' "
                "ORDER BY ordinal_position")
    if _PRAGMA.match(sql):
        return None
    out = []
    for is_lit, text in _split_literals(sql):
        if is_lit:
            out.append(text.replace("%", "%%"))
            continue
        t = text.replace("%", "%%").replace("?", "%s")
        t = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "SERIAL PRIMARY KEY", t, flags=re.I)
        t = re.sub(r"\bREAL\b", "DOUBLE PRECISION", t, flags=re.I)
        t = re.sub(r"\bLIKE\b", "ILIKE", t, flags=re.I)
        t = re.sub(r"(\bALTER\s+TABLE\s+\S+\s+ADD\s+COLUMN\s+)(?!IF\s+NOT\s+EXISTS)", r"\1IF NOT EXISTS ", t, flags=re.I)
        out.append(t)
    return "".join(out)


def insert_table(sql: str) -> Optional[str]:
    m = _INSERT.match(sql)
    if m and m.group(1).lower() in AUTOID_TABLES and not re.search(r"\bRETURNING\b", sql, re.I):
        return m.group(1).lower()
    return None


# --------------------------------------------------------------------------
# Postgres connection wrapper that behaves like the sqlite3 bits the app uses
# --------------------------------------------------------------------------
class PGRow:
    """Row with index access, name access, keys() and dict() support."""
    __slots__ = ("_names", "_values")

    def __init__(self, names: Sequence[str], values: Sequence[Any]):
        self._names, self._values = list(names), list(values)

    def keys(self):
        return list(self._names)

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        try:
            return self._values[self._names.index(key)]
        except ValueError:
            raise KeyError(key)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


class PGCursor:
    def __init__(self, raw):
        self._raw = raw
        self.lastrowid = None
        self.rowcount = -1
        self._names: List[str] = []
        self._rows: Optional[list] = None
        self._pos = 0

    def execute(self, sql: str, params: Sequence[Any] = ()):
        pg_sql = translate(sql)
        self._rows, self._pos, self.lastrowid = None, 0, None
        if pg_sql is None:
            self._rows, self.rowcount = [], 0
            return self
        table = insert_table(sql)
        if table:
            pg_sql = pg_sql.rstrip().rstrip(";") + " RETURNING id"
        self._raw.execute(pg_sql, tuple(params))
        self.rowcount = self._raw.rowcount
        desc = self._raw.description
        if desc:
            self._names = [d[0].decode() if isinstance(d[0], bytes) else d[0] for d in desc]
            self._rows = [PGRow(self._names, r) for r in self._raw.fetchall()]
            if table and self._rows:
                self.lastrowid = self._rows[0][0]
                self.rowcount = len(self._rows)
        else:
            self._rows = []
        return self

    def executemany(self, sql: str, seq):
        for params in seq:
            self.execute(sql, params)
        return self

    def fetchone(self):
        if not self._rows or self._pos >= len(self._rows):
            return None
        row = self._rows[self._pos]
        self._pos += 1
        return row

    def fetchall(self):
        rows = (self._rows or [])[self._pos:]
        self._pos = len(self._rows or [])
        return rows

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        try:
            self._raw.close()
        except Exception:
            pass


class PGConnection:
    def __init__(self, raw):
        self._raw = raw

    def cursor(self):
        return PGCursor(self._raw.cursor())

    def execute(self, sql: str, params: Sequence[Any] = ()):
        return self.cursor().execute(sql, params)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        try:
            self._raw.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


def ssl_context(url: str):
    """libpq-style sslmode: disable | require (default, encrypted, no cert check) |
    verify-ca | verify-full. DATABASE_SSL_ROOT_CERT (PEM text) forces verify-full
    against that CA. Nothing here logs the URL."""
    u = urlparse(url)
    mode = (parse_qs(u.query).get("sslmode", [""])[0] or "").lower()
    pem = os.environ.get("DATABASE_SSL_ROOT_CERT", "").strip()
    if not mode:
        mode = "disable" if (u.hostname or "") in ("localhost", "127.0.0.1") else "require"
    if pem:
        mode = "verify-full"
    if mode in ("disable", "allow", "prefer"):
        return None
    if mode == "require":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if mode not in ("verify-ca", "verify-full"):
        raise ValueError("unsupported sslmode")
    ctx = ssl.create_default_context(cadata=pem or None)
    ctx.check_hostname = mode == "verify-full"
    return ctx


def connect_postgres() -> PGConnection:
    import pg8000.dbapi  # imported lazily: only needed when DATABASE_URL is set
    url = database_url()
    u = urlparse(url)
    raw = pg8000.dbapi.connect(
        user=unquote(u.username or ""), password=unquote(u.password or ""),
        host=u.hostname, port=u.port or 5432,
        database=(u.path or "/postgres").lstrip("/") or "postgres",
        ssl_context=ssl_context(url), timeout=20,
    )
    schema = os.environ.get("DATABASE_SCHEMA", "").strip()
    if schema:
        # Isolated schema (e.g. a throwaway test run). Name is validated, never interpolated raw.
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,40}", schema):
            raise ValueError("invalid DATABASE_SCHEMA")
        cur = raw.cursor()
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        cur.execute(f"SET search_path TO {schema}")
        raw.commit()
    return PGConnection(raw)


def connect_sqlite(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
