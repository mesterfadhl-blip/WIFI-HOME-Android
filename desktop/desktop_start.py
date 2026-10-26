"""Entry script for the bundled Windows Python, isolated from user site packages."""

from pathlib import Path
import os
import sys
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from erp.desktop import main

    raise SystemExit(main())
except Exception:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "WIFI-HOME-ERP"
    base.mkdir(parents=True, exist_ok=True)
    log = base / "last-start-error.txt"
    log.write_text(traceback.format_exc(), encoding="utf-8")
    print(
        "The system could not start. Your existing database was not replaced without a backup."
    )
    print("Error details: " + str(log))
    traceback.print_exc()
    raise SystemExit(1)
