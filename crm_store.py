"""
GitPulse CMS - Account-scoped storage: accounts, memberships, per-account
WhatsApp credentials and the CRM tables (contacts, conversations, messages,
deals, broadcasts, automations).

Tenancy rule: every function that touches tenant data takes `account_id` as a
required first argument and every query filters on it, including UPDATE and
DELETE. There is no "all accounts" read path. Ids from a request are never
trusted on their own: a row is only reachable together with its account_id.
"""

import dbcompat
from currencies import is_valid_currency
import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from database import get_connection
from engine import secrets_box
from engine.permissions import ROLES

CRM_TABLES = ("contacts", "conversations", "messages", "deals", "broadcasts", "automations")


def _now() -> str:
    return datetime.utcnow().isoformat()


def _norm_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _tags(raw: Any, default: Optional[list] = None) -> list:
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else (default or [])
    except Exception:
        return default if default is not None else []


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def init_schema(conn) -> None:
    """Create account-scoped tables. Pre-account tables without account_id are
    renamed to legacy_<name> (data kept, never read by the app, never deleted)."""
    cur = conn.cursor()
    for t in CRM_TABLES + ("whatsapp_configs",):
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})").fetchall()]
        if cols and "account_id" not in cols:
            cur.execute(f"ALTER TABLE {t} RENAME TO legacy_{t}")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        contact_email TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','deleted')),
        created_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS memberships (
        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('owner','admin','agent','viewer')),
        created_at TEXT NOT NULL,
        PRIMARY KEY (account_id, user_id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS whatsapp_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL UNIQUE REFERENCES accounts(id) ON DELETE RESTRICT,
        phone_number_id TEXT NOT NULL DEFAULT '',
        waba_id TEXT NOT NULL DEFAULT '',
        business_name TEXT NOT NULL DEFAULT '',
        phone_number TEXT NOT NULL DEFAULT '',
        access_token_enc TEXT NOT NULL DEFAULT '',
        app_secret_enc TEXT NOT NULL DEFAULT '',
        verify_token_hash TEXT NOT NULL DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_phone_number_id
                   ON whatsapp_accounts (phone_number_id) WHERE phone_number_id != ''""")

    A = "account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT"
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, {A},
        name TEXT NOT NULL, phone TEXT NOT NULL, phone_norm TEXT NOT NULL,
        email TEXT DEFAULT '', tags TEXT NOT NULL DEFAULT '["Lead"]', notes TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE (account_id, phone_norm), UNIQUE (id, account_id)
    )""")
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, {A},
        contact_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open',
        assigned_to TEXT NOT NULL DEFAULT 'Team', unread_count INTEGER NOT NULL DEFAULT 0,
        last_message_at TEXT, last_message_preview TEXT DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE (account_id, contact_id), UNIQUE (id, account_id),
        FOREIGN KEY (contact_id, account_id) REFERENCES contacts(id, account_id) ON DELETE CASCADE
    )""")
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, {A},
        conversation_id INTEGER NOT NULL, contact_id INTEGER NOT NULL,
        direction TEXT NOT NULL, message_type TEXT NOT NULL DEFAULT 'text',
        body TEXT NOT NULL, media_url TEXT DEFAULT '', wa_message_id TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'sent', error_message TEXT DEFAULT '', created_at TEXT NOT NULL,
        FOREIGN KEY (conversation_id, account_id) REFERENCES conversations(id, account_id) ON DELETE CASCADE,
        FOREIGN KEY (contact_id, account_id) REFERENCES contacts(id, account_id) ON DELETE CASCADE
    )""")
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, {A},
        contact_id INTEGER, title TEXT NOT NULL, value REAL NOT NULL DEFAULT 0.0,
        currency TEXT NOT NULL DEFAULT 'USD', stage TEXT NOT NULL DEFAULT 'lead',
        expected_close TEXT DEFAULT '', notes TEXT DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY (contact_id, account_id) REFERENCES contacts(id, account_id) ON DELETE SET NULL
    )""")
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS broadcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, {A},
        name TEXT NOT NULL, template_body TEXT NOT NULL, target_tag TEXT NOT NULL DEFAULT 'all',
        total_recipients INTEGER NOT NULL DEFAULT 0, sent_count INTEGER NOT NULL DEFAULT 0,
        delivered_count INTEGER NOT NULL DEFAULT 0, read_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'draft', scheduled_at TEXT DEFAULT '', created_at TEXT NOT NULL
    )""")
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS automations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, {A},
        name TEXT NOT NULL, trigger_type TEXT NOT NULL, trigger_keyword TEXT DEFAULT '',
        action_type TEXT NOT NULL DEFAULT 'send_message', message_template TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1, executions_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS account_settings (
        account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE RESTRICT,
        ai_provider TEXT NOT NULL DEFAULT '', ai_api_key_enc TEXT NOT NULL DEFAULT '',
        github_token_enc TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
    )""")
    acct_cols = {r[1] for r in cur.execute("PRAGMA table_info(accounts)").fetchall()}
    if "default_currency" not in acct_cols:
        cur.execute("ALTER TABLE accounts ADD COLUMN default_currency TEXT NOT NULL DEFAULT 'INR'")
    wa_cols = {r[1] for r in cur.execute("PRAGMA table_info(whatsapp_accounts)").fetchall()}
    for col, ddl in (("last_webhook_at", "TEXT NOT NULL DEFAULT ''"), ("last_test_at", "TEXT NOT NULL DEFAULT ''"),
                     ("last_test_ok", "INTEGER NOT NULL DEFAULT 0"), ("last_test_message", "TEXT NOT NULL DEFAULT ''")):
        if col not in wa_cols:
            cur.execute(f"ALTER TABLE whatsapp_accounts ADD COLUMN {col} {ddl}")
    conv_cols = {r[1] for r in cur.execute("PRAGMA table_info(conversations)").fetchall()}
    if "assigned_user_id" not in conv_cols:
        cur.execute("ALTER TABLE conversations ADD COLUMN assigned_user_id INTEGER")
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_contacts_acct ON contacts (account_id, updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_conv_acct ON conversations (account_id, last_message_at)",
        "CREATE INDEX IF NOT EXISTS idx_msg_acct_conv ON messages (account_id, conversation_id)",
        "CREATE INDEX IF NOT EXISTS idx_msg_acct_wa ON messages (account_id, wa_message_id)",
        "CREATE INDEX IF NOT EXISTS idx_deals_acct ON deals (account_id, stage)",
        "CREATE INDEX IF NOT EXISTS idx_bc_acct ON broadcasts (account_id)",
        "CREATE INDEX IF NOT EXISTS idx_auto_acct ON automations (account_id)",
        "CREATE INDEX IF NOT EXISTS idx_members_user ON memberships (user_id)",
    ):
        cur.execute(stmt)


# --------------------------------------------------------------------------
# Accounts and memberships
# --------------------------------------------------------------------------

def create_account(name: str, contact_email: str = "") -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Account name is required.")
    acct = {"id": uuid.uuid4().hex, "name": name, "contact_email": (contact_email or "").strip(),
            "status": "active", "created_at": _now()}
    with get_connection() as conn:
        conn.execute("INSERT INTO accounts (id, name, contact_email, status, created_at) VALUES (?,?,?,?,?)",
                     (acct["id"], acct["name"], acct["contact_email"], acct["status"], acct["created_at"]))
        conn.commit()
    return acct


def get_account(account_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ? AND status != 'deleted'", (account_id,)).fetchone()
        return dict(row) if row else None


def set_default_currency(account_id: str, currency: str) -> bool:
    cur_code = (currency or "").strip().upper()
    if not is_valid_currency(cur_code):
        raise ValueError("Currency must be a valid ISO code such as INR or USD.")
    with get_connection() as conn:
        cur = conn.execute("UPDATE accounts SET default_currency = ? WHERE id = ? AND status != 'deleted'",
                           (cur_code, account_id))
        conn.commit()
        return cur.rowcount > 0


def rename_account(account_id: str, name: str) -> bool:
    name = (name or "").strip()
    if not name:
        raise ValueError("Account name is required.")
    with get_connection() as conn:
        cur = conn.execute("UPDATE accounts SET name = ? WHERE id = ? AND status != 'deleted'", (name, account_id))
        conn.commit()
        return cur.rowcount > 0


def soft_delete_account(account_id: str) -> bool:
    """Mark deleted. Rows stay scoped to the account (never become global); memberships removed."""
    with get_connection() as conn:
        cur = conn.execute("UPDATE accounts SET status = 'deleted' WHERE id = ? AND status != 'deleted'", (account_id,))
        conn.execute("UPDATE whatsapp_accounts SET is_active = 0, phone_number_id = '' WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM memberships WHERE account_id = ?", (account_id,))
        conn.commit()
        return cur.rowcount > 0


def list_accounts_for_user(user_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT a.id, a.name, m.role FROM memberships m JOIN accounts a ON a.id = m.account_id
            WHERE m.user_id = ? AND a.status = 'active' ORDER BY a.name""", (user_id,)).fetchall()
        return [dict(r) for r in rows]


