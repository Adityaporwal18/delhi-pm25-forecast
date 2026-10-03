"""Tests for reading the cleaning decisions in config/pipeline.toml (src/delhi_pm25/config.py)."""

from pathlib import Path

import pandas as pd
import pytest

from delhi_pm25.config import ConfigError, load_config
from delhi_pm25.paths import PIPELINE_TOML

VALID = """
target = "pm25"

[split]
test_start = 2025-01-01T00:00:00+05:30

[hourly]
min_readings = 1
clock = "ist"

[ceiling]
ug_m3 = 1000.0
pollutants = ["pm25", "pm10"]

[spikes.pm25]
jump_ug_m3 = 200.0
calm_city_median_ug_m3 = 300.0

[flat_runs]
min_hours = 6
pollutants = ["pm25", "pm10"]

[stations]
min_train_coverage_pct = 75.0
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
    ],
)
def test_invalid_settings_are_rejected_with_a_clear_message(
    tmp_path: Path, old: str, new: str, message: str,
) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(write_config(tmp_path, VALID.replace(old, new)))
