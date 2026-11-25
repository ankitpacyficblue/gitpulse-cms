"""Dashboard alerts, one row per problem per account: repeats raise the count.

Alert text must never contain tokens, secrets or message bodies."""
import os
import time
from datetime import datetime
from typing import Any, Dict, List

import database as db

TYPES = ("send_failed", "ai_failed", "handoff", "webhook_rejected", "token_invalid", "blog_failed", "worker_stalled")
STALL_SECONDS = 300


def raise_alert(account_id: str, kind: str, message: str, link: str = "", severity: str = "warning") -> None:
    if not account_id:
        return
    now = datetime.utcnow().isoformat()
    with db.get_connection() as conn:
        row = conn.execute("SELECT id FROM alerts WHERE account_id = ? AND type = ? AND link = ? AND resolved_at = ''",
                           (account_id, kind, link)).fetchone()
        if row:
            conn.execute("UPDATE alerts SET count = count + 1, last_seen = ?, message = ?, severity = ? WHERE id = ?",
                         (now, message[:300], severity, row["id"]))
        else:
            conn.execute("""INSERT INTO alerts (account_id, type, severity, message, link, count, first_seen, last_seen)
                            VALUES (?,?,?,?,?,1,?,?)""", (account_id, kind, severity, message[:300], link, now, now))
        conn.commit()


def list_alerts(account_id: str, include_resolved: bool = False) -> List[Dict[str, Any]]:
    q = "SELECT * FROM alerts WHERE account_id = ?" + ("" if include_resolved else " AND resolved_at = ''")
    with db.get_connection() as conn:
        out = [dict(r) for r in conn.execute(q + " ORDER BY last_seen DESC LIMIT 200", (account_id,)).fetchall()]
    # Computed on read: a worker that is not running cannot report itself.
    last = float(db.get_setting("worker_last_tick", "0") or 0)
    if not os.environ.get("CRON_SECRET"):
        out.insert(0, {"id": None, "type": "worker_setup", "severity": "info", "link": "", "count": 1,
                       "message": "Scheduled runs are not set up yet. Add CRON_SECRET in the hosting settings; until then "
                                  "queued messages go out while the dashboard is in use.",
                       "first_seen": None, "last_seen": None, "resolved_at": ""})
    elif time.time() - last > STALL_SECONDS:
        out.insert(0, {"id": None, "type": "worker_stalled", "severity": "error", "link": "", "count": 1,
                       "message": "The background worker has not run in the last 5 minutes. Queued messages and "
                                  "scheduled posts are waiting.",
                       "first_seen": None, "last_seen": datetime.utcfromtimestamp(last).isoformat() if last else None,
                       "resolved_at": ""})
    return out


def resolve(account_id: str, alert_id: int) -> bool:
    with db.get_connection() as conn:
        cur = conn.execute("UPDATE alerts SET resolved_at = ? WHERE id = ? AND account_id = ? AND resolved_at = ''",
                           (datetime.utcnow().isoformat(), alert_id, account_id))
        conn.commit()
        return cur.rowcount > 0


def open_counts() -> Dict[str, int]:
    with db.get_connection() as conn:
        rows = conn.execute("SELECT account_id, COUNT(*) AS n FROM alerts WHERE resolved_at = '' GROUP BY account_id").fetchall()
        return {r["account_id"]: r["n"] for r in rows}
