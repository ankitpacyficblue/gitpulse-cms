"""
GitPulse CMS - Authentication & Security Engine
Provides PBKDF2-HMAC password hashing, timing-attack-safe verification,
session lifecycle management, and brute-force/malicious login restriction.
"""

import time
import secrets
import hashlib
import hmac
import base64
import os
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from database import get_connection, log_event

# Security Parameters
PBKDF2_ITERATIONS = 260_000 # OWASP recommended minimum
MAX_FAILED_ATTEMPTS = 5      # Lockout threshold
LOCKOUT_DURATION_SEC = 900   # 15 minutes lockout window
SESSION_DURATION_SEC = 86400 * 2 # 48 hours session lifetime

def hash_password(password: str) -> Tuple[str, str]:
    """Generate cryptographically secure salt and PBKDF2-HMAC-SHA256 hash."""
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        PBKDF2_ITERATIONS
    )
    return salt.hex(), key.hex()

def verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    """Verify password in constant time to prevent timing attacks."""
    try:
        salt = bytes.fromhex(salt_hex)
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            PBKDF2_ITERATIONS
        )
        # Constant-time comparison
        return hmac.compare_digest(key.hex(), expected_hash_hex)
    except Exception:
        return False

# --- Malicious Login & Brute Force Prevention ---

def check_login_lockout(ip_address: str, username: str) -> Tuple[bool, int]:
    """
    Check if the IP or username is currently locked out due to repeated failures.
    Returns (is_locked_out, remaining_lockout_seconds).
    """
    now = time.time()
    cutoff = now - LOCKOUT_DURATION_SEC

    with get_connection() as conn:
        cursor = conn.cursor()
        # Find failed attempts within the lockout window
        cursor.execute("""
            SELECT attempt_time FROM login_attempts
            WHERE (ip_address = ? OR username = ?)
              AND attempt_time > ?
              AND success = 0
            ORDER BY attempt_time DESC
        """, (ip_address, username, cutoff))
        rows = cursor.fetchall()

    if len(rows) >= MAX_FAILED_ATTEMPTS:
        # User is locked out. Calculate remaining time based on latest failed attempt
        latest_attempt_time = rows[0]["attempt_time"]
        elapsed = now - latest_attempt_time
        remaining = max(1, int(LOCKOUT_DURATION_SEC - elapsed))
        return True, remaining

    return False, 0

def record_login_attempt(ip_address: str, username: str, success: bool):
    """Record an authentication attempt for audit and rate-limiting."""
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO login_attempts (ip_address, username, attempt_time, success)
            VALUES (?, ?, ?, ?)
        """, (ip_address, username, now, 1 if success else 0))
        
        # If login was successful, clear out previous failed attempts for this user/IP
        if success:
            cursor.execute("""
                DELETE FROM login_attempts
                WHERE (ip_address = ? OR username = ?) AND success = 0
            """, (ip_address, username))

        # Cleanup old attempts older than 24 hours to keep table small
        cursor.execute("DELETE FROM login_attempts WHERE attempt_time < ?", (now - 86400,))
        conn.commit()

# --- User Management ---

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""SELECT id, username, COALESCE(email, '') AS email, COALESCE(is_active, 1) AS is_active,
                                 COALESCE(is_platform_admin, 0) AS is_platform_admin, created_at
                          FROM users WHERE id = ?""", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_user(username: str, password: str, email: str = "", is_platform_admin: bool = False) -> int:
    """Create a login. Roles live on account memberships, not on the user."""
    username = username.strip().lower()
    if not username or len(password) < 8:
        raise ValueError("A username and a password of at least 8 characters are required.")
    salt_hex, hash_hex = hash_password(password)
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, password_hash, salt, role, email, is_active, is_platform_admin, created_at)
            VALUES (?, ?, ?, 'member', ?, 1, ?, ?)
        """, (username, hash_hex, salt_hex, email.strip().lower(), 1 if is_platform_admin else 0, now))
        conn.commit()
        return cursor.lastrowid

def set_user_active(user_id: int, active: bool) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if active else 0, user_id))
        if not active:
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0

def update_user_password(user_id: int, new_password: str) -> bool:
    salt_hex, hash_hex = hash_password(new_password)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET password_hash = ?, salt = ? WHERE id = ?
        """, (hash_hex, salt_hex, user_id))
        updated = cursor.rowcount > 0
        # Invalidate all existing sessions for this user on password change
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
        return updated

def bootstrap_platform_admin_from_env() -> Optional[int]:
    """For hosts with no shell (Vercel): create the first platform admin from environment variables
    BOOTSTRAP_ADMIN_USERNAME / BOOTSTRAP_ADMIN_PASSWORD (min 12 chars). Does nothing if either is
    missing or the user already exists. There is no built-in default login."""
    username = (os.environ.get("BOOTSTRAP_ADMIN_USERNAME") or "").strip().lower()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD") or ""
    if not username or len(password) < 12 or get_user_by_username(username):
        return None
    user_id = create_user(username, password, is_platform_admin=True)
    log_event(f"Platform admin '{username}' created from environment.", "INFO")
    return user_id

