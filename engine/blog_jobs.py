"""Daily blog run per active project, as a queued job: one per project per local day, however often
the tick runs. A run that fails is reported on the dashboard and not repeated, so nothing posts twice."""
from datetime import datetime, timezone
from typing import Any, Dict

import database as db
from engine import alerts, jobs
from engine.messaging import IST


def _local_date(utc_iso: str) -> str:
    if not utc_iso:
        return ""
    return datetime.fromisoformat(utc_iso).replace(tzinfo=timezone.utc).astimezone(IST).strftime("%Y-%m-%d")


def schedule_due() -> int:
    """Queue today's run for each project whose publish time (account time zone) has passed."""
    now = datetime.now(IST)
    today, clock = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    with db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT p.id, p.account_id, p.publish_time, p.last_run_at FROM projects p JOIN accounts a ON a.id = p.account_id "
            "WHERE p.is_active = 1 AND a.status = 'active'").fetchall()]
    queued = 0
    for p in rows:
        if clock >= (p["publish_time"] or "09:00").strip().zfill(5) and _local_date(p["last_run_at"] or "") != today:
            if jobs.enqueue(p["account_id"], "blog_run", {"project_id": p["id"]}, dedupe_key=f"blog:{p['id']}:{today}"):
                queued += 1
    return queued


def _failed(account_id: str, project_id: int, reason: str) -> None:
    alerts.raise_alert(account_id, "blog_failed", f"The daily blog post was not published: {reason}",
                       link=f"project:{project_id}", severity="error")


@jobs.handler("blog_run")
def _blog_run(job: Dict[str, Any]) -> None:
    from engine.pipeline import run_publication_pipeline
    account_id, project_id = job["account_id"], job["payload"]["project_id"]
    project = db.get_project(project_id)
    if not project or project.get("account_id") != account_id or not project.get("is_active"):
        return
    try:
        result = run_publication_pipeline(project_id)
    except Exception as e:  # noqa: BLE001
        from engine.ai_generator import GenerationError
        _failed(account_id, project_id, str(e) if isinstance(e, GenerationError) else type(e).__name__)
        db.update_project_last_run(project_id)
        return
    if result.get("blocked"):
        _failed(account_id, project_id, f"the draft is held for review ({result['blocked']})")
    elif not result.get("success"):
        _failed(account_id, project_id, str(result.get("error", "publishing error"))[:200])
        db.update_project_last_run(project_id)


jobs.ON_FAIL["blog_run"] = lambda job, error: _failed(job["account_id"], job["payload"].get("project_id"), error)