def list_all_accounts(user_id: int) -> List[Dict[str, Any]]:
    """Platform admins see every active account; role is theirs if they are a member, else "owner"
    (platform support access), and member_count helps them find empty or abandoned accounts."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT a.id, a.name, a.default_currency,
                   (SELECT COUNT(*) FROM memberships mm WHERE mm.account_id = a.id) AS member_count,
                   (SELECT m.role FROM memberships m WHERE m.account_id = a.id AND m.user_id = ?) AS my_role
            FROM accounts a WHERE a.status = 'active' ORDER BY a.name""", (user_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["role"] = d.pop("my_role") or "owner"
        out.append(d)
    return out


def get_membership_role(account_id: str, user_id: int) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute("""
            SELECT m.role FROM memberships m JOIN accounts a ON a.id = m.account_id
            WHERE m.account_id = ? AND m.user_id = ? AND a.status = 'active'""", (account_id, user_id)).fetchone()
        return row["role"] if row else None


def add_membership(account_id: str, user_id: int, role: str) -> None:
    if role not in ROLES:
        raise ValueError("Invalid role.")
    with get_connection() as conn:
        conn.execute("INSERT INTO memberships (account_id, user_id, role, created_at) VALUES (?,?,?,?)",
                     (account_id, user_id, role, _now()))
        conn.commit()


def count_owners(account_id: str) -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM memberships WHERE account_id = ? AND role = 'owner'",
                            (account_id,)).fetchone()[0]


