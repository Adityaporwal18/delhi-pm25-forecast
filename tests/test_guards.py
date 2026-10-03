"""Tests for the checks that stop the pipeline when its inputs are out of date (src/delhi_pm25/guards.py)."""

import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from delhi_pm25.guards import InputsOutOfDate, check_up_to_date, check_weather_covers

FIRST_DAY, LAST_DAY = date(2023, 1, 1), date(2025, 12, 31)
STACK_COMMAND = ".venv/bin/python scripts/03_stack_raw.py"


def weather_manifest(start: str, end: str) -> pd.DataFrame:
    return pd.DataFrame({"source": ["actual_ecmwf_ifs"], "cell_id": ["28.5764N_77.1868E"],
                         "start_date": [start], "end_date": [end]})


@pytest.mark.parametrize(("start", "end"), [("2023-12-25", "2026-01-01"), ("2022-12-25", "2025-06-30")])
def test_weather_not_covering_the_data_stops_with_the_command_that_fixes_it(start: str, end: str) -> None:
    # Given: PM2.5 data from 1 Jan 2023 to 31 Dec 2025, weather starting too late or ending too early
    manifest = weather_manifest(start, end)
    # When / Then: the message carries the exact re-download command (a week of extra history included)
    with pytest.raises(InputsOutOfDate, match="--start 2022-12-25 --end 2025-12-31 --force"):
        check_weather_covers(manifest, FIRST_DAY, LAST_DAY)


def test_weather_covering_the_data_plus_a_week_passes() -> None:
    check_weather_covers(weather_manifest("2022-12-25", "2026-01-01"), FIRST_DAY, LAST_DAY)


def touched(path: Path, mtime: int) -> Path:
    path.touch()
    os.utime(path, (mtime, mtime))
    return path


def test_output_older_than_its_inputs_stops_with_the_rebuild_command(tmp_path: Path) -> None:
    # Given: the stacked parquet was written before a raw CSV changed
    output = touched(tmp_path / "stacked.parquet", 1000)
    source = touched(tmp_path / "station.csv", 2000)
    # When / Then
    with pytest.raises(InputsOutOfDate, match="03_stack_raw"):
        check_up_to_date(output, [source], STACK_COMMAND)


def test_output_newer_than_its_inputs_passes(tmp_path: Path) -> None:
    source = touched(tmp_path / "station.csv", 1000)
    output = touched(tmp_path / "stacked.parquet", 2000)
    check_up_to_date(output, [source], STACK_COMMAND)


def test_missing_output_stops_with_the_build_command(tmp_path: Path) -> None:
    with pytest.raises(InputsOutOfDate, match="03_stack_raw"):
        check_up_to_date(tmp_path / "stacked.parquet", [], STACK_COMMAND)
