"""Tests for the stage 6 error-analysis slices (src/delhi_pm25/error_analysis.py)."""

import numpy as np
import pandas as pd

from delhi_pm25.error_analysis import change_class, errors_by, issue_time_tail, outcome_tail, target_season


def utc(*stamps: str) -> pd.Series:
    return pd.Series(pd.DatetimeIndex(stamps, tz="UTC").as_unit("us"))


def ten_hours() -> pd.Series:
    return utc(*[f"2025-01-01 {hour:02d}:30" for hour in range(10)])


def test_season_follows_the_delhi_calendar_of_the_target_hour() -> None:
    # Given: the last Delhi hour of February (ends 18:30 UTC), the first of March, July, October
    ends = utc("2025-02-28 18:30", "2025-02-28 19:30", "2025-07-01 06:30", "2025-10-20 06:30")
    # When / Then
    assert target_season(pd.DataFrame({"target_hour_end_utc": ends})).tolist() == [
        "winter", "summer", "monsoon", "post-monsoon",
    ]


def test_change_class_measures_how_far_pm25_moved_in_48_hours() -> None:
    rows = pd.DataFrame({"target": [350.0, 250.0, 200.0, 150.0, 50.0, np.nan], "pm25_lag_0h": [200.0] * 6})
    assert change_class(rows, now="pm25_lag_0h").astype(object).fillna("blank").tolist() == [
        "rose 100+", "rose 30-100", "steady (within 30)", "fell 30-100", "fell 100+", "blank",
    ]


def test_outcome_tail_picks_hours_by_how_smoggy_they_turned_out() -> None:
    # Given: ten target hours at one station, 10 to 100 ug/m3
    rows = pd.DataFrame({"target_hour_end_utc": ten_hours(), "target": np.arange(10, 101, 10.0)})
    # When / Then: the smoggiest 10% is the 100 ug/m3 hour alone
    assert outcome_tail(rows, share=0.1).tolist() == [False] * 9 + [True]


def test_issue_time_tail_picks_hours_by_the_city_median_known_when_forecasting() -> None:
    rows = pd.DataFrame({"hour_end_utc": ten_hours(), "city_pm25_median": np.arange(10, 101, 10.0)})
    assert issue_time_tail(rows, share=0.1, city_now="city_pm25_median").tolist() == [False] * 9 + [True]


def test_errors_by_scores_every_forecast_on_the_same_rows() -> None:
    # Given: two groups; persistence is blank on the last row, so that row is left out for all
    rows = pd.DataFrame({"target": [100.0, 100.0, 200.0, 200.0]})
    forecasts = {
        "persistence": pd.Series([110.0, 90.0, 150.0, np.nan]),
        "model": pd.Series([100.0, 120.0, 260.0, 0.0]),
    }
    # When
    table = errors_by(rows, forecasts, pd.Series(["a", "a", "b", "b"], name="group"))
    # Then: a = MAE 10 / 10, bias 0 / +10; b (one row) = MAE 50 / 60, bias -50 / +60
    columns = ["n_rows", "persistence_mae", "model_mae", "persistence_bias", "model_bias"]
    assert table.loc[["a", "b"], columns].to_numpy().tolist() == [[2, 10, 10, 0, 10], [1, 50, 60, -50, 60]]
