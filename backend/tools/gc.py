"""Delete recordings past the retention window.

An execution is a directory of events plus a row in SQLite, and both are
regenerable: re-running the same source with the same settings reproduces it
byte for byte.  Expiry is therefore safe, and the only visible consequence is
that an old share link 404s.

    python backend/tools/gc.py            # honour ALGOSTUDIO_RETENTION_DAYS
    python backend/tools/gc.py --days 7
    python backend/tools/gc.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from algostudio.config import SETTINGS                              # noqa: E402
from algostudio.services.execution_service import ExecutionService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=None,
                        help="override ALGOSTUDIO_RETENTION_DAYS")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be deleted and exit")
    args = parser.parse_args()

    window = SETTINGS.retention_days if args.days is None else args.days
    service = ExecutionService()

    if window <= 0:
        print("retention disabled (days <= 0); nothing to do")
        return 0

    if args.dry_run:
        cutoff = time.time() - window * 86_400
        rows = service.db.executions_before(cutoff)
        for row in rows:
            print(f"would delete {row['id']}  {row['storage_dir']}")
        print(f"{len(rows)} execution(s) older than {window} day(s)")
        return 0

    removed = service.purge_expired(window)
    print(f"removed {removed} execution(s) older than {window} day(s) "
          f"from {SETTINGS.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
