"""Import first in every test module: isolates the SQLite file and sets a test encryption key."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if "GITPULSE_DB_PATH" not in os.environ:
    _d = tempfile.mkdtemp(prefix="gitpulse-test-")
    os.environ["GITPULSE_DB_PATH"] = os.path.join(_d, "test.db")
# Root-level discovery imports engine/ (and so database) before any test module: repoint what already loaded.
for _name in ("config", "database"):
    if _name in sys.modules:
        sys.modules[_name].DATABASE_PATH = Path(os.environ["GITPULSE_DB_PATH"])
# Never run against a real Postgres by accident: only an explicit throwaway schema keeps DATABASE_URL.
if not os.environ.get("DATABASE_SCHEMA"):
    os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("CREDENTIAL_ENC_KEY", "dGVzdC1rZXktdGVzdC1rZXktdGVzdC1rZXktMTIzNDU=")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.pop("WHATSAPP_MOCK", None)
