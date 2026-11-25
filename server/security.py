"""Security response headers shared by the dev server and the Vercel entry point."""

# The UI uses inline scripts/styles plus Tailwind's CDN and Google Fonts; connections stay same-origin.
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)

import os
from urllib.parse import urlparse

# Media previews come from storage by signed link, and the browser uploads straight to it.
_media = urlparse(os.environ.get("MEDIA_SUPABASE_URL", ""))
if _media.scheme == "https" and _media.netloc:
    CSP = CSP.replace("connect-src 'self'", f"connect-src 'self' https://{_media.netloc}")
    CSP += f"; media-src 'self' https://{_media.netloc}"

if os.environ.get("VERCEL_ENV") == "preview":
    # The Vercel toolbar (comments/preview bar) only exists on preview deployments; production never gets this.
    CSP = (CSP.replace("script-src 'self'", "script-src 'self' https://vercel.live")
              .replace("connect-src 'self'", "connect-src 'self' https://vercel.live wss://ws-us3.pusher.com https://sockjs-us3.pusher.com")
              .replace("style-src 'self'", "style-src 'self' https://vercel.live")
              .replace("font-src 'self'", "font-src 'self' https://vercel.live https://assets.vercel.com")
              .replace("img-src 'self'", "img-src 'self' https://vercel.live https://vercel.com")
              .replace("frame-ancestors 'none'", "frame-src https://vercel.live; frame-ancestors 'none'"))

SECURITY_HEADERS = [
    ("Content-Security-Policy", CSP),
    ("X-Frame-Options", "DENY"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
]
