"""
GitPulse CMS - Vercel Serverless Entrypoint
Exports both WSGI `app` and `handler` for `@vercel/python` serverless runtime.
Routes all web dashboard, API, static asset, and webhook requests.
"""

import sys
import os
import json
import mimetypes
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from http.server import BaseHTTPRequestHandler
import io

# Add parent directory to sys.path so modules resolve on Vercel
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from database import init_db, seed_demo_data
from engine.auth import init_default_admin, validate_session
from server.routes_web import render_dashboard_html, render_login_html
from server.routes_api import handle_api_request
from server.routes_public import handle_public_request
from server.routes_webhook import handle_github_webhook

# Initialize DB on cold start
try:
    init_db()
    seed_demo_data()
    init_default_admin()
except Exception as e:
    pass

STATIC_DIR = ROOT_DIR / "static"

def get_static_asset(rel_path: str):
    rel_clean = rel_path.lstrip("/")
    candidates = [
        (STATIC_DIR / rel_clean).resolve(),
        (ROOT_DIR / "public" / "static" / rel_clean).resolve(),
        (Path.cwd() / "static" / rel_clean).resolve(),
        (Path.cwd() / "public" / "static" / rel_clean).resolve(),
        (Path("/var/task/static") / rel_clean).resolve(),
        (Path("/var/task/public/static") / rel_clean).resolve()
    ]
    for p in candidates:
        if p.is_file():
            mime, _ = mimetypes.guess_type(str(p))
            try:
                with open(p, "rb") as f:
                    return f.read(), (mime or "application/octet-stream")
            except Exception:
                pass

    # In-memory fail-safe fallback
    try:
        from server.routes_web import _get_embedded_css, _get_embedded_js
        if rel_clean.endswith(".css"):
            css = _get_embedded_css()
            if css:
                return css.encode("utf-8"), "text/css; charset=utf-8"
        if rel_clean.endswith(".js"):
            js = _get_embedded_js()
            if js:
                return js.encode("utf-8"), "application/javascript; charset=utf-8"
    except Exception:
        pass
    return None, None

class handler(BaseHTTPRequestHandler):
    """BaseHTTPRequestHandler interface supported by @vercel/python."""
    
    def log_message(self, format, *args):
        return

    def _get_client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def _get_session_token(self):
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[len("Bearer "):].strip()
        cookie_header = self.headers.get("Cookie", "")
        if "session_token=" in cookie_header:
            for part in cookie_header.split(";"):
                part = part.strip()
                if part.startswith("session_token="):
                    return part[len("session_token="):]
        return None

    def _get_authenticated_user(self):
        token = self._get_session_token()
        if not token:
            return None
        return validate_session(token)

    def _set_headers(self, status_code=200, content_type="application/json", set_cookie=None, location=None):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        if location:
            self.send_header("Location", location)
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(204, "text/plain")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        current_user = self._get_authenticated_user()

        if path == "/login":
            if current_user:
                self._set_headers(302, "text/plain", location="/")
                return
            html = render_login_html()
            self._set_headers(200, "text/html; charset=utf-8")
            self.wfile.write(html.encode("utf-8"))
            return

        if path in ("/", "/index.html", "/dashboard"):
            if not current_user:
                self._set_headers(302, "text/plain", location="/login")
                return
            html = render_dashboard_html()
            self._set_headers(200, "text/html; charset=utf-8")
            self.wfile.write(html.encode("utf-8"))
            return

        if path.startswith("/static/"):
            rel_path = path[len("/static/"):].lstrip("/")
            body_bytes, mime = get_static_asset(rel_path)
            if body_bytes is not None:
                self._set_headers(200, mime or "application/octet-stream")
                self.wfile.write(body_bytes)
                return
            else:
                self._set_headers(404, "text/plain")
                self.wfile.write(b"404 Not Found")
                return

        if path.startswith("/api/public/"):
            client_ip = self._get_client_ip()
            code, ctype, resp_body = handle_public_request(path, query, client_ip)
            self._set_headers(code, ctype)
            self.wfile.write(resp_body.encode("utf-8") if isinstance(resp_body, str) else resp_body)
            return

        if path.startswith("/api/"):
            client_ip = self._get_client_ip()
            user_agent = self.headers.get("User-Agent", "")
            code, resp = handle_api_request("GET", path, query, None, current_user, client_ip, user_agent)
            self._set_headers(code, "application/json")
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self._set_headers(404, "application/json")
        self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

    def do_POST(self):
        self._handle_body("POST")

    def do_PUT(self):
        self._handle_body("PUT")

    def do_DELETE(self):
        self._handle_body("DELETE")

    def _handle_body(self, method):
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

        if path == "/api/webhook/github" and method == "POST":
            event_type = self.headers.get("X-GitHub-Event", "ping")
            signature = self.headers.get("X-Hub-Signature-256", "")
            code, resp = handle_github_webhook(event_type, signature, raw_body_bytes, body_data or {})
            self._set_headers(code, "application/json")
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path.startswith("/api/"):
            code, resp = handle_api_request(method, path, query, body_data, current_user, client_ip, user_agent)
            set_cookie = None
            if path == "/api/auth/login" and code == 200 and "token" in resp:
                set_cookie = f"session_token={resp['token']}; Path=/; HttpOnly; SameSite=Strict; Max-Age=172800"
            if path == "/api/auth/logout":
                set_cookie = "session_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT"

            self._set_headers(code, "application/json", set_cookie=set_cookie)
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self._set_headers(404, "application/json")
        self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))

