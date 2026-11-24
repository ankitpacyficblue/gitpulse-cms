"""
GitPulse CMS - Supabase PostgreSQL REST Client
Zero-dependency Python client communicating directly with Supabase PostgREST API.
Enables cloud data persistence across Vercel serverless invocations.
"""

import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Tuple

class SupabaseTableQuery:
    def __init__(self, client: 'SupabaseClient', table_name: str):
        self.client = client
        self.table_name = table_name

    def select(self, columns: str = "*", filters: Optional[Dict[str, str]] = None, order: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        query_parts = [f"select={columns}"]
        if filters:
            for col, val in filters.items():
                query_parts.append(f"{col}={val}")
        if order:
            query_parts.append(f"order={order}")
        if limit:
            query_parts.append(f"limit={limit}")

        query_str = "&".join(query_parts)
        url = f"{self.client.base_url}/rest/v1/{self.table_name}?{query_str}"
        headers = self.client._get_headers()
        req = urllib.request.Request(url, headers=headers, method="GET")

        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def insert(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = f"{self.client.base_url}/rest/v1/{self.table_name}"
        headers = self.client._get_headers(prefer="return=representation")
        req = urllib.request.Request(
            url,
            data=json.dumps(record).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data[0] if isinstance(data, list) and data else data

    def update(self, record: Dict[str, Any], filters: Dict[str, str]) -> List[Dict[str, Any]]:
        query_parts = []
        for col, val in filters.items():
            query_parts.append(f"{col}={val}")
        url = f"{self.client.base_url}/rest/v1/{self.table_name}?{'&'.join(query_parts)}"
        headers = self.client._get_headers(prefer="return=representation")
        req = urllib.request.Request(
            url,
            data=json.dumps(record).encode("utf-8"),
            headers=headers,
            method="PATCH"
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def delete(self, filters: Dict[str, str]) -> bool:
        query_parts = []
        for col, val in filters.items():
            query_parts.append(f"{col}={val}")
        url = f"{self.client.base_url}/rest/v1/{self.table_name}?{'&'.join(query_parts)}"
        headers = self.client._get_headers()
        req = urllib.request.Request(url, headers=headers, method="DELETE")
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status in (200, 204)

class SupabaseClient:
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        # Default to linked project ref if not explicitly specified
        self.base_url = (url or os.environ.get("SUPABASE_URL") or "https://suvmyyonlqyipzgnmony.supabase.co").rstrip("/")
        self.key = (key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()

    def is_configured(self) -> bool:
        return bool(self.base_url and self.key)

    def _get_headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "User-Agent": "GitPulse-CMS-Supabase/1.0"
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def table(self, table_name: str) -> SupabaseTableQuery:
        return SupabaseTableQuery(self, table_name)

    def test_connection(self) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "Supabase API key is not configured."
        url = f"{self.base_url}/rest/v1/projects?select=count"
        headers = self._get_headers(prefer="count=exact")
        headers["Range-Unit"] = "items"
        headers["Range"] = "0-0"
        try:
            req = urllib.request.Request(url, headers=headers, method="HEAD")
            with urllib.request.urlopen(req, timeout=8) as resp:
                return True, f"Connected to Supabase ({self.base_url}). Status: {resp.status}"
        except urllib.error.HTTPError as e:
            if e.code == 401 or e.code == 403:
                return False, f"Supabase Authentication error (HTTP {e.code}). Please verify your service_role or anon key."
            return True, f"Supabase reachable (HTTP {e.code})"
        except Exception as e:
            return False, f"Supabase connection error: {str(e)}"
