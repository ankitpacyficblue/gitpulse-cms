"""
GitPulse CMS - Background Publishing Scheduler
Monitors publishing schedules, executes daily content runs,
and provides programmatic/API on-demand triggers.
"""

import time
import threading
from datetime import datetime
from typing import Optional
from database import list_all_projects, log_event
from engine.pipeline import run_publication_pipeline

class CronWorker:
    def __init__(self, check_interval_seconds: int = 45):
        self.check_interval = check_interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start scheduler daemon in background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="GitPulse-Scheduler", daemon=True)
        self._thread.start()
        log_event("Daily publishing scheduler started.", "INFO")

    def stop(self):
        """Stop scheduler daemon."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        log_event("Daily publishing scheduler stopped.", "INFO")

    def is_alive(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def _loop(self):
        while self._running:
            try:
                self._check_and_execute_schedules()
            except Exception as e:
                log_event(f"Scheduler tick exception: {str(e)}", "ERROR")
            
            # Sleep in small slices to allow fast shutdown
            for _ in range(self.check_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _check_and_execute_schedules(self):
        """Examine active projects and trigger publishing when scheduled."""
        now_dt = datetime.utcnow()
        current_time_str = now_dt.strftime("%H:%M")
        today_date_str = now_dt.strftime("%Y-%m-%d")

        projects = list_all_projects()
        for p in projects:
            if not p.get("is_active"):
                continue

            scheduled_time = p.get("publish_time", "09:00").strip()
            last_run = p.get("last_run_at") or ""
            already_ran_today = last_run.startswith(today_date_str)

            # Trigger condition: time matches and hasn't run yet today
            if current_time_str == scheduled_time and not already_ran_today:
                log_event(f"Schedule triggered for project '{p['name']}' at {current_time_str} UTC.", "INFO", project_id=p["id"])
                try:
                    run_publication_pipeline(p["id"])
                except Exception as err:
                    log_event(f"Pipeline execution failed for '{p['name']}': {err}", "ERROR", project_id=p["id"])

# Global singleton
scheduler = CronWorker()

def start_scheduler():
    scheduler.start()

def stop_scheduler():
    scheduler.stop()
