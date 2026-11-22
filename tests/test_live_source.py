"""Tests for where the site gets the latest live forecast (src/delhi_pm25/live_source.py)."""

import json
from pathlib import Path

from delhi_pm25.live_source import CACHE_SECONDS, LiveDocument, LiveSource


def document(issued: str) -> dict[str, object]:
    """A live forecast file as scripts/14_refresh_live.py writes it (one row is enough here)."""
    return {
        "generated_at_utc": "2026-11-22T17:15:12+00:00", "issued_utc": issued, "stations_reporting": 1, "stations": 1,
        "training_window": {"first_target_utc": "2023-01-01T01:30:00+00:00", "last_target_utc": "2026-11-16T18:30:00+00:00"},
        "rows": [{"slug": "a", "horizon_h": 48, "valid_utc": "2026-11-24T16:30:00+00:00",
                  "p10": 79.2, "p50": 145.1, "p90": 240.0, "measured": None}],
    }


OLDER = document("2026-11-22T03:30:00+00:00")
NEWER = document("2026-11-22T16:30:00+00:00")


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class CountingFetch:
    """Stands in for GitHub: returns a document, or fails like an unreachable server."""

    def __init__(self, answer: dict[str, object] | None) -> None:
        self.answer, self.calls = answer, 0

    def __call__(self) -> dict[str, object]:
        self.calls += 1
        if self.answer is None:
            raise OSError("GitHub unreachable")
        return self.answer


def built_in(tmp_path: Path, contents: dict[str, object]) -> Path:
    path = tmp_path / "live_forecast.json"
    path.write_text(json.dumps(contents))
    return path


def issued(found: LiveDocument | None) -> str | None:
    return None if found is None else found.issued_utc.isoformat()


def test_the_later_forecast_wins_whichever_copy_holds_it(tmp_path: Path) -> None:
    newer_on_github = LiveSource(CountingFetch(NEWER), built_in(tmp_path, OLDER)).latest()
    newer_built_in = LiveSource(CountingFetch(OLDER), built_in(tmp_path, NEWER)).latest()
    assert (issued(newer_on_github), issued(newer_built_in)) == ("2026-11-22T16:30:00+00:00",) * 2


def test_github_being_unreachable_falls_back_to_the_built_in_copy(tmp_path: Path) -> None:
    assert issued(LiveSource(CountingFetch(None), built_in(tmp_path, OLDER)).latest()) == "2026-11-22T03:30:00+00:00"


def test_a_malformed_copy_is_ignored_even_if_it_claims_to_be_newer(tmp_path: Path) -> None:
    # Given: GitHub's copy is newer but incomplete (no rows, no stations)
    broken = CountingFetch({"issued_utc": "2026-11-23T00:00:00+00:00"})
    # When / Then: the complete built-in copy is shown
    assert issued(LiveSource(broken, built_in(tmp_path, OLDER)).latest()) == "2026-11-22T03:30:00+00:00"


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
