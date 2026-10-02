"""Tests for turning 15-minute readings into a complete hourly grid (src/delhi_aqi/clean.py)."""

import numpy as np
import pandas as pd
import pytest

from delhi_aqi.clean import GridError, check_complete_grid, to_hourly
from delhi_aqi.config import CeilingRule, HourlyRules
from delhi_aqi.raw_cpcb import POLLUTANTS

DELHI_HOURS = HourlyRules(min_readings=1, clock="ist")
CEILING = CeilingRule(ug_m3=1000.0, pollutants=("pm25",))
ONE_DELHI_HOUR = [("a", "2024-01-01 10:00", 10.0), ("a", "2024-01-01 10:15", 20.0),
                  ("a", "2024-01-01 10:30", 30.0), ("a", "2024-01-01 10:45", 40.0)]


def readings_frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """Minimal stacked readings as load_raw returns them: (slug, label, pm25); other pollutants empty."""
    slugs, labels, pm25 = zip(*rows, strict=True)
    frame = pd.DataFrame({column: np.nan for column in POLLUTANTS}, index=range(len(rows)))
    frame["pm25"] = pm25
    frame.insert(0, "ts_label", pd.to_datetime(list(labels)))
    frame.insert(0, "slug", pd.Categorical(slugs, categories=sorted(set(slugs))))
    return frame


def test_delhi_clock_hour_becomes_one_row_stamped_with_its_end_in_utc() -> None:
    # Given: four readings labelled 10:00-10:45 (the label is Delhi time despite its '+0000')
    readings = readings_frame(ONE_DELHI_HOUR)
    # When
    hourly = to_hourly(readings, DELHI_HOURS, CEILING)
    # Then: the hour 10:00-11:00 Delhi time ends at 11:00 Delhi time = 05:30 UTC
    assert hourly["hour_end_utc"].tolist() == [pd.Timestamp("2024-01-01 05:30", tz="UTC")]


def test_hourly_value_is_the_mean_of_its_readings_and_keeps_their_count() -> None:
    hourly = to_hourly(readings_frame(ONE_DELHI_HOUR), DELHI_HOURS, CEILING)
    assert (hourly["pm25"].tolist(), hourly["n_pm25"].tolist()) == ([25.0], [4])


def test_utc_clock_splits_a_delhi_hour_across_two_utc_hours() -> None:
    # Given: 10:00 and 10:15 Delhi = 04:30 and 04:45 UTC; 10:30 and 10:45 Delhi = 05:00 and 05:15 UTC
    readings = readings_frame(ONE_DELHI_HOUR)
    # When
    hourly = to_hourly(readings, HourlyRules(min_readings=1, clock="utc"), CEILING)
    # Then: UTC hours ending 05:00 and 06:00 each get two of the readings
    assert hourly.set_index("hour_end_utc")["pm25"].to_dict() == {
        pd.Timestamp("2024-01-01 05:00", tz="UTC"): 15.0,
        pd.Timestamp("2024-01-01 06:00", tz="UTC"): 35.0,
    }


def test_hour_with_too_few_readings_stays_blank_but_keeps_its_count() -> None:
    readings = readings_frame([("a", "2024-01-01 10:00", 10.0)])
    hourly = to_hourly(readings, HourlyRules(min_readings=2, clock="ist"), CEILING)
    assert (hourly["pm25"].isna().tolist(), hourly["n_pm25"].tolist()) == ([True], [1])


def test_hours_without_any_reading_become_explicit_blank_rows() -> None:
    readings = readings_frame([("a", "2024-01-01 10:00", 10.0), ("a", "2024-01-01 12:00", 30.0)])
    hourly = to_hourly(readings, DELHI_HOURS, CEILING)
    assert hourly["n_pm25"].tolist() == [1, 0, 1]


def test_reading_at_the_analyser_ceiling_flags_its_hour() -> None:
    readings = readings_frame([("a", "2024-01-01 10:00", 1000.0), ("a", "2024-01-01 10:15", 900.0)])
    hourly = to_hourly(readings, DELHI_HOURS, CEILING)
    assert hourly["pm25_at_ceiling"].tolist() == [True]


def two_station_grid() -> pd.DataFrame:
    """Rows 0-2: anand_vihar, rows 3-5: rk_puram; three hours each."""
    readings = readings_frame([("anand_vihar", "2024-01-01 10:00", 10.0),
                               ("anand_vihar", "2024-01-01 12:00", 30.0),
                               ("rk_puram", "2024-01-01 11:00", 20.0)])
    return to_hourly(readings, DELHI_HOURS, CEILING)


def test_grid_check_accepts_what_to_hourly_produces() -> None:
    hourly = two_station_grid()
    check_complete_grid(hourly)  # Then: no GridError


def test_grid_check_rejects_a_missing_hour() -> None:
    hourly = two_station_grid().drop(index=4)
    with pytest.raises(GridError, match="rk_puram"):
        check_complete_grid(hourly)


def test_grid_check_rejects_a_repeated_hour() -> None:
    grid = two_station_grid()
    hourly = pd.concat([grid, grid.iloc[[4]]]).sort_values(["slug", "hour_end_utc"])
    with pytest.raises(GridError, match="rk_puram"):
        check_complete_grid(hourly)


def test_grid_check_rejects_stations_covering_different_hours() -> None:
    hourly = two_station_grid().drop(index=5)
    with pytest.raises(GridError, match="rk_puram"):
        check_complete_grid(hourly)
