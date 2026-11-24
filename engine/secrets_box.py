"""
GitPulse CMS - Credential encryption (AES-256-GCM).

Per-account WhatsApp secrets are encrypted at rest. The key comes from the
CREDENTIAL_ENC_KEY environment variable (32 random bytes, base64 encoded).
Ciphertext is bound to the owning account through the GCM associated data, so
a value copied from one account's row cannot be decrypted as another account's.
Plaintext and key are never logged and never put in error messages.
"""

import base64
import os
import secrets
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "v1:"


class SecretsBoxError(Exception):
    """Raised when a secret cannot be encrypted or decrypted. Message never holds secret data."""


def _load_key() -> bytes:
    raw = os.environ.get("CREDENTIAL_ENC_KEY", "").strip()
    if not raw:
        raise SecretsBoxError("CREDENTIAL_ENC_KEY is not set")
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except Exception:
        raise SecretsBoxError("CREDENTIAL_ENC_KEY is not valid base64")
    if len(key) != 32:
        raise SecretsBoxError("CREDENTIAL_ENC_KEY must decode to 32 bytes")
    return key


def generate_key() -> str:
    """Return a new random key suitable for CREDENTIAL_ENC_KEY."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def is_configured() -> bool:
    try:
        _load_key()
        return True
    except SecretsBoxError:
        return False


def encrypt(plaintext: str, account_id: str) -> str:
    if not plaintext:
        return ""
    nonce = secrets.token_bytes(12)
    ct = AESGCM(_load_key()).encrypt(nonce, plaintext.encode("utf-8"), account_id.encode("utf-8"))
    return PREFIX + base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt(token: str, account_id: str) -> str:
    if not token:
        return ""
    if not token.startswith(PREFIX):
        raise SecretsBoxError("unsupported ciphertext format")
    try:
        blob = base64.urlsafe_b64decode(token[len(PREFIX):].encode("ascii"))
        nonce, ct = blob[:12], blob[12:]
        return AESGCM(_load_key()).decrypt(nonce, ct, account_id.encode("utf-8")).decode("utf-8")
    except SecretsBoxError:
        raise
    except (InvalidTag, ValueError):
        raise SecretsBoxError("could not decrypt value (wrong key or wrong account)")


def mask(secret: str) -> str:
    """Display form of a secret: only the last 4 characters, never more."""
    if not secret:
        return ""
    return "…" + secret[-4:] if len(secret) > 8 else "…"
