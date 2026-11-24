"""
GitPulse CMS - Application Entrypoint
Launches the background publishing scheduler daemon and starts the Web Dashboard.
"""

import sys
from database import init_db, seed_demo_data
from engine.auth import init_default_admin
from scheduler.cron_worker import start_scheduler
from server.http_server import run_server
from config import SERVER_HOST, SERVER_PORT

def main():
    print("=" * 60)
    print("⚡ GitPulse CMS - Autonomous Multi-Repo GitHub Blog Engine")
    print("=" * 60)
    
    # 1. Initialize SQLite Database & Schema
    init_db()
    seed_demo_data()

    # 2. Ensure Administrator Account & Security Guardrails
    admin_info = init_default_admin()
    if admin_info.get("is_new"):
        print(f"🔒 Initial Administrator Created:")
        print(f"   Username: {admin_info['username']}")
        print(f"   Password: {admin_info['password']}")
        print(f"   (Please change your password in Settings after logging in)")

    # 3. Start Background Scheduler Daemon
    start_scheduler()

    # 4. Start HTTP Server
    run_server(host=SERVER_HOST, port=SERVER_PORT)

if __name__ == "__main__":
    main()
