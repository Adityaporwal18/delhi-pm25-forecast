"""Tests for the Stage 2 cleaning rules and station selection (src/delhi_aqi/clean_rules.py)."""

import dataclasses

import numpy as np
import pandas as pd

from delhi_aqi.clean_rules import blank_flat_runs, missing_in_worst_hours, remove_spikes, station_selection
from delhi_aqi.config import PipelineConfig

START = pd.Timestamp("2024-11-01 00:30", tz="UTC")
HOUR = pd.Timedelta(hours=1)


def hourly_grid(pm25: dict[str, list[float]]) -> pd.DataFrame:
    """A complete hourly grid as to_hourly returns it: one row per station per hour, from START.
    Every hour with a value is a full hour (4 readings); every blank hour has none."""
    parts = [pd.DataFrame({"slug": slug, "hour_end_utc": pd.date_range(START, periods=len(values), freq="h"),
                           "pm25": values})
             for slug, values in pm25.items()]
    hourly = pd.concat(parts, ignore_index=True)
    hourly["slug"] = pd.Categorical(hourly["slug"], categories=list(pm25))
    hourly["n_pm25"] = np.where(hourly["pm25"].notna(), 4, 0).astype("int8")
    return hourly


def test_station_selection_judges_coverage_on_training_hours_only(config: PipelineConfig) -> None:
    # Given: a is complete in training but empty in test; b is the opposite
    hourly = hourly_grid({"a": [1.0] * 4, "b": [1.0] * 4})
    hourly["n_pm25"] = [4, 4, 0, 0, 4, 0, 4, 4]
    training_is_first_two_hours = dataclasses.replace(config, test_start=START + HOUR)
    # When
    selection = station_selection(hourly, training_is_first_two_hours)
    # Then: a (100% of training readings) stays; b (50%) goes, however good its test period is
    assert selection["kept"].to_dict() == {"a": True, "b": False}


def test_isolated_spike_is_removed_when_the_rest_of_the_city_is_calm(config: PipelineConfig) -> None:
    # Given: a jumps 100 -> 400 -> 110 while b and c stay at 100 (city median 100 at the spike)
    hourly = hourly_grid({"a": [100.0, 400.0, 110.0], "b": [100.0] * 3, "c": [100.0] * 3})
    # When
    cleaned, _ = remove_spikes(hourly, config.spikes)
    # Then
    assert cleaned.loc[cleaned["slug"] == "a", "pm25"].isna().tolist() == [False, True, False]


def test_isolated_spike_is_kept_when_the_city_is_polluted_too(config: PipelineConfig) -> None:
    # Given: the same spike, but b and c read 320, so the city median at the spike hour is 320 (>= 300)
    hourly = hourly_grid({"a": [100.0, 400.0, 110.0], "b": [320.0] * 3, "c": [320.0] * 3})
    # When
    _, log = remove_spikes(hourly, config.spikes)
    # Then
    assert log["action"].tolist() == ["kept: city polluted"]


def test_six_identical_hours_are_blanked(config: PipelineConfig) -> None:
    hourly = hourly_grid({"a": [50.0] * 6 + [60.0]})
    cleaned, _ = blank_flat_runs(hourly, config.flat_runs)
    assert cleaned["pm25"].isna().tolist() == [True] * 6 + [False]


def test_five_identical_hours_are_kept(config: PipelineConfig) -> None:
    hourly = hourly_grid({"a": [50.0] * 5 + [60.0]})
    cleaned, _ = blank_flat_runs(hourly, config.flat_runs)
    assert cleaned["pm25"].notna().all()


def test_a_flat_run_never_continues_into_the_next_station(config: PipelineConfig) -> None:
    # Given: a ends with three 50s and b starts with three 50s (six in a row only if stations got mixed)
    hourly = hourly_grid({"a": [10.0, 20.0, 30.0, 50.0, 50.0, 50.0], "b": [50.0, 50.0, 50.0, 60.0, 70.0, 80.0]})
    # When
    cleaned, _ = blank_flat_runs(hourly, config.flat_runs)
    # Then
    assert cleaned["pm25"].notna().all()


def test_missing_share_in_the_smoggiest_test_hours(config: PipelineConfig) -> None:
    # Given: 10 training + 10 test hours; in the test period the one smoggy hour (city 600) is blank at b
    training = [100.0] * 9 + [500.0]
    hourly = hourly_grid({"a": training + [100.0] * 9 + [600.0], "b": training + [100.0] * 9 + [np.nan]})
    training_is_first_ten_hours = dataclasses.replace(config, test_start=START + 9 * HOUR)
    # When
    table = missing_in_worst_hours(hourly, training_is_first_ten_hours).set_index(["period", "hours"])
    # Then: 1 of 20 test station-hours is blank overall (5%), but 1 of the 2 in the smoggiest hour (50%)
    assert table.loc[[("test", "all hours"), ("test", "smoggiest 10.0%")], "blank_pct"].tolist() == [5.0, 50.0]


def test_partial_share_counts_values_built_from_fewer_than_four_readings(config: PipelineConfig) -> None:
    # Given: two training hours with values; the second rests on only 2 of its 4 readings
    hourly = hourly_grid({"a": [100.0, 200.0]})
    hourly["n_pm25"] = np.array([4, 2], dtype="int8")
    # When
    table = missing_in_worst_hours(hourly, config).set_index(["period", "hours"])
    # Then
    assert table.loc[("train", "all hours"), "partial_pct"] == 50.0
