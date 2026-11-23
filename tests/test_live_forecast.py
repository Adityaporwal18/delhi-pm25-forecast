"""Tests for turning live features into the published forecast, failing safely (src/delhi_pm25/live_forecast.py)."""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from delhi_pm25.live_forecast import (
    STALE_AFTER,
    Freshness,
    already_published,
    forecast_document,
    order_band,
    previous_issue,
    problems_with,
    publish_if_sound,
    published_age,
)
from delhi_pm25.paths import PROJECT_ROOT

NOW = pd.Timestamp("2026-11-22 04:30", tz="UTC")
ISSUED = pd.Timestamp("2026-11-22 02:30", tz="UTC")


def latest_features(now_values: list[float], week_means: list[float], issued: pd.Timestamp = ISSUED) -> pd.DataFrame:
    """The live feature rows for one forecast hour (only the columns the checks read)."""
    return pd.DataFrame({"slug": [f"s{i}" for i in range(len(now_values))], "hour_end_utc": issued,
                         "pm25_lag_0h": now_values, "pm25_mean_168h": week_means})


GOOD = latest_features([100.0, 120.0, 140.0], [150.0, 160.0, 170.0])


def test_sound_live_data_raises_no_problem() -> None:
    assert problems_with(GOOD, "pm25", Freshness(now=NOW, previous_issue=None)) == []


@pytest.mark.parametrize(
    ("features", "freshness", "message"),
    [
        pytest.param(GOOD, Freshness(ISSUED + pd.Timedelta(hours=13), None), "old", id="stale"),
        pytest.param(latest_features([100.0] * 3, [150.0, np.nan, np.nan]), Freshness(NOW, None), "history", id="short history"),
        pytest.param(GOOD, Freshness(ISSUED - pd.Timedelta(hours=2), None), "future", id="clock wrong"),
    ],
)
def test_suspicious_live_data_is_refused_with_a_reason(features: pd.DataFrame, freshness: Freshness, message: str) -> None:
    problems = problems_with(features, "pm25", freshness)
    assert any(message in problem for problem in problems), problems


def test_band_edges_never_cross_the_median() -> None:
    low, high = order_band(pd.Series([10.0, 60.0]), pd.Series([50.0, 50.0]), pd.Series([40.0, 80.0]))
    assert (low.tolist(), high.tolist()) == ([10.0, 50.0], [50.0, 80.0])


def test_the_document_carries_last_updated_and_blank_values_as_null() -> None:
    # Given: the value measured now (horizon 0) and one forecast
    table = pd.DataFrame({"slug": ["a", "a"], "horizon_h": [0, 6], "valid_utc": [ISSUED, ISSUED + pd.Timedelta(hours=6)],
                          "p10": [np.nan, 60.04], "p50": [np.nan, 90.0], "p90": [np.nan, 150.0], "measured": [120.6, np.nan]})
    # When
    document = forecast_document(table, ISSUED, NOW)
    # Then
    assert (document["generated_at_utc"], document["issued_utc"], document["rows"][0]["p50"], document["rows"][1]["p10"]) == (
        "2026-11-22T04:30:00+00:00", "2026-11-22T02:30:00+00:00", None, 60.0,
    )


def test_with_any_problem_the_published_file_is_left_untouched(tmp_path: Path) -> None:
    # Given: yesterday's forecast already published
    path = tmp_path / "live_forecast.json"
    path.write_text('{"issued_utc": "yesterday"}')
    # When: today's refresh found a problem
    published = publish_if_sound({"issued_utc": "today"}, ["too few stations"], path)
    # Then: a slightly stale forecast beats a broken page
    assert (published, path.read_text()) == (False, '{"issued_utc": "yesterday"}')


def test_sound_refresh_replaces_the_file_and_is_read_back_as_the_previous_issue(tmp_path: Path) -> None:
    path = tmp_path / "live_forecast.json"
    assert publish_if_sound({"issued_utc": ISSUED.isoformat(), "rows": []}, [], path)
    assert (json.loads(path.read_text())["issued_utc"], previous_issue(path)) == (ISSUED.isoformat(), ISSUED)


def test_no_published_file_means_no_previous_issue(tmp_path: Path) -> None:
    assert previous_issue(tmp_path / "missing.json") is None


def test_a_forecast_hour_already_published_is_not_news() -> None:
    # Given: the published file already starts at this forecast hour (a second trigger ran)
    # When / Then: nothing to publish, which is not a failure
    assert (already_published(GOOD, Freshness(NOW, ISSUED)), already_published(GOOD, Freshness(NOW, None))) == (True, False)


def test_the_published_forecast_s_age_and_the_stale_line_match_the_site(tmp_path: Path) -> None:
    # Given: a forecast made at NOW, and the stale line the website warns at
    path = tmp_path / "live_forecast.json"
    path.write_text(json.dumps({"generated_at_utc": NOW.isoformat()}))
    site = re.search(r"STALE_AFTER_HOURS = (\d+)", (PROJECT_ROOT / "frontend" / "src" / "live.ts").read_text())
    # When / Then: two hours later it is two hours old, and both sides call it stale at the same age
    assert site is not None
    assert (published_age(path, NOW + pd.Timedelta(hours=2)), STALE_AFTER) == (pd.Timedelta(hours=2), pd.Timedelta(hours=int(site.group(1))))
