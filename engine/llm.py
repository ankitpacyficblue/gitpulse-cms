"""Small JSON-only LLM call. Raises LLMError; there is never a canned fallback reply.

Keys are sent in headers, never in a URL, and never logged or put in an error."""
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

import crm_store as cs
import database as db

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class LLMError(Exception):
    pass


def resolve(account_id: str) -> Tuple[str, str]:
    """The account's own provider and key win; otherwise the platform's."""
    from config import DEFAULT_AI_PROVIDER, DEFAULT_GEMINI_API_KEY, DEFAULT_OPENAI_API_KEY
    provider, key = cs.get_account_ai(account_id)
    if provider and key:
        return provider, key
    provider = provider or db.get_setting("ai_provider", DEFAULT_AI_PROVIDER)
    key = db.get_setting(f"{provider}_api_key", "") or {"gemini": DEFAULT_GEMINI_API_KEY,
                                                        "openai": DEFAULT_OPENAI_API_KEY}.get(provider, "")
    return provider, key


def _post(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=dict(headers, **{"Content-Type": "application/json"}), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMError(f"AI provider returned HTTP {e.code}")
    except Exception as e:
        raise LLMError(f"AI provider unreachable ({type(e).__name__})")


def parse_json(text: str) -> Dict[str, Any]:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip()).strip()
    try:
        out = json.loads(text)
    except ValueError:
        raise LLMError("AI reply was not valid JSON")
    if not isinstance(out, dict):
        raise LLMError("AI reply was not a JSON object")
    return out


def generate_json(account_id: str, system: str, turns: List[Tuple[str, str]], timeout: float = 10) -> Dict[str, Any]:
    """turns: [("customer"|"business", text), ...], oldest first."""
    provider, key = resolve(account_id)
    if not key:
        raise LLMError("No AI key is configured")
    if provider == "gemini":
        data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                     {"system_instruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user" if who == "customer" else "model", "parts": [{"text": t}]}
                                   for who, t in turns],
                      "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2}},
                     {"x-goog-api-key": key}, timeout)
        try:
            return parse_json(data["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, TypeError):
            raise LLMError("AI provider returned no answer")
    if provider == "openai":
        data = _post("https://api.openai.com/v1/chat/completions",
                     {"model": OPENAI_MODEL, "temperature": 0.2, "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": system}] +
                                  [{"role": "user" if who == "customer" else "assistant", "content": t} for who, t in turns]},
                     {"Authorization": f"Bearer {key}"}, timeout)
        try:
            return parse_json(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise LLMError("AI provider returned no answer")
    raise LLMError("Unsupported AI provider")
