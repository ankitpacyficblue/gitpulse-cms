"""
GitPulse CMS - Application Entrypoint
Launches the background publishing scheduler daemon and starts the Web Dashboard.
"""

import sys
from engine.auth import init_db_and_admin
from scheduler.cron_worker import start_scheduler
from server.http_server import run_server
from config import SERVER_HOST, SERVER_PORT

def main():
    print("=" * 60)
    print("⚡ GitPulse CMS - Autonomous Multi-Repo GitHub Blog Engine")
    print("=" * 60)
    
    # 1. Initialize SQLite Database & Schema (no sample data, no default login)
    init_db_and_admin()
    print("No accounts are created automatically. Create the first owner with:")
    print("   python3 cli.py create-owner --account \"Account name\" --username NAME")

    # 2. Start Background Scheduler Daemon
    start_scheduler()

    # 3. Start HTTP Server
    run_server(host=SERVER_HOST, port=SERVER_PORT)

if __name__ == "__main__":
    main()