def set_membership_role(account_id: str, user_id: int, role: str) -> bool:
    if role not in ROLES:
        raise ValueError("Invalid role.")
    with get_connection() as conn:
        cur = conn.execute("UPDATE memberships SET role = ? WHERE account_id = ? AND user_id = ?",
                           (role, account_id, user_id))
        conn.commit()
        return cur.rowcount > 0


def _unassign_for_removed(conn, account_id: str, user_id: int) -> None:
    conn.execute("UPDATE conversations SET assigned_user_id = NULL, assigned_to = 'Team' "
                 "WHERE account_id = ? AND assigned_user_id = ?", (account_id, user_id))


def remove_membership(account_id: str, user_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM memberships WHERE account_id = ? AND user_id = ?", (account_id, user_id))
        _unassign_for_removed(conn, account_id, user_id)
        conn.commit()
        return cur.rowcount > 0


def list_members(account_id: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT u.id AS user_id, u.username, COALESCE(u.email, '') AS email,
                   COALESCE(u.is_active, 1) AS is_active, m.role
            FROM memberships m JOIN users u ON u.id = m.user_id
            WHERE m.account_id = ? ORDER BY u.username""", (account_id,)).fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Per-account WhatsApp credentials
# --------------------------------------------------------------------------

def _hash_verify(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def save_whatsapp_account(account_id: str, phone_number_id: Optional[str] = None, waba_id: Optional[str] = None,
                          business_name: Optional[str] = None, phone_number: Optional[str] = None,
                          access_token: str = "", app_secret: str = "") -> Optional[str]:
    """Create/update this account's WhatsApp config. Empty access_token/app_secret keep the stored
    values. Returns a new verify token (shown once) when the row is first created, else None."""
    now = _now()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM whatsapp_accounts WHERE account_id = ?", (account_id,)).fetchone()
        token_enc = secrets_box.encrypt(access_token.strip(), account_id) if access_token.strip() else None
        secret_enc = secrets_box.encrypt(app_secret.strip(), account_id) if app_secret.strip() else None
        def keep(new, old):  # absent field (None) keeps the stored value
            return old if new is None else new.strip()
        if row:
            conn.execute("""UPDATE whatsapp_accounts SET phone_number_id=?, waba_id=?, business_name=?,
                            phone_number=?, access_token_enc=?, app_secret_enc=?, is_active=1, updated_at=?
                            WHERE account_id=?""",
                         (keep(phone_number_id, row["phone_number_id"]), keep(waba_id, row["waba_id"]),
                          keep(business_name, row["business_name"]), keep(phone_number, row["phone_number"]),
                          token_enc if token_enc is not None else row["access_token_enc"],
                          secret_enc if secret_enc is not None else row["app_secret_enc"], now, account_id))
            conn.commit()
            return None
        verify = secrets.token_urlsafe(24)
        conn.execute("""INSERT INTO whatsapp_accounts (account_id, phone_number_id, waba_id, business_name,
                        phone_number, access_token_enc, app_secret_enc, verify_token_hash, is_active,
                        created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
                     (account_id, (phone_number_id or "").strip(), (waba_id or "").strip(),
                      (business_name or "").strip(), (phone_number or "").strip(),
                      token_enc or "", secret_enc or "", _hash_verify(verify), now, now))
        conn.commit()
        return verify


def _settings_row(account_id: str):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM account_settings WHERE account_id = ?", (account_id,)).fetchone()


def save_account_settings(account_id: str, ai_provider: Optional[str] = None, ai_api_key: str = "",
                          github_token: str = "", clear_ai_key: bool = False, clear_github_token: bool = False) -> None:
    """Per-account blog settings. Empty key/token keep the stored value; clear_* removes it."""
    row = _settings_row(account_id)
    provider = (row["ai_provider"] if row else "") if ai_provider is None else ai_provider.strip()
    key_enc = row["ai_api_key_enc"] if row else ""
    gh_enc = row["github_token_enc"] if row else ""
    if clear_ai_key:
        key_enc = ""
    if ai_api_key.strip():
        key_enc = secrets_box.encrypt(ai_api_key.strip(), account_id)
    if clear_github_token:
        gh_enc = ""
    if github_token.strip():
        gh_enc = secrets_box.encrypt(github_token.strip(), account_id)
    with get_connection() as conn:
        if row:
            conn.execute("""UPDATE account_settings SET ai_provider=?, ai_api_key_enc=?, github_token_enc=?, updated_at=?
                            WHERE account_id=?""", (provider, key_enc, gh_enc, _now(), account_id))
        else:
            conn.execute("""INSERT INTO account_settings (account_id, ai_provider, ai_api_key_enc, github_token_enc, updated_at)
                            VALUES (?,?,?,?,?)""", (account_id, provider, key_enc, gh_enc, _now()))
        conn.commit()


def _open_setting(enc: str, account_id: str) -> str:
    try:
        return secrets_box.decrypt(enc, account_id) if enc else ""
    except secrets_box.SecretsBoxError:
        return ""


def get_account_ai(account_id: str):
    """(provider, api_key) this account chose, or ('', '') so the caller falls back to the platform setting."""
    row = _settings_row(account_id)
    if not row:
        return "", ""
    return row["ai_provider"], _open_setting(row["ai_api_key_enc"], account_id)


def get_account_github_token(account_id: str) -> str:
    row = _settings_row(account_id)
    return _open_setting(row["github_token_enc"], account_id) if row else ""


def get_account_settings_public(account_id: str) -> Dict[str, Any]:
    """Write-only secrets: the API reports only whether a value is set and its last 4 characters."""
    row = _settings_row(account_id)
    key = _open_setting(row["ai_api_key_enc"], account_id) if row else ""
    gh = _open_setting(row["github_token_enc"], account_id) if row else ""
    return {"ai_provider": (row["ai_provider"] if row else ""), "has_ai_api_key": bool(key),
            "ai_api_key_masked": secrets_box.mask(key), "has_github_token": bool(gh),
            "github_token_masked": secrets_box.mask(gh),
            "ai_key_source": "account" if key else "platform"}


def rotate_verify_token(account_id: str) -> Optional[str]:
    verify = secrets.token_urlsafe(24)
    with get_connection() as conn:
        cur = conn.execute("UPDATE whatsapp_accounts SET verify_token_hash = ?, updated_at = ? WHERE account_id = ?",
                           (_hash_verify(verify), _now(), account_id))
        conn.commit()
        return verify if cur.rowcount else None


def get_whatsapp_public(account_id: str) -> Dict[str, Any]:
    """Safe view for the API: never contains the token, app secret or verify hash."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM whatsapp_accounts WHERE account_id = ?", (account_id,)).fetchone()
    if not row:
        return {"configured": False, "has_token": False, "token_masked": "", "phone_number_id": "",
                "waba_id": "", "business_name": "", "phone_number": ""}
    masked = ""
    if row["access_token_enc"]:
        try:
            masked = secrets_box.mask(secrets_box.decrypt(row["access_token_enc"], account_id))
        except secrets_box.SecretsBoxError:
            masked = "…"
    return {"configured": bool(row["phone_number_id"]), "has_token": bool(row["access_token_enc"]),
            "token_masked": masked, "has_app_secret": bool(row["app_secret_enc"]),
            "phone_number_id": row["phone_number_id"], "waba_id": row["waba_id"],
            "business_name": row["business_name"], "phone_number": row["phone_number"],
            "is_active": bool(row["is_active"])}


def touch_whatsapp_webhook(account_id: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE whatsapp_accounts SET last_webhook_at = ? WHERE account_id = ?", (_now(), account_id))
        conn.commit()


def save_whatsapp_test(account_id: str, ok: bool, message: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE whatsapp_accounts SET last_test_at = ?, last_test_ok = ?, last_test_message = ? "
                     "WHERE account_id = ?", (_now(), 1 if ok else 0, (message or "")[:300], account_id))
        conn.commit()


def get_whatsapp_status(account_id: str) -> Dict[str, Any]:
    """Setup-wizard view: what is saved, when Meta last called us, and the last connection test.
    Never includes a token, secret or hash."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM whatsapp_accounts WHERE account_id = ?", (account_id,)).fetchone()
    if not row:
        return {"credentials": {"phone_number_id": False, "access_token": False, "app_secret": False, "verify_token": False},
                "last_webhook_at": None, "last_test": None}
    return {"credentials": {"phone_number_id": bool(row["phone_number_id"]), "access_token": bool(row["access_token_enc"]),
                            "app_secret": bool(row["app_secret_enc"]), "verify_token": bool(row["verify_token_hash"])},
            "last_webhook_at": row["last_webhook_at"] or None,
            "last_test": ({"at": row["last_test_at"], "ok": bool(row["last_test_ok"]), "message": row["last_test_message"]}
                          if row["last_test_at"] else None)}


def get_whatsapp_credentials(account_id: str) -> Dict[str, str]:
    """Server-side only. Returns decrypted credentials, or empty strings when not configured."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM whatsapp_accounts WHERE account_id = ? AND is_active = 1",
                           (account_id,)).fetchone()
    if not row:
        return {"phone_number_id": "", "access_token": "", "app_secret": ""}
    return {"phone_number_id": row["phone_number_id"],
            "access_token": secrets_box.decrypt(row["access_token_enc"], account_id),
            "app_secret": secrets_box.decrypt(row["app_secret_enc"], account_id)}


def find_account_by_phone_number_id(phone_number_id: str) -> Optional[str]:
    if not phone_number_id:
        return None
    with get_connection() as conn:
        row = conn.execute("""SELECT w.account_id FROM whatsapp_accounts w JOIN accounts a ON a.id = w.account_id
                              WHERE w.phone_number_id = ? AND w.is_active = 1 AND a.status = 'active'""",
                           (phone_number_id,)).fetchone()
        return row["account_id"] if row else None


def verify_token_matches_any(token: str) -> bool:
    if not token:
        return False
    digest = _hash_verify(token)
    with get_connection() as conn:
        rows = conn.execute("""SELECT w.verify_token_hash FROM whatsapp_accounts w JOIN accounts a ON a.id = w.account_id
                               WHERE w.is_active = 1 AND a.status = 'active' AND w.verify_token_hash != ''""").fetchall()
    ok = False
    for r in rows:
        ok |= hmac.compare_digest(digest, r["verify_token_hash"])
    return ok


# --------------------------------------------------------------------------
# Contacts
# --------------------------------------------------------------------------

def _contact(row) -> Dict[str, Any]:
    d = dict(row)
    d.pop("phone_norm", None)
    d["tags"] = _tags(d.get("tags"), ["Lead"])
    return d


def list_contacts(account_id: str, search: str = "", tag: str = "") -> List[Dict[str, Any]]:
    q, p = "SELECT * FROM contacts WHERE account_id = ?", [account_id]
    if search:
        q += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
        p += [f"%{search}%"] * 3
    if tag:
        q += " AND tags LIKE ?"
        p.append(f"%{tag}%")
    q += " ORDER BY updated_at DESC, id DESC"
    with get_connection() as conn:
        return [_contact(r) for r in conn.execute(q, p).fetchall()]


def get_contact(account_id: str, contact_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM contacts WHERE id = ? AND account_id = ?", (contact_id, account_id)).fetchone()
        return _contact(row) if row else None


def get_contact_by_phone(account_id: str, phone: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM contacts WHERE account_id = ? AND phone_norm = ?",
                           (account_id, _norm_phone(phone))).fetchone()
        return _contact(row) if row else None


def create_contact(account_id: str, name: str, phone: str, email: str = "", tags: Any = None,
                   notes: str = "") -> int:
    """Raises ValueError('duplicate_phone') when this account already has the number."""
    tags_list = ["Lead"] if tags is None else (tags if isinstance(tags, list) else [str(tags)])
    now = _now()
    with get_connection() as conn:
        try:
            cur = conn.execute("""INSERT INTO contacts (account_id, name, phone, phone_norm, email, tags, notes,
                                  status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,'active',?,?)""",
                               (account_id, name.strip(), phone.strip(), _norm_phone(phone), email.strip(),
                                json.dumps(tags_list), notes.strip(), now, now))
        except Exception as e:
            if dbcompat.is_unique_violation(e):
                raise ValueError("duplicate_phone")
            raise
        conn.commit()
        return cur.lastrowid


def update_contact(account_id: str, contact_id: int, **kwargs) -> bool:
    fields, params = [], []
    for k in ("name", "phone", "email", "tags", "notes", "status"):
        if k in kwargs:
            v = kwargs[k]
            if k == "tags" and isinstance(v, list):
                v = json.dumps(v)
            fields.append(f"{k} = ?")
            params.append(v)
            if k == "phone":
                fields.append("phone_norm = ?")
                params.append(_norm_phone(v))
    if not fields:
        return False
    fields.append("updated_at = ?")
    params += [_now(), contact_id, account_id]
    with get_connection() as conn:
        cur = conn.execute(f"UPDATE contacts SET {', '.join(fields)} WHERE id = ? AND account_id = ?", params)
        conn.commit()
        return cur.rowcount > 0


def delete_contact(account_id: str, contact_id: int) -> bool:
    with get_connection() as conn:
        # Unlink deals first: the composite FK's SET NULL would also null account_id.
        conn.execute("UPDATE deals SET contact_id = NULL WHERE contact_id = ? AND account_id = ?",
                     (contact_id, account_id))
        cur = conn.execute("DELETE FROM contacts WHERE id = ? AND account_id = ?", (contact_id, account_id))
        conn.commit()
        return cur.rowcount > 0


# --------------------------------------------------------------------------
# Conversations and messages
# --------------------------------------------------------------------------

_CONV_SELECT = """SELECT conv.*, c.name AS contact_name, c.phone AS contact_phone,
                  c.email AS contact_email, c.tags AS contact_tags
                  FROM conversations conv JOIN contacts c ON c.id = conv.contact_id AND c.account_id = conv.account_id"""


def _conv(row) -> Dict[str, Any]:
    d = dict(row)
    d["contact_tags"] = _tags(d.get("contact_tags"), ["Lead"])
    return d


def list_conversations(account_id: str, status: str = "", assigned_user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    q, p = _CONV_SELECT + " WHERE conv.account_id = ?", [account_id]
    if assigned_user_id is not None:
        q += " AND conv.assigned_user_id = ?"
        p.append(assigned_user_id)
    if status:
        q += " AND conv.status = ?"
        p.append(status)
    q += " ORDER BY conv.last_message_at DESC, conv.id DESC"
    with get_connection() as conn:
        return [_conv(r) for r in conn.execute(q, p).fetchall()]


def assign_conversation(account_id: str, conversation_id: int, user_id: Optional[int]) -> bool:
    """Assign to a member of this account (or None to unassign). Caller has checked membership."""
    label = "Team"
    if user_id is not None:
        with get_connection() as conn:
            row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        label = row["username"] if row else "Team"
    with get_connection() as conn:
        cur = conn.execute("""UPDATE conversations SET assigned_user_id = ?, assigned_to = ?, updated_at = ?
                              WHERE id = ? AND account_id = ?""",
                           (user_id, label, _now(), conversation_id, account_id))
        conn.commit()
        return cur.rowcount > 0


def get_conversation(account_id: str, conversation_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(_CONV_SELECT + " WHERE conv.id = ? AND conv.account_id = ?",
                           (conversation_id, account_id)).fetchone()
        return _conv(row) if row else None


def get_or_create_conversation(account_id: str, contact_id: int) -> Optional[Dict[str, Any]]:
    """None when the contact does not belong to this account."""
    if not get_contact(account_id, contact_id):
        return None
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM conversations WHERE account_id = ? AND contact_id = ?",
                           (account_id, contact_id)).fetchone()
        if not row:
            now = _now()
            cur = conn.execute("""INSERT INTO conversations (account_id, contact_id, status, assigned_to, unread_count,
                                  last_message_at, last_message_preview, created_at, updated_at)
                                  VALUES (?,?,'open','Team',0,?,'New conversation',?,?)""",
                               (account_id, contact_id, now, now, now))
            conn.commit()
            return get_conversation(account_id, cur.lastrowid)
    return get_conversation(account_id, row["id"])


def mark_conversation_read(account_id: str, conversation_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("UPDATE conversations SET unread_count = 0 WHERE id = ? AND account_id = ?",
                           (conversation_id, account_id))
        conn.commit()
        return cur.rowcount > 0


def list_messages(account_id: str, conversation_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""SELECT * FROM messages WHERE account_id = ? AND conversation_id = ?
                               ORDER BY id ASC LIMIT ?""", (account_id, conversation_id, limit)).fetchall()
        return [dict(r) for r in rows]


