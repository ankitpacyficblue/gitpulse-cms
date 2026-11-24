"""
GitPulse CMS - RFC 6238 Time-Based One-Time Password (TOTP) Engine
Zero-dependency, pure Python implementation for 2-Factor Authentication (2FA).
Generates base32 secrets, otpauth URIs, inline SVG QR codes, and verifies codes.
"""

import time
import hmac
import hashlib
import struct
import base64
import secrets
from typing import Tuple, Optional

# Base32 alphabet for standard authenticator apps
BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

def generate_totp_secret(length: int = 20) -> str:
    """Generate a random base32 encoded secret key (160-bit standard)."""
    random_bytes = secrets.token_bytes(length)
    return base64.b32encode(random_bytes).decode('utf-8').replace('=', '')

def generate_totp_code(secret: str, time_step: int = 30, for_time: Optional[float] = None) -> str:
    """Compute current 6-digit TOTP code for a secret."""
    t = int((for_time or time.time()) // time_step)
    
    # Pad base32 secret if necessary
    secret_clean = secret.strip().replace(' ', '').upper()
    padding = (8 - len(secret_clean) % 8) % 8
    secret_bytes = base64.b32decode(secret_clean + ('=' * padding))
    
    # Pack counter as big-endian 8-byte integer
    msg = struct.pack(">Q", t)
    h = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
    
    # Dynamic truncation
    offset = h[-1] & 0x0F
    code_int = struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF
    code_6digit = code_int % 1000000
    return f"{code_6digit:06d}"

def verify_totp_code(secret: str, code: str, time_step: int = 30, window: int = 1) -> bool:
    """
    Verify TOTP code within time window tolerance (+- window steps).
    Uses constant time string comparison.
    """
    if not secret or not code:
        return False

    code_clean = code.strip().replace(' ', '')
    if len(code_clean) != 6 or not code_clean.isdigit():
        return False

    now = time.time()
    for w in range(-window, window + 1):
        expected_code = generate_totp_code(secret, time_step=time_step, for_time=now + (w * time_step))
        if hmac.compare_digest(code_clean, expected_code):
            return True
            
    return False

def get_totp_uri(username: str, secret: str, issuer: str = "GitPulse CMS") -> str:
    """Build standard otpauth:// URI for authenticator applications."""
    clean_user = username.strip()
    return f"otpauth://totp/{issuer}:{clean_user}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
