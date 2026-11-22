"""Where the site gets the latest live forecast, without redeploying.

A GitHub Action commits serving/live_forecast.json every 6 hours (scripts/14_refresh_live.py).
The site reads that file from GitHub, asking at most once per CACHE_SECONDS, and keeps the copy
built into its image as a fallback, always showing whichever of the two was issued later. A new
forecast therefore appears within minutes of the commit with no rebuild, and a GitHub outage
leaves the last good forecast on the page.
"""

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Final

import requests

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


class LiveSource:
    """The latest live forecast: the later of GitHub's copy and the built-in one, cached."""

    def __init__(self, fetch: Fetch, fallback: Path, clock: Clock = time.monotonic) -> None:
        self._fetch, self._fallback, self._clock = fetch, fallback, clock
        self._cached: dict[str, object] | None = None
        self._checked_at: float | None = None

    def latest(self) -> dict[str, object] | None:
        now = self._clock()
        if self._checked_at is not None and now - self._checked_at < CACHE_SECONDS:
            return self._cached
        found = [document for document in (self._remote(), self._built_in()) if document is not None]
        self._cached = max(found, key=lambda document: str(document.get("issued_utc", "")), default=None)
        self._checked_at = now
        return self._cached

    def _remote(self) -> dict[str, object] | None:
        try:
            return self._fetch()
        except (OSError, ValueError):
            return None

    def _built_in(self) -> dict[str, object] | None:
        try:
            return json.loads(self._fallback.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None
