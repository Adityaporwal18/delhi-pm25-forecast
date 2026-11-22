"""Where the site gets the latest live forecast, without redeploying.

A GitHub Action commits serving/live_forecast.json every 6 hours (scripts/14_refresh_live.py).
The site reads that file from GitHub, asking at most once per CACHE_SECONDS, and keeps the copy
built into its image as a fallback, always showing whichever of the two was issued later. A new
forecast therefore appears within minutes of the commit with no rebuild, and a GitHub outage
leaves the last good forecast on the page.
"""

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Final

import requests
from pydantic import BaseModel

CACHE_SECONDS: Final = 600.0

Fetch = Callable[[], dict[str, object]]
Clock = Callable[[], float]


def github_fetch(url: str) -> Fetch:
    """A fetch for the committed forecast file at `url` (raises OSError or ValueError on failure)."""

    def fetch() -> dict[str, object]:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    return fetch


class LiveWindow(BaseModel):
    first_target_utc: str
    last_target_utc: str


class LivePoint(BaseModel):
    slug: str
    horizon_h: int
    valid_utc: datetime
    p10: float | None
    p50: float | None
    p90: float | None
    measured: float | None


class LiveDocument(BaseModel):
    """serving/live_forecast.json as scripts/14_refresh_live.py writes it."""

    generated_at_utc: datetime
    issued_utc: datetime
    stations_reporting: int
    stations: int
    training_window: LiveWindow
    rows: list[LivePoint]


class LiveSource:
    """The latest live forecast: the later of GitHub's copy and the built-in one, cached. A copy
    that cannot be read as a complete forecast is ignored, so it can never replace a good one."""

    def __init__(self, fetch: Fetch, fallback: Path, clock: Clock = time.monotonic) -> None:
        self._fetch, self._fallback, self._clock = fetch, fallback, clock
        self._cached: LiveDocument | None = None
        self._checked_at: float | None = None

    def latest(self) -> LiveDocument | None:
        now = self._clock()
        if self._checked_at is not None and now - self._checked_at < CACHE_SECONDS:
            return self._cached
        found = [document for document in (self._remote(), self._built_in()) if document is not None]
        self._cached = max(found, key=lambda document: document.issued_utc, default=None)
        self._checked_at = now
        return self._cached

    def _remote(self) -> LiveDocument | None:
        try:
            return LiveDocument.model_validate(self._fetch())
        except (OSError, ValueError):
            return None

    def _built_in(self) -> LiveDocument | None:
        try:
            return LiveDocument.model_validate_json(self._fallback.read_text())
        except (OSError, ValueError):
            return None