def generate_temporary_password() -> str:
    return secrets.token_urlsafe(12)

# --- Session Management ---

def get_auth_secret_key() -> str:
    """Signing key for session tokens. SESSION_SECRET is required on serverless hosts.
    Local runs without it generate a random key once and keep it in the settings table."""
    key = os.environ.get("SESSION_SECRET")
    if key:
        return key
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        raise RuntimeError("SESSION_SECRET must be set in the environment.")
    from database import get_setting, set_setting
    stored = get_setting("session_secret", "")
    if not stored:
        stored = secrets.token_hex(32)
        set_setting("session_secret", stored)
    return stored

def _sign(body: str) -> str:
    return hmac.new(get_auth_secret_key().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()

def create_session(user_id: int, ip_address: str = "", user_agent: str = "") -> str:
    """HMAC-signed token (user id, expiry, nonce). Role and account access are NOT in the token:
    they are read from the database on every request, so changes apply immediately."""
    expires_at = int(time.time()) + SESSION_DURATION_SEC
    body = f"{user_id}:{expires_at}:{secrets.token_hex(8)}"
    token = base64.urlsafe_b64encode(f"{body}:{_sign(body)}".encode("utf-8")).decode("utf-8")
    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO sessions (token, user_id, expires_at, ip_address, user_agent, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (token, user_id, float(expires_at), ip_address, user_agent, datetime.utcnow().isoformat()))
            conn.commit()
    except Exception:
        pass
    return token

def validate_session(token: str) -> Optional[Dict[str, Any]]:
    """Return the signed-in user, or None for a bad, expired, revoked token or an inactive user."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        user_id_str, expires_at_str, nonce, sig = raw.split(":")
        if not hmac.compare_digest(_sign(f"{user_id_str}:{expires_at_str}:{nonce}"), sig):
            return None
        if int(expires_at_str) < time.time():
            return None
        with get_connection() as conn:
            if conn.execute("SELECT 1 FROM sessions WHERE token = ? AND expires_at < 0", (token,)).fetchone():
                return None
        user = get_user_by_id(int(user_id_str))
    except Exception:
        return None
    if not user or not user["is_active"]:
        return None
    return {"id": user["id"], "username": user["username"], "email": user["email"],
            "is_platform_admin": bool(user["is_platform_admin"]), "token": token}

def revoke_session(token: str):
    """Revoke a session (logout) by recording a tombstone for the token."""
    if not token:
        return
    user_id = None
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        user_id = int(raw.split(":")[0])
    except Exception:
        return
    try:
        with get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.execute("""
                INSERT INTO sessions (token, user_id, expires_at, ip_address, user_agent, created_at)
                VALUES (?, ?, -1, '', '', ?)
            """, (token, user_id, datetime.utcnow().isoformat()))
            conn.commit()
    except Exception:
        pass

# --- High-level Login Handler ---

def authenticate_user(username: str, password: str, ip_address: str = "", user_agent: str = "") -> Tuple[bool, Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """
    Attempt authentication with brute force and malicious login restrictions.
    Returns: (success, session_token, user_dict, error_message).
    """
    clean_user = username.strip().lower()

    # 1. Check if IP or username is locked out
    locked, remaining_sec = check_login_lockout(ip_address, clean_user)
    if locked:
        msg = f"Account temporarily locked to protect against brute-force attacks. Please retry in {remaining_sec} seconds."
        log_event(f"Blocked malicious login attempt for '{clean_user}' from {ip_address} (Lockout active).", "WARN")
        return False, None, None, msg

    # 2. Lookup user
    user = get_user_by_username(clean_user)
    if not user:
        record_login_attempt(ip_address, clean_user, success=False)
        # Generic error message to prevent user enumeration
        return False, None, None, "Invalid username or password."

    if not user.get("is_active", 1):
        record_login_attempt(ip_address, clean_user, success=False)
        return False, None, None, "Invalid username or password."

    # 3. Verify password
    if not verify_password(password, user["salt"], user["password_hash"]):
        record_login_attempt(ip_address, clean_user, success=False)
        log_event(f"Failed password attempt for '{clean_user}' from {ip_address}.", "WARN")
        return False, None, None, "Invalid username or password."

    # 4. Successful login
    record_login_attempt(ip_address, clean_user, success=True)
    token = create_session(user["id"], ip_address, user_agent)
    log_event(f"User '{clean_user}' logged in successfully from {ip_address}.", "INFO")

    return True, token, {
        "id": user["id"],
        "username": user["username"],
        "is_platform_admin": bool(user.get("is_platform_admin", 0))
    }, None
