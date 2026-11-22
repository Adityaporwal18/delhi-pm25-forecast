"""Tests for where the site gets the latest live forecast (src/delhi_pm25/live_source.py)."""

import json
from pathlib import Path

from delhi_pm25.live_source import CACHE_SECONDS, LiveSource

OLDER = {"issued_utc": "2026-11-22T03:30:00+00:00", "generated_at_utc": "2026-11-22T04:27:31+00:00"}
NEWER = {"issued_utc": "2026-11-22T09:30:00+00:00", "generated_at_utc": "2026-11-22T10:25:00+00:00"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class CountingFetch:
    """Stands in for GitHub: returns a document, or fails like an unreachable server."""

    def __init__(self, document: dict[str, object] | None) -> None:
        self.document, self.calls = document, 0

    def __call__(self) -> dict[str, object]:
        self.calls += 1
        if self.document is None:
            raise OSError("GitHub unreachable")
        return self.document


def built_in(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "live_forecast.json"
    path.write_text(json.dumps(document))
    return path


def test_the_later_forecast_wins_whichever_copy_holds_it(tmp_path: Path) -> None:
    newer_on_github = LiveSource(CountingFetch(NEWER), built_in(tmp_path, OLDER)).latest()
    newer_built_in = LiveSource(CountingFetch(OLDER), built_in(tmp_path, NEWER)).latest()
    assert (newer_on_github, newer_built_in) == (NEWER, NEWER)


def test_github_being_unreachable_falls_back_to_the_built_in_copy(tmp_path: Path) -> None:
    assert LiveSource(CountingFetch(None), built_in(tmp_path, OLDER)).latest() == OLDER


def test_github_is_asked_at_most_once_per_cache_period(tmp_path: Path) -> None:
    # Given
    fetch, clock = CountingFetch(NEWER), FakeClock()
    source = LiveSource(fetch, built_in(tmp_path, OLDER), clock)
    # When: three page loads within the cache period, then one after it
    for moment in (0.0, 1.0, CACHE_SECONDS - 1.0, CACHE_SECONDS + 1.0):
        clock.now = moment
        source.latest()
    # Then
    assert fetch.calls == 2


def test_no_forecast_anywhere_gives_nothing_instead_of_failing(tmp_path: Path) -> None:
    assert LiveSource(CountingFetch(None), tmp_path / "missing.json").latest() is None
