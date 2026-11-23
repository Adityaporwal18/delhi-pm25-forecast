"""Should a scheduled run refresh the live forecast now? Standard library only, so the scheduled job
can decide in seconds, before installing anything.

GitHub starts scheduled runs late or drops them (on 23 Nov 2026 it ran none for 12 hours), so the
job is scheduled twice an hour, and this check lets a run go ahead only when the published forecast
is at least REFRESH_EVERY old, or when a person started the run by hand. Forecasts still come
about every 3 hours, and a missed or failed refresh is retried half an hour later.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

REFRESH_EVERY: Final = timedelta(hours=2, minutes=45)


def refresh_due(published: Path, now: datetime, by_hand: bool) -> bool:
    """True if `published` (serving/live_forecast.json) was made at least REFRESH_EVERY before
    `now`, cannot be read, or the run was started by hand."""
    if by_hand:
        return True
    try:
        made = datetime.fromisoformat(json.loads(published.read_text())["generated_at_utc"])
    except (OSError, ValueError, KeyError, TypeError):
        return True
    return now - made >= REFRESH_EVERY