# WSGI Application compatibility
def app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    query_string = environ.get("QUERY_STRING", "")
    query = {k: v[0] for k, v in parse_qs(query_string).items()}

    # Cookie & Auth
    http_cookie = environ.get("HTTP_COOKIE", "")
    token = None
    if "session_token=" in http_cookie:
        for part in http_cookie.split(";"):
            part = part.strip()
            if part.startswith("session_token="):
                token = part[len("session_token="):]
    if not token and "HTTP_AUTHORIZATION" in environ:
        auth_hdr = environ["HTTP_AUTHORIZATION"]
        if auth_hdr.startswith("Bearer "):
            token = auth_hdr[len("Bearer "):].strip()

    current_user = validate_session(token) if token else None
    client_ip = environ.get("HTTP_X_FORWARDED_FOR", environ.get("REMOTE_ADDR", "127.0.0.1")).split(",")[0].strip()
    user_agent = environ.get("HTTP_USER_AGENT", "")

    headers = [
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type, Authorization")
    ]

    if method == "OPTIONS":
        headers.append(("Content-Type", "text/plain"))
        start_response("204 No Content", headers)
        return [b""]

    if method == "GET":
        if path == "/login":
            if current_user:
                headers.append(("Location", "/"))
                start_response("302 Found", headers)
                return [b""]
            html = render_login_html()
            headers.append(("Content-Type", "text/html; charset=utf-8"))
            start_response("200 OK", headers)
            return [html.encode("utf-8")]

        if path in ("/", "/index.html", "/dashboard"):
            if not current_user:
                headers.append(("Location", "/login"))
                start_response("302 Found", headers)
                return [b""]
            html = render_dashboard_html()
            headers.append(("Content-Type", "text/html; charset=utf-8"))
            start_response("200 OK", headers)
            return [html.encode("utf-8")]

        if path.startswith("/static/"):
            rel_path = path[len("/static/"):].lstrip("/")
            body_bytes, mime = get_static_asset(rel_path)
            if body_bytes is not None:
                headers.append(("Content-Type", mime or "application/octet-stream"))
                start_response("200 OK", headers)
                return [body_bytes]
            headers.append(("Content-Type", "text/plain"))
            start_response("404 Not Found", headers)
            return [b"404 Not Found"]

        if path.startswith("/api/public/"):
            code, ctype, resp_body = handle_public_request(path, query, client_ip)
            headers.append(("Content-Type", ctype))
            status_str = f"{code} OK" if code == 200 else f"{code} Error"
            start_response(status_str, headers)
            return [resp_body.encode("utf-8") if isinstance(resp_body, str) else resp_body]

        if path.startswith("/api/"):
            code, resp = handle_api_request("GET", path, query, None, current_user, client_ip, user_agent)
            headers.append(("Content-Type", "application/json"))
            status_str = f"{code} OK" if code == 200 else f"{code} Error"
            start_response(status_str, headers)
            return [json.dumps(resp).encode("utf-8")]

    # POST, PUT, DELETE with body
    try:
        content_length = int(environ.get("CONTENT_LENGTH", 0) or 0)
    except ValueError:
        content_length = 0

    body_bytes = environ["wsgi.input"].read(content_length) if content_length > 0 else b""
    body_data = None
    if body_bytes:
        try:
            body_data = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body_data = {}

    if path == "/api/webhook/github" and method == "POST":
        event_type = environ.get("HTTP_X_GITHUB_EVENT", "ping")
        signature = environ.get("HTTP_X_HUB_SIGNATURE_256", "")
        code, resp = handle_github_webhook(event_type, signature, body_bytes, body_data or {})
        headers.append(("Content-Type", "application/json"))
        start_response(f"{code} OK" if code == 200 else f"{code} Error", headers)
        return [json.dumps(resp).encode("utf-8")]

    if path.startswith("/api/"):
        code, resp = handle_api_request(method, path, query, body_data, current_user, client_ip, user_agent)
        headers.append(("Content-Type", "application/json"))
        if path == "/api/auth/login" and code == 200 and "token" in resp:
            headers.append(("Set-Cookie", f"session_token={resp['token']}; Path=/; HttpOnly; SameSite=Strict; Max-Age=172800"))
        if path == "/api/auth/logout":
            headers.append(("Set-Cookie", "session_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT"))

        status_str = f"{code} OK" if code == 200 else f"{code} Error"
        start_response(status_str, headers)
        return [json.dumps(resp).encode("utf-8")]

    headers.append(("Content-Type", "application/json"))
    start_response("404 Not Found", headers)
    return [json.dumps({"error": "Endpoint not found"}).encode("utf-8")]
