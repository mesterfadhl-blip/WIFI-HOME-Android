"""Create a consistent backup while the desktop service is running or stopped."""

from pathlib import Path
from datetime import datetime, timezone
import os
import secrets
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from erp.backup import backup

base = (
    Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    / "WIFI-HOME-ERP"
)
source = base / "data.sqlite3"
if not source.is_file():
    raise SystemExit("Start the system once before creating a backup.")
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
target = ROOT / "MY-BACKUPS" / f"WIFI-HOME-{stamp}-{secrets.token_hex(4)}.sqlite3"
print("Consistent backup saved: " + str(backup(source, target)))
