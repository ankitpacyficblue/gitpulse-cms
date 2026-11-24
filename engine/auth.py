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
        cursor.execute("SELECT id, username, role, created_at FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def create_user(username: str, password: str, role: str = "admin") -> int:
    salt_hex, hash_hex = hash_password(password)
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (username, password_hash, salt, role, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (username.strip().lower(), hash_hex, salt_hex, role, now))
        conn.commit()
        return cursor.lastrowid

def update_user_password(user_id: int, new_password: str) -> bool:
    salt_hex, hash_hex = hash_password(new_password)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET password_hash = ?, salt = ? WHERE id = ?
        """, (hash_hex, salt_hex, user_id))
        conn.commit()
        # Invalidate all existing sessions for this user on password change
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0

def init_default_admin() -> Dict[str, str]:
    """Ensure an administrator account exists upon initial startup."""
    admin = get_user_by_username("admin")
    if not admin:
        default_pass = "GitPulse@Admin2026!"
        create_user("admin", default_pass, role="admin")
        log_event("Created initial default admin account.", "WARN")
        return {"username": "admin", "password": default_pass, "is_new": True}
    return {"username": "admin", "is_new": False}

# --- Session Management ---

def get_auth_secret_key() -> str:
    """Returns persistent secret key for signing tokens."""
    key = os.environ.get("SESSION_SECRET") or os.environ.get("SUPABASE_KEY")
    if key:
        return key
    return "gitpulse_cms_stateless_master_auth_secret_key_2026_v1"

def create_session(user_id: int, ip_address: str = "", user_agent: str = "") -> str:
    """Generate an HMAC-signed stateless session token with 48h validity and DB audit trail."""
    user = get_user_by_id(user_id)
    username = user["username"] if user else "admin"
    role = user["role"] if user else "admin"
    
    expires_at = int(time.time()) + SESSION_DURATION_SEC
    nonce = secrets.token_hex(8)
    body = f"{user_id}:{expires_at}:{role}:{username}:{nonce}"
    sig = hmac.new(get_auth_secret_key().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{body}:{sig}"
    token = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")

    now = datetime.utcnow().isoformat()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (token, user_id, expires_at, ip_address, user_agent, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (token, user_id, float(expires_at), ip_address, user_agent, now))
            conn.commit()
    except Exception:
        pass

    return token

def validate_session(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate a session token.
    Supports both HMAC-SHA256 signed stateless verification (for serverless instances)
    and SQLite database session store with revocation checks.
    """
    if not token:
        return None

    now = time.time()

    # 1. Cryptographic verification of HMAC-signed token (Works across any serverless instance)
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        parts = raw.split(":")
        if len(parts) == 6:
            user_id_str, expires_at_str, role, username, nonce, sig = parts
            body = f"{user_id_str}:{expires_at_str}:{role}:{username}:{nonce}"
            expected_sig = hmac.new(get_auth_secret_key().encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected_sig, sig):
                expires_at = int(expires_at_str)
                if expires_at < now:
                    return None  # Token expired

                # Check if explicitly revoked in sessions table
                try:
                    with get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM sessions WHERE token = ? AND expires_at < 0", (token,))
                        if cursor.fetchone():
                            return None
                except Exception:
                    pass

                return {
                    "id": int(user_id_str),
                    "username": username,
                    "role": role,
                    "token": token
                }
    except Exception:
        pass

    # 2. Fallback to direct DB query (for legacy tokens or local SQLite)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.token, s.expires_at, u.id, u.username, u.role
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = ?
            """, (token,))
            row = cursor.fetchone()

            if not row:
                return None

            if row["expires_at"] < now:
                cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
                conn.commit()
                return None

            return {
                "id": row["id"],
                "username": row["username"],
                "role": row["role"],
                "token": row["token"]
            }
    except Exception:
        return None

def revoke_session(token: str):
    """Revoke a session (logout)."""
    if not token:
        return
    user_id = 1
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        parts = raw.split(":")
        if len(parts) >= 1 and parts[0].isdigit():
            user_id = int(parts[0])
    except Exception:
        pass

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
            cursor.execute("""
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
        "role": user["role"]
    }, None
