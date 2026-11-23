"""Tests for whether a scheduled run should refresh the forecast (src/delhi_pm25/due.py)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from delhi_pm25.due import REFRESH_EVERY, refresh_due

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def published(tmp_path: Path, age: timedelta) -> Path:
    path = tmp_path / "live_forecast.json"
    path.write_text(json.dumps({"generated_at_utc": (NOW - age).isoformat()}))
    return path


@pytest.mark.parametrize(
    ("age", "by_hand", "due"),
    [
        pytest.param(timedelta(hours=1), False, False, id="made an hour ago: not due"),
        pytest.param(REFRESH_EVERY, False, True, id="old enough: due"),
        pytest.param(timedelta(hours=1), True, True, id="started by hand: always due"),
    ],
)
def test_a_refresh_is_due_when_the_forecast_is_old_enough_or_asked_for(tmp_path: Path, age: timedelta, by_hand: bool, due: bool) -> None:
    assert refresh_due(published(tmp_path, age), NOW, by_hand) is due


def test_without_a_readable_forecast_a_refresh_is_due(tmp_path: Path) -> None:
    broken = tmp_path / "live_forecast.json"
    broken.write_text("not json")
    assert (refresh_due(broken, NOW, False), refresh_due(tmp_path / "missing.json", NOW, False)) == (True, True)
