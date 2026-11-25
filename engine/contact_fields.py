"""Per-account contact fields. Values live on the contact (contacts.custom, JSON keyed by field id).
Deleting a field archives it: hidden everywhere, values kept."""
import json
import math
from datetime import date, datetime
from typing import Any, Dict, List

import database as db

TYPES = ("text", "number", "date", "select")
MAX_FIELDS = 30


class FieldError(Exception):
    def __init__(self, status: int, code: str, message: str = ""):
        super().__init__(message or code)
        self.status, self.code, self.message = status, code, message


def list_fields(account_id: str) -> List[Dict[str, Any]]:
    with db.get_connection() as conn:
        rows = conn.execute("SELECT id, name, type, options FROM contact_fields WHERE account_id = ? AND archived = 0 "
                            "ORDER BY id", (account_id,)).fetchall()
    return [dict(r, options=json.loads(r["options"])) for r in (dict(x) for x in rows)]


def _field(account_id: str, field_id: Any) -> Dict[str, Any]:
    for f in list_fields(account_id):
        if str(f["id"]) == str(field_id):
            return f
    raise FieldError(404, "field_not_found", "No such contact field.")


def _name(account_id: str, value: Any, own_id: int = 0) -> str:
    name = str(value or "").strip()[:60]
    if not name:
        raise FieldError(400, "name_required", "Give the field a name.")
    if any(f["name"].lower() == name.lower() and f["id"] != own_id for f in list_fields(account_id)):
        raise FieldError(409, "duplicate_name", "A field with this name already exists.")
    return name


def _options(kind: str, value: Any) -> List[str]:
    if kind != "select":
        return []
    options = list(dict.fromkeys(str(o).strip()[:100] for o in value if str(o).strip())) if isinstance(value, list) else []
    if not options:
        raise FieldError(400, "options_required", "A choice field needs at least one option.")
    return options[:100]


def create(account_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(data.get("type") or "")
    if kind not in TYPES:
        raise FieldError(400, "invalid_type", "Type must be text, number, date or select.")
    name, options = _name(account_id, data.get("name")), _options(kind, data.get("options"))
    if len(list_fields(account_id)) >= MAX_FIELDS:
        raise FieldError(409, "too_many_fields", f"An account can have {MAX_FIELDS} fields.")
    with db.get_connection() as conn:
        field_id = conn.execute("INSERT INTO contact_fields (account_id, name, type, options, archived, created_at) "
                                "VALUES (?,?,?,?,0,?)", (account_id, name, kind, json.dumps(options),
                                                         datetime.utcnow().isoformat())).lastrowid
        conn.commit()
    return {"id": field_id, "name": name, "type": kind, "options": options}


def update(account_id: str, field_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    field = _field(account_id, field_id)
    kind = str(data.get("type") or field["type"])
    if kind not in TYPES:
        raise FieldError(400, "invalid_type", "Type must be text, number, date or select.")
    if kind != field["type"] and _has_values(account_id, field["id"]):
        raise FieldError(409, "type_in_use", "The type cannot change once contacts have values.")
    name = _name(account_id, data.get("name", field["name"]), field["id"])
    options = _options(kind, data.get("options", field["options"]))
    with db.get_connection() as conn:
        conn.execute("UPDATE contact_fields SET name = ?, type = ?, options = ? WHERE id = ? AND account_id = ?",
                     (name, kind, json.dumps(options), field["id"], account_id))
        conn.commit()
    return {"id": field["id"], "name": name, "type": kind, "options": options}


def archive(account_id: str, field_id: int) -> None:
    field = _field(account_id, field_id)
    with db.get_connection() as conn:
        conn.execute("UPDATE contact_fields SET archived = 1 WHERE id = ? AND account_id = ?", (field["id"], account_id))
        conn.commit()


def _values(raw: Any) -> Dict[str, Any]:
    try:
        out = json.loads(raw or "{}") if isinstance(raw, str) else raw
        return out if isinstance(out, dict) else {}
    except ValueError:
        return {}


def _has_values(account_id: str, field_id: int) -> bool:
    with db.get_connection() as conn:
        rows = conn.execute("SELECT custom FROM contacts WHERE account_id = ? AND custom != '{}'", (account_id,)).fetchall()
    return any(str(field_id) in _values(r["custom"]) for r in rows)


def _coerce(field: Dict[str, Any], value: Any):
    bad = FieldError(400, "invalid_value", f"'{field['name']}' needs a valid {field['type']} value.")
    text = str(value).strip()
    if field["type"] == "number":
        try:
            number = float(text)
        except ValueError:
            raise bad
        if not math.isfinite(number):
            raise bad
        return int(number) if number.is_integer() else number
    if field["type"] == "date":
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            raise bad
    if field["type"] == "select":
        if text not in field["options"]:
            raise bad
        return text
    return text[:500]


def validate(account_id: str, custom: Any) -> Dict[str, Any]:
    """Partial change set. None means "clear this value". Check everything before anything is saved."""
    if custom in (None, ""):
        return {}
    if not isinstance(custom, dict):
        raise FieldError(400, "invalid_value", "custom must be an object keyed by field id.")
    out = {}
    for key, value in custom.items():
        field = _field(account_id, key)
        out[str(field["id"])] = None if value in (None, "") else _coerce(field, value)
    return out


def save(account_id: str, contact_id: int, changes: Dict[str, Any]) -> bool:
    with db.get_connection() as conn:
        row = conn.execute("SELECT custom FROM contacts WHERE id = ? AND account_id = ?", (contact_id, account_id)).fetchone()
        if not row:
            return False
        values = _values(row["custom"])
        for key, value in changes.items():
            if value is None:
                values.pop(key, None)
            else:
                values[key] = value
        conn.execute("UPDATE contacts SET custom = ? WHERE id = ? AND account_id = ?",
                     (json.dumps(values), contact_id, account_id))
        conn.commit()
    return True


def present(account_id: str, contacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """custom as an object holding only fields that still exist."""
    live = {str(f["id"]) for f in list_fields(account_id)}
    return [dict(c, custom={k: v for k, v in _values(c.get("custom")).items() if k in live}) for c in contacts]


def filter_contacts(account_id: str, contacts: List[Dict[str, Any]], query: Dict[str, str]) -> List[Dict[str, Any]]:
    """?cf_<id>=value, and cf_<id>_min / _max for numbers and dates. Several filters combine."""
    for key, raw in query.items():
        if not key.startswith("cf_") or raw == "":
            continue
        ident, _, bound = key[3:].partition("_")
        field = _field(account_id, ident)
        if bound and (bound not in ("min", "max") or field["type"] not in ("number", "date")):
            raise FieldError(400, "invalid_filter", f"'{field['name']}' cannot be filtered that way.")
        wanted = _coerce(field, raw)
        kept = []
        for c in contacts:
            have = c["custom"].get(str(field["id"]))
            if have is None:
                continue
            if bound == "min":
                match = have >= wanted
            elif bound == "max":
                match = have <= wanted
            elif field["type"] == "text":
                match = wanted.lower() in have.lower()
            else:
                match = have == wanted
            if match:
                kept.append(c)
        contacts = kept
    return contacts
