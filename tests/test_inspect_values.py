"""Tests for Stage 2 inspection, part 2: suspicious values, station pairs, AQI evidence."""

import numpy as np
import pandas as pd
import pytest

from delhi_pm25.inspect_coverage import POLLUTANTS
from delhi_pm25.inspect_values import (
    bp_units,
    distance_km,
    hourly_checks,
    lag_scan,
    neighbour_lags,
    prominent_shares,
    repeats_within_hour,
    spike_table,
    value_extremes,
    worst_days,
)


def hourly_frame(**columns: list[float]) -> pd.DataFrame:
    """One station 'a' on a complete hourly grid, like inspect_coverage.hourly_by_label."""
    n = len(next(iter(columns.values())))
    hours = pd.date_range("2024-11-01", periods=n, freq="h", name="hour")
    index = pd.MultiIndex.from_product([pd.CategoricalIndex(["a"]), hours], names=["slug", "hour"])
    return pd.DataFrame(columns, index=index, dtype=float)


def test_value_extremes_counts_readings_sitting_on_the_station_maximum() -> None:
    # Given: PM2.5 that hits the same top value three times (an instrument ceiling) and one zero
    readings = pd.DataFrame({p: np.nan for p in POLLUTANTS}, index=range(5))
    readings["slug"] = pd.Categorical(["a"] * 5)
    readings["pm25"] = [10.0, 1000.0, 1000.0, 1000.0, 0.0]
    # When
    table = value_extremes(readings).set_index(["slug", "pollutant"])
    # Then
    assert table.loc[("a", "pm25"), ["max", "n_at_max", "n_nonpositive"]].tolist() == [1000.0, 3, 1]


def test_bp_units_tells_hpa_from_mmhg_by_the_median() -> None:
    # Given: one station reporting ~988 (hPa), one ~739 (mmHg), one without a sensor
    readings = pd.DataFrame({
        "slug": pd.Categorical(["x", "x", "y", "y", "z"]),
        "bp": [985.0, 990.0, 738.0, 740.0, np.nan],
    })
    # When
    table = bp_units(readings)
    # Then
    assert table["looks_like"].to_dict() == {"x": "hPa", "y": "mmHg", "z": "no sensor"}


def test_pm25_above_pm10_share_counts_only_hours_with_both() -> None:
    # Given: 2 hours with both values (one impossible: PM2.5 > PM10) and 2 incomplete hours
    hourly = hourly_frame(pm25=[50, 80, np.nan, 30], pm10=[100, 60, 90, np.nan])
    # When
    table = hourly_checks(hourly, flat_hours=6)
    # Then
    assert table.loc["a", "pm25_above_pm10_pct"] == 50.0


def test_spike_table_reports_the_neighbours_of_an_isolated_spike() -> None:
    # Given: one hour that jumps up 300 and straight back down
    hourly = hourly_frame(pm25=[100, 400, 110, 105])
    # When
    spikes = spike_table(hourly, jump=200.0)
    # Then
    assert spikes[["before", "value", "after"]].to_numpy().tolist() == [[100.0, 400.0, 110.0]]


def test_distance_km_matches_a_hundredth_of_a_degree_of_latitude() -> None:
    # Given / When / Then: 0.01 degree of latitude is about 1.11 km everywhere
    assert distance_km((28.60, 77.20), (28.61, 77.20)) == pytest.approx(1.112, abs=0.002)


def test_repeats_within_hour_counts_full_hours_with_a_single_value() -> None:
    # Given: hour 1 repeats one value four times (really hourly), hour 2 has four different values
    labels = pd.date_range("2024-01-01", periods=8, freq="15min")
    readings = pd.DataFrame({
        "slug": pd.Categorical(["a"] * 8),
        "ts_label": labels,
        "pm25": [5.0, 5.0, 5.0, 5.0, 5.0, 6.0, 7.0, 8.0],
    })
    # When
    table = repeats_within_hour(readings)
    # Then
    assert table.loc["a", "all_four_identical_pct"] == 50.0


def test_prominent_shares_ignore_hours_without_a_valid_aqi() -> None:
    # Given: two valid winter hours (PM2.5 worst, then PM10 worst) and one invalid hour
    hours = pd.to_datetime(["2024-01-01 00:00", "2024-01-01 01:00", "2024-01-01 02:00"])
    index = pd.MultiIndex.from_product([["a"], hours], names=["slug", "hour"])
    aqi = pd.DataFrame({"aqi": [300.0, 120.0, np.nan], "prominent": ["pm25", "pm10", None]}, index=index)
    # When
    shares = prominent_shares(aqi)
    # Then
    assert shares.loc["winter", ["pm10", "pm25"]].tolist() == [50.0, 50.0]


def test_worst_days_are_indexed_by_day_not_hour() -> None:
    # Given: two days of hourly PM2.5, the second one worse
    hourly = hourly_frame(pm25=[100.0] * 24 + [300.0] * 24)
    # When
    table = worst_days(hourly, n=1)
    # Then
    assert (table.index.name, table.index[0]) == ("day", pd.Timestamp("2024-11-02"))


def test_lag_scan_finds_how_many_hours_one_series_runs_behind_another() -> None:
    # Given: b is the same signal as a, but written 3 hours later
    a = pd.Series(np.random.default_rng(0).normal(size=300).cumsum())
    b = a.shift(3)
    # When
    scan = lag_scan(b, a, max_lag=6)
    # Then
    assert scan.idxmax() == 3


def test_neighbour_lags_compares_each_station_with_its_nearest_reference() -> None:
    # Given: references a and b (b far away); c measures a's air but labels it 2 hours later
    signal = np.random.default_rng(1).normal(size=200).cumsum()
    pm25 = {"a": signal, "b": signal[::-1].copy(), "c": pd.Series(signal).shift(2).to_numpy()}
    hours = pd.date_range("2024-11-01", periods=200, freq="h", name="hour")
    index = pd.MultiIndex.from_product([pd.CategoricalIndex(list(pm25)), hours], names=["slug", "hour"])
    hourly = pd.DataFrame({"pm25": np.concatenate(list(pm25.values()))}, index=index)
    stations = pd.DataFrame({"slug": list(pm25), "latitude": [28.60, 28.90, 28.61], "longitude": [77.2] * 3})
    # When
    table = neighbour_lags(stations, hourly, reference=["a", "b"])
    # Then
    assert table.loc["c", ["neighbour", "best_lag_h"]].tolist() == ["a", 2]
