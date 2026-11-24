"""
GitPulse CMS - HTTP Server Implementation
Lightweight, zero-dependency WSGI/HTTP server handling JSON REST APIs,
cookie-based sessions, auth guards, static asset delivery, and the interactive dashboard.
"""

import os
import json
import mimetypes
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from typing import Dict, Any, Optional

from config import BASE_DIR
from server.routes_api import handle_api_request
from server.routes_web import render_dashboard_html, render_login_html
from server.routes_public import handle_public_request
from server.routes_webhook import handle_github_webhook
from server.routes_whatsapp import handle_whatsapp_webhook_get, handle_whatsapp_webhook_post
from engine.auth import validate_session

STATIC_DIR = BASE_DIR / "static"

from server.security import SECURITY_HEADERS


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class GitPulseHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy standard request logging
        return

    def _get_client_ip(self) -> str:
        """Extract client IP handling proxies."""
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def _get_session_token(self) -> Optional[str]:
        """Extract session token from Cookie or Authorization header."""
        # 1. Bearer Token Header (case-insensitive)
        auth_header = self.headers.get("Authorization") or self.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()

        # 2. Cookie Header (session_token=...)
        cookie_header = self.headers.get("Cookie") or self.headers.get("cookie") or ""
        if "session_token=" in cookie_header:
            for part in cookie_header.split(";"):
                part = part.strip()
                if part.startswith("session_token="):
                    return part[len("session_token="):]
        return None

    def _get_authenticated_user(self) -> Optional[Dict[str, Any]]:
        """Validate token and return user if active."""
        token = self._get_session_token()
        if not token:
            return None
        return validate_session(token)

    def _set_headers(
        self,
        status_code: int = 200,
        content_type: str = "application/json",
        set_cookie: Optional[str] = None,
        location: Optional[str] = None
    ):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        for k, v in SECURITY_HEADERS:
            self.send_header(k, v)
        if getattr(self, "path", "").split("?")[0].startswith("/api/public/"):
            # Read-only public blog data may be embedded on client sites; everything else is same-origin.
            self.send_header("Access-Control-Allow-Origin", "*")
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        if location:
            self.send_header("Location", location)
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(204, "text/plain")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        current_user = self._get_authenticated_user()

        # 1. Login Page
        if path == "/login":
            if current_user:
                # Already authenticated, redirect to main dashboard
                self._set_headers(302, "text/plain", location="/")
                return
            html = render_login_html()
            self._set_headers(200, "text/html; charset=utf-8")
            self.wfile.write(html.encode("utf-8"))
            return

        # 2. Root Dashboard (Protected)
        if path in ("/", "/index.html", "/dashboard"):
            if not current_user:
                # Unauthenticated user visiting dashboard -> redirect to /login
                self._set_headers(302, "text/plain", location="/login")
                return
            html = render_dashboard_html()
            self._set_headers(200, "text/html; charset=utf-8")
            self.wfile.write(html.encode("utf-8"))
            return

        # 3. Static Assets (Public)
        if path.startswith("/static/"):
            rel_path = path[len("/static/"):].lstrip("/")
            file_path = (STATIC_DIR / rel_path).resolve()

            # Security check: prevent directory traversal
            if STATIC_DIR in file_path.parents and file_path.is_file():
                mime, _ = mimetypes.guess_type(str(file_path))
                self._set_headers(200, mime or "application/octet-stream")
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self._set_headers(404, "text/plain")
                self.wfile.write(b"404 Not Found")
                return

        # WhatsApp Meta Webhook Handshake (GET)
        if path == "/api/webhook/whatsapp":
            code, ctype, resp_body = handle_whatsapp_webhook_get(query)
            self._set_headers(code, ctype)
            self.wfile.write(resp_body.encode("utf-8") if isinstance(resp_body, str) else resp_body)
            return

        # 4. Public Headless Content API (CORS enabled, no auth required)
        if path.startswith("/api/public/"):
            client_ip = self._get_client_ip()
            code, ctype, resp_body = handle_public_request(path, query, client_ip)
            self._set_headers(code, ctype)
            self.wfile.write(resp_body.encode("utf-8") if isinstance(resp_body, str) else resp_body)
            return

        # 5. Protected Admin API Routes
        if path.startswith("/api/"):
            client_ip = self._get_client_ip()
            user_agent = self.headers.get("User-Agent", "")
            status_code, resp_data = handle_api_request("GET", path, query, None, current_user, client_ip, user_agent, headers=dict(self.headers))
            self._set_headers(status_code, "application/json")
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
            return

        # Fallback 404
        self._set_headers(404, "application/json")
        self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

    def do_POST(self):
        self._handle_with_body("POST")

    def do_PUT(self):
        self._handle_with_body("PUT")

    def do_PATCH(self):
        self._handle_with_body("PATCH")

    def do_DELETE(self):
        self._handle_with_body("DELETE")

    def _handle_with_body(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        current_user = self._get_authenticated_user()
        client_ip = self._get_client_ip()
        user_agent = self.headers.get("User-Agent", "")

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body_bytes = b""
        body_data = None
        if content_length > 0:
            try:
                raw_body_bytes = self.rfile.read(content_length)
                raw_body = raw_body_bytes.decode("utf-8")
                body_data = json.loads(raw_body) if raw_body else {}
            except Exception:
                body_data = {}

        # WhatsApp Webhook Receiver (POST)
        if path == "/api/webhook/whatsapp" and method == "POST":
            code, resp = handle_whatsapp_webhook_post(raw_body_bytes, self.headers.get("X-Hub-Signature-256", ""), body_data or {})
            self._set_headers(code, "application/json")
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        # GitHub Bi-Directional Webhook Receiver
        if path == "/api/webhook/github" and method == "POST":
            event_type = self.headers.get("X-GitHub-Event", "ping")
            signature = self.headers.get("X-Hub-Signature-256", "")
            code, resp = handle_github_webhook(event_type, signature, raw_body_bytes, body_data or {})
            self._set_headers(code, "application/json")
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path.startswith("/api/"):
            status_code, resp_data = handle_api_request(method, path, query, body_data, current_user, client_ip, user_agent, headers=dict(self.headers))

            # Handle Cookie setting on successful login
            set_cookie = None
            if path == "/api/auth/login" and status_code == 200 and "token" in resp_data:
                token = resp_data["token"]
                is_https = (self.headers.get("X-Forwarded-Proto") == "https") or bool(os.environ.get("VERCEL"))
                secure_flag = "; Secure" if is_https else ""
                set_cookie = f"session_token={token}; Path=/; SameSite=Lax{secure_flag}; Max-Age=172800"

            # Handle Cookie removal on logout
            if path == "/api/auth/logout":
                set_cookie = "session_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax"

            self._set_headers(status_code, "application/json", set_cookie=set_cookie)
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
            return

        self._set_headers(404, "application/json")
        self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))

def run_server(host: str = "0.0.0.0", port: int = 8420):
    server = ThreadedHTTPServer((host, port), GitPulseHTTPHandler)
    print(f"🚀 GitPulse CMS Web Dashboard running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()
