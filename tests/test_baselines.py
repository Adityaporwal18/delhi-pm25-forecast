"""Tests for the persistence and climatology baselines and how forecasts are scored (src/delhi_pm25/baselines.py)."""

import numpy as np
import pandas as pd

from delhi_pm25.baselines import calendar_slot, climatology, climatology_table, score
from delhi_pm25.config import BaselineSettings


def ends(*delhi_hour_starts: str) -> pd.Series:
    """Hour-end stamps in UTC for hours that START at the given Delhi times."""
    starts = pd.DatetimeIndex(delhi_hour_starts).tz_localize("Asia/Kolkata")
    return pd.Series(starts + pd.Timedelta(hours=1)).dt.tz_convert("UTC").dt.as_unit("us")


def history(values: dict[str, float]) -> pd.DataFrame:
    """Training targets at station a, keyed by the Delhi start time of their hour."""
    return pd.DataFrame({"slug": "a", "target_hour_end_utc": ends(*values), "target": list(values.values())})


def target_rows(*delhi_hour_starts: str) -> pd.DataFrame:
    return pd.DataFrame({"slug": "a", "target_hour_end_utc": ends(*delhi_hour_starts)})


def test_the_same_date_is_the_same_calendar_day_in_leap_and_ordinary_years() -> None:
    # Given: 11:00 on 1 March in an ordinary year and in a leap year
    stamps = ends("2023-03-01 11:00", "2024-03-01 11:00")
    # When
    hour, day = calendar_slot(stamps)
    # Then
    assert (hour.tolist(), day.tolist()) == ([11, 11], [61, 61])


def test_climatology_averages_nearby_days_and_needs_enough_values() -> None:
    # Given: 11:00 values on 10-12 January and a lone one on 20 January; window +-1 day, 2 values needed
    known = history({"2023-01-10 11:00": 100.0, "2023-01-11 11:00": 200.0,
                     "2023-01-12 11:00": 300.0, "2023-01-20 11:00": 1000.0})
    table = climatology_table(known, BaselineSettings(climatology_days_either_side=1, climatology_min_values=2))
    # When
    forecast = climatology(target_rows("2024-01-11 11:00", "2024-01-20 11:00"), table)
    # Then
    assert forecast.fillna(-1).tolist() == [200.0, -1]


def test_climatology_window_wraps_round_the_new_year() -> None:
    # Given: one value at 11:00 on 31 December
    table = climatology_table(history({"2023-12-31 11:00": 50.0}), BaselineSettings(1, 1))
    # When
    forecast = climatology(target_rows("2024-01-01 11:00"), table)
    # Then
    assert forecast.tolist() == [50.0]


def test_methods_are_scored_on_the_same_rows() -> None:
    # Given: three measured target hours; the persistence forecast is blank for the second
    rows = target_rows("2024-11-01 10:00", "2024-11-01 11:00", "2024-11-01 12:00").assign(target=[10.0, 20.0, 30.0])
    forecasts = {"persistence": pd.Series([12.0, np.nan, 33.0]), "climatology": pd.Series([10.0, 25.0, 30.0])}
    # When
    table = score(rows, forecasts).set_index("hours")
    # Then: both methods are scored on the first and third rows only
    assert table.loc["all hours", ["n_rows", "persistence_mae", "climatology_mae"]].tolist() == [2, 2.5, 0.0]
