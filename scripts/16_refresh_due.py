"""Live forecasts: tell the scheduled job whether to refresh now (prints due=true or due=false).

The job runs twice an hour; see src/delhi_pm25/due.py for why. Standard library only, so the job
runs this before installing anything, with PYTHONPATH=src:
  PYTHONPATH=src python3 scripts/16_refresh_due.py >> "$GITHUB_OUTPUT"
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from delhi_pm25.due import refresh_due

PUBLISHED = Path(__file__).resolve().parents[1] / "serving" / "live_forecast.json"


def main() -> int:
    by_hand = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    due = refresh_due(PUBLISHED, datetime.now(timezone.utc), by_hand)
    print(f"due={'true' if due else 'false'}")
    print("Refresh due." if due else "Not due: the published forecast is less than 2 h 45 min old.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
