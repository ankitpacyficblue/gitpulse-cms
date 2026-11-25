"""Database-backed job queue. A serverless host has no long-running process, so due jobs run when
POST /api/internal/tick is called (the first attempt of an AI reply runs inside the webhook).

A job is claimed with a conditional UPDATE, so two ticks never run it twice. A job found still
'running' long after its claim is marked failed, never repeated: its message may already be sent."""
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import database as db
from engine import alerts

RETRY_DELAYS = (60, 300, 1800)      # after the 1st, 2nd and 3rd failed attempt
STALE_SECONDS = 600
TICK_BUDGET_SECONDS = 40
OPPORTUNISTIC_EVERY = 60      # seconds between queue drains triggered by normal requests
OPPORTUNISTIC_BUDGET = 3
_checked_at = 0.0
HANDLERS: Dict[str, Callable] = {}
ON_FAIL: Dict[str, Callable] = {}


class Retry(Exception):
    """The handler asks for another attempt later."""


class Defer(Exception):
    """Not an attempt: run again at `run_at` (for example, the daily cap is used up)."""
    def __init__(self, run_at: float):
        super().__init__("deferred")
        self.run_at = run_at


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def _now() -> str:
    return datetime.utcnow().isoformat()


def enqueue(account_id: str, kind: str, payload: Dict[str, Any], run_at: Optional[float] = None,
            dedupe_key: Optional[str] = None, attempts: int = 0) -> Optional[int]:
    """None when a job with this dedupe key already exists."""
    now = _now()
    with db.get_connection() as conn:
        cur = conn.execute("""INSERT INTO jobs (account_id, kind, payload, run_at, attempts, status, dedupe_key, created_at,
                              updated_at) VALUES (?,?,?,?,?,'pending',?,?,?) ON CONFLICT (dedupe_key) DO NOTHING""",
                           (account_id, kind, json.dumps(payload), run_at if run_at is not None else time.time(),
                            attempts, dedupe_key, now, now))
        conn.commit()
        return cur.lastrowid if cur.rowcount > 0 else None


def _set(job_id: int, status: str, error: str = "", run_at: Optional[float] = None, attempts: Optional[int] = None) -> None:
    with db.get_connection() as conn:
        conn.execute("UPDATE jobs SET status = ?, last_error = ?, run_at = COALESCE(?, run_at), "
                     "attempts = COALESCE(?, attempts), updated_at = ? WHERE id = ?",
                     (status, error[:300], run_at, attempts, _now(), job_id))
        conn.commit()


def _load(row) -> Dict[str, Any]:
    job = dict(row)
    job["payload"] = json.loads(job["payload"] or "{}")
    return job


def _fail(job: Dict[str, Any], error: str, attempts: int) -> None:
    _set(job["id"], "failed", error, attempts=attempts)
    hook = ON_FAIL.get(job["kind"])
    if hook:
        hook(job, error)
    else:
        alerts.raise_alert(job["account_id"], "send_failed", f"A background task failed: {error}", severity="error")


def run_job(job_id: int) -> str:
    """Claim and run one pending job. Returns done, retry, deferred, failed or skipped."""
    with db.get_connection() as conn:
        cur = conn.execute("UPDATE jobs SET status = 'running', locked_at = ?, updated_at = ? WHERE id = ? AND status = 'pending'",
                           (time.time(), _now(), job_id))
        claimed = cur.rowcount > 0
        conn.commit()
    if not claimed:
        return "skipped"
    with db.get_connection() as conn:
        job = _load(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    try:
        HANDLERS[job["kind"]](job)
    except Defer as d:
        _set(job_id, "pending", "deferred", run_at=d.run_at)
        return "deferred"
    except Retry as e:
        attempts = job["attempts"] + 1
        if attempts <= len(RETRY_DELAYS):
            _set(job_id, "pending", str(e), run_at=time.time() + RETRY_DELAYS[attempts - 1], attempts=attempts)
            return "retry"
        _fail(job, str(e), attempts)
        return "failed"
    except Exception as e:  # noqa: BLE001  one broken job must not stop the queue
        logging.getLogger("gitpulse").exception("job %s (%s) failed", job_id, job["kind"])
        _fail(job, type(e).__name__, job["attempts"] + 1)
        return "failed"
    _set(job_id, "done")
    return "done"


def maybe_tick() -> None:
    """Drain the message queue on a normal request, because a daily cron alone is too slow for retries.
    At most once a minute across all instances (compare-and-set on the last tick time). Never writes
    AI blog drafts (too slow for someone waiting) and never raises. On for Vercel, or OPPORTUNISTIC_TICK=1."""
    global _checked_at
    if not (os.environ.get("VERCEL") or os.environ.get("OPPORTUNISTIC_TICK") == "1"):
        return
    now = time.time()
    if now - _checked_at < OPPORTUNISTIC_EVERY:
        return
    _checked_at = now
    try:
        last = db.get_setting("worker_last_tick", "")
        if last and now - float(last) < OPPORTUNISTIC_EVERY:
            return
        if last:
            with db.get_connection() as conn:
                won = conn.execute("UPDATE settings SET value = ? WHERE key = 'worker_last_tick' AND value = ?",
                                   (str(now), last)).rowcount == 1
                conn.commit()
            if not won:
                return
        tick(budget=OPPORTUNISTIC_BUDGET, limit=10, blogs=False)
    except Exception:  # noqa: BLE001  the request that triggered this must not fail because of it
        logging.getLogger("gitpulse").exception("opportunistic tick failed")


def tick(budget: float = TICK_BUDGET_SECONDS, limit: int = 100, blogs: bool = True) -> Dict[str, int]:
    from engine import messaging, assistant, blog_plan  # noqa: F401  (registers the handlers)
    started = time.time()
    db.set_setting("worker_last_tick", str(started))
    with db.get_connection() as conn:
        stale = [_load(r) for r in conn.execute("SELECT * FROM jobs WHERE status = 'running' AND locked_at < ?",
                                                (started - STALE_SECONDS,)).fetchall()]
    for job in stale:
        _fail(job, "Interrupted; not repeated in case it already went out.", job["attempts"] + 1)
    # Publishing approved posts is quick enough for any tick; writing a draft with AI is not.
    blog_plan.schedule_due()
    if blogs:
        blog_plan.schedule_drafts()
    only = "" if blogs else " AND kind != 'plan_draft'"
    with db.get_connection() as conn:
        due = [r["id"] for r in conn.execute(f"SELECT id FROM jobs WHERE status = 'pending' AND run_at <= ?{only} "
                                             "ORDER BY run_at, id LIMIT ?", (time.time(), limit)).fetchall()]
    counts = {"done": 0, "retry": 0, "deferred": 0, "failed": 0, "skipped": 0}
    for job_id in due:
        if time.time() - started > budget:
            break
        counts[run_job(job_id)] += 1
    return counts