def create_message(account_id: str, conversation_id: int, contact_id: int, direction: str, body: str,
                   message_type: str = "text", media_url: str = "", wa_message_id: str = "",
                   status: str = "sent", error_message: str = "") -> Optional[int]:
    """None when the conversation or contact is not in this account."""
    if not get_conversation(account_id, conversation_id) or not get_contact(account_id, contact_id):
        return None
    now = _now()
    preview = (body[:60] + "...") if len(body) > 60 else body
    with get_connection() as conn:
        cur = conn.execute("""INSERT INTO messages (account_id, conversation_id, contact_id, direction, message_type,
                              body, media_url, wa_message_id, status, error_message, created_at)
                              VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                           (account_id, conversation_id, contact_id, direction, message_type, body.strip(),
                            media_url.strip(), wa_message_id.strip(), status, error_message, now))
        unread = ", unread_count = unread_count + 1" if direction == "inbound" else ""
        conn.execute(f"""UPDATE conversations SET last_message_at = ?, last_message_preview = ?, updated_at = ?{unread}
                         WHERE id = ? AND account_id = ?""", (now, preview, now, conversation_id, account_id))
        conn.commit()
        return cur.lastrowid


def update_message_status(account_id: str, wa_message_id: str, status: str) -> bool:
    if not wa_message_id:
        return False
    with get_connection() as conn:
        cur = conn.execute("UPDATE messages SET status = ? WHERE account_id = ? AND wa_message_id = ?",
                           (status, account_id, wa_message_id))
        conn.commit()
        return cur.rowcount > 0


# --------------------------------------------------------------------------
# Deals
# --------------------------------------------------------------------------

def list_deals(account_id: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("""SELECT d.*, c.name AS contact_name, c.phone AS contact_phone, c.email AS contact_email
                               FROM deals d LEFT JOIN contacts c ON c.id = d.contact_id AND c.account_id = d.account_id
                               WHERE d.account_id = ? ORDER BY d.id DESC""", (account_id,)).fetchall()
        return [dict(r) for r in rows]


def create_deal(account_id: str, title: str, value: float, stage: str = "lead", contact_id: Optional[int] = None,
                currency: Optional[str] = None, expected_close: str = "", notes: str = "") -> int:
    if not currency:
        currency = (get_account(account_id) or {}).get("default_currency") or "INR"
    currency = currency.strip().upper()
    if not is_valid_currency(currency):
        raise ValueError("invalid_currency")
    if float(value) < 0:
        raise ValueError("negative_value")
    if contact_id is not None and not get_contact(account_id, contact_id):
        raise ValueError("contact_not_found")
    now = _now()
    with get_connection() as conn:
        cur = conn.execute("""INSERT INTO deals (account_id, contact_id, title, value, currency, stage, expected_close,
                              notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                           (account_id, contact_id, title.strip(), float(value), currency, stage.lower().strip(),
                            expected_close, notes.strip(), now, now))
        conn.commit()
        return cur.lastrowid


def update_deal_stage(account_id: str, deal_id: int, stage: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("UPDATE deals SET stage = ?, updated_at = ? WHERE id = ? AND account_id = ?",
                           (stage.lower().strip(), _now(), deal_id, account_id))
        conn.commit()
        return cur.rowcount > 0


def delete_deal(account_id: str, deal_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM deals WHERE id = ? AND account_id = ?", (deal_id, account_id))
        conn.commit()
        return cur.rowcount > 0


# --------------------------------------------------------------------------
# Broadcasts and automations
# --------------------------------------------------------------------------

def list_broadcasts(account_id: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM broadcasts WHERE account_id = ? ORDER BY id DESC", (account_id,)).fetchall()]


def get_broadcast(account_id: str, broadcast_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM broadcasts WHERE id = ? AND account_id = ?",
                           (broadcast_id, account_id)).fetchone()
        return dict(row) if row else None


def create_broadcast(account_id: str, name: str, template_body: str, target_tag: str = "all",
                     scheduled_at: str = "") -> int:
    with get_connection() as conn:
        cur = conn.execute("""INSERT INTO broadcasts (account_id, name, template_body, target_tag, status, scheduled_at,
                              created_at) VALUES (?,?,?,?,'draft',?,?)""",
                           (account_id, name.strip(), template_body.strip(), target_tag.strip(), scheduled_at, _now()))
        conn.commit()
        return cur.lastrowid


def update_broadcast_stats(account_id: str, broadcast_id: int, total: int = 0, sent: int = 0,
                           delivered: int = 0, read: int = 0, status: str = "completed") -> bool:
    with get_connection() as conn:
        cur = conn.execute("""UPDATE broadcasts SET total_recipients=?, sent_count=?, delivered_count=?, read_count=?,
                              status=? WHERE id = ? AND account_id = ?""",
                           (total, sent, delivered, read, status, broadcast_id, account_id))
        conn.commit()
        return cur.rowcount > 0


def list_automations(account_id: str) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM automations WHERE account_id = ? ORDER BY id ASC", (account_id,)).fetchall()]


def create_automation(account_id: str, name: str, trigger_type: str, message_template: str,
                      trigger_keyword: str = "", action_type: str = "send_message", is_active: bool = True) -> int:
    now = _now()
    with get_connection() as conn:
        cur = conn.execute("""INSERT INTO automations (account_id, name, trigger_type, trigger_keyword, action_type,
                              message_template, is_active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                           (account_id, name.strip(), trigger_type.strip(), trigger_keyword.strip().lower(),
                            action_type.strip(), message_template.strip(), 1 if is_active else 0, now, now))
        conn.commit()
        return cur.lastrowid


def toggle_automation(account_id: str, automation_id: int, is_active: bool) -> bool:
    with get_connection() as conn:
        cur = conn.execute("UPDATE automations SET is_active = ?, updated_at = ? WHERE id = ? AND account_id = ?",
                           (1 if is_active else 0, _now(), automation_id, account_id))
        conn.commit()
        return cur.rowcount > 0


def delete_automation(account_id: str, automation_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM automations WHERE id = ? AND account_id = ?", (automation_id, account_id))
        conn.commit()
        return cur.rowcount > 0


def increment_automation_execution(account_id: str, automation_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("""UPDATE automations SET executions_count = executions_count + 1
                              WHERE id = ? AND account_id = ?""", (automation_id, account_id))
        conn.commit()
        return cur.rowcount > 0
