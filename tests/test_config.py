"""Tests for reading the cleaning decisions in config/pipeline.toml (src/delhi_pm25/config.py)."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from delhi_pm25.config import ConfigError, load_config
from delhi_pm25.paths import PIPELINE_TOML

VALID = """
target = "pm25"

[split]
test_start = 2025-01-01T00:00:00+05:30
validation_start = 2024-01-01T00:00:00+05:30
test_end = 2026-01-01T00:00:00+05:30

[hourly]
min_readings = 1
clock = "ist"

[ceiling]
ug_m3 = 1000.0
pollutants = ["pm25", "pm10"]

[spikes.pm25]
jump_ug_m3 = 200.0
calm_city_median_ug_m3 = 200.0
polluted_city_median_ug_m3 = 300.0
min_ratio_in_between = 2.0

[flat_runs]
min_hours = 6
exempt_hours_at_ceiling = true
pollutants = ["pm25", "pm10"]

[stations]
min_train_coverage_pct = 75.0

[features]
horizon_hours = 48
lags_hours = [0, 3, 6, 12, 24, 48, 168]
rolling_hours = [6, 24, 72, 168]
rolling_min_share = 0.5
other_pollutants = ["pm10", "no2", "co"]

[features.diwali]
dates = [2023-11-12, 2024-10-31, 2025-10-20, 2026-11-08]
start_hour_ist = 18
hours = 18

[features.stubble]
first_day = "10-15"
last_day = "11-15"

[baselines]
climatology_days_either_side = 7
climatology_min_values = 5
"""


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "pipeline.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_project_config_gives_the_test_start_in_utc() -> None:
    config = load_config(PIPELINE_TOML)
    assert str(config.test_start.tz) == "UTC"


def test_test_start_written_in_delhi_time_is_converted_to_utc(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, VALID))
    assert config.test_start == pd.Timestamp("2024-12-31 18:30", tz="UTC")


def test_valid_config_gives_typed_rules(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, VALID))
    assert (config.target, config.hourly.clock, config.spikes["pm25"].jump_ug_m3, config.flat_runs.pollutants) == (
        "pm25", "ist", 200.0, ("pm25", "pm10"),
    )


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('target = "pm25"', 'target = "aqi"', "target"),
        ("+05:30", "", "time zone"),
        ("min_readings = 1", "min_readings = 5", "min_readings"),
        ('clock = "ist"', 'clock = "local"', "clock"),
        ('"pm10"]', '"pm1"]', "pm1"),
        ("min_train_coverage_pct = 75.0", "min_train_coverage_pct = 175.0", "min_train_coverage_pct"),
        ("jump_ug_m3 = 200.0", "jump_ug_m3 = -5", "jump_ug_m3"),
        ("polluted_city_median_ug_m3 = 300.0", "polluted_city_median_ug_m3 = 150.0", "polluted_city_median_ug_m3"),
        ("exempt_hours_at_ceiling = true", 'exempt_hours_at_ceiling = "yes"', "exempt_hours_at_ceiling"),
        ('ug_m3 = 1000.0\npollutants = ["pm25", "pm10"]', 'ug_m3 = 1000.0\npollutants = ["pm25"]', "exempt_hours_at_ceiling"),
        ("horizon_hours = 48", "horizon_hours = 0", "horizon_hours"),
        ("lags_hours = [0,", "lags_hours = [-1,", "lags_hours"),
        ("rolling_min_share = 0.5", "rolling_min_share = 1.5", "rolling_min_share"),
        ("start_hour_ist = 18", "start_hour_ist = 25", "start_hour_ist"),
        ('first_day = "10-15"', 'first_day = "13-01"', "first_day"),
        ('first_day = "10-15"', 'first_day = "11-20"', "first_day"),
        ('other_pollutants = ["pm10", "no2", "co"]', 'other_pollutants = ["pm25", "no2"]', "other_pollutants"),
        ("dates = [2023-11-12,", "dates = [2023-11-12T18:00:00,", "dates"),
        ("validation_start = 2024-01-01T00:00:00+05:30", "validation_start = 2025-06-01T00:00:00+05:30", "validation_start"),
        ("validation_start = 2024-01-01T00:00:00+05:30", "validation_start = 2024-01-01T00:00:00", "validation_start"),
        ("climatology_days_either_side = 7", "climatology_days_either_side = 200", "climatology_days_either_side"),
        ("climatology_min_values = 5", "climatology_min_values = 0", "climatology_min_values"),
        ("test_end = 2026-01-01T00:00:00+05:30", "test_end = 2024-06-01T00:00:00+05:30", "test_end"),
    ],
)
def test_invalid_settings_are_rejected_with_a_clear_message(
    tmp_path: Path, old: str, new: str, message: str,
) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(write_config(tmp_path, VALID.replace(old, new)))


def test_rule_d_and_the_ceiling_exemption_are_read_from_the_file(tmp_path: Path) -> None:
    # Given: settings for spike rule (d) and the exemption for hours at the analyser limit
    path = write_config(tmp_path, VALID)
    # When
    config = load_config(path)
    # Then
    spike = config.spikes["pm25"]
    assert (spike.calm_city_median_ug_m3, spike.polluted_city_median_ug_m3, spike.min_ratio_in_between,
            config.flat_runs.exempt_hours_at_ceiling) == (200.0, 300.0, 2.0, True)


def test_feature_settings_are_read_from_the_file(tmp_path: Path) -> None:
    # Given: the valid settings, including the [features] tables
    path = write_config(tmp_path, VALID)
    # When
    features = load_config(path).features
    # Then: dates stay calendar dates, the stubble season becomes month*100 + day
    assert (features.horizon_hours, features.lags_hours[-1], features.diwali.dates[1],
            features.stubble_season) == (48, 168, date(2024, 10, 31), (1015, 1115))


def test_split_and_baseline_settings_are_read_from_the_file(tmp_path: Path) -> None:
    # Given / When
    config = load_config(write_config(tmp_path, VALID))
    # Then
    assert (config.validation_start, config.baselines.climatology_days_either_side,
            config.baselines.climatology_min_values) == (pd.Timestamp("2023-12-31 18:30", tz="UTC"), 7, 5)


def test_the_test_year_has_an_end_so_later_data_is_never_scored(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path, VALID))
    assert config.test_end == pd.Timestamp("2025-12-31 18:30", tz="UTC")
