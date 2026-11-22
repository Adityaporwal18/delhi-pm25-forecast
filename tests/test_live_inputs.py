"""Tests for the pure parts of the live inputs (src/delhi_pm25/live_inputs.py)."""

import pandas as pd
import pytest

from delhi_pm25.live_inputs import LiveInputError, check_grid, newest_sensors, weather_rows
from delhi_pm25.weather import SOURCES


def sensor(sensor_id: int, parameter: str, last_utc: str | None) -> dict[str, object]:
    """One entry of /v3/locations/{id}/sensors (the fields we use)."""
    return {"id": sensor_id, "parameter": {"name": parameter},
            "datetimeLast": None if last_utc is None else {"utc": last_utc}}


def test_each_parameter_gets_its_most_recently_reporting_sensor() -> None:
    # Given: an old and a current PM2.5 sensor, a PM10 sensor, an ozone sensor and a dead NO2 sensor
    sensors = [sensor(1, "pm25", "2022-01-01T00:00:00Z"), sensor(2, "pm25", "2026-11-21T09:00:00Z"),
               sensor(3, "pm10", "2026-11-21T09:00:00Z"), sensor(4, "o3", "2026-11-21T09:00:00Z"),
               sensor(5, "no2", None)]
    # When / Then: only the parameters asked for, each from its newest sensor; none for a dead one
    assert newest_sensors(sensors, ("pm25", "pm10", "no2")) == {"pm25": 2, "pm10": 3}


def test_open_meteo_hours_become_the_weather_table_the_features_read() -> None:
    # Given: two hours of the forecast API's response for one grid cell
    hourly = {"time": ["2026-11-21T08:00", "2026-11-21T09:00"]} | {v: [1.0, 2.0] for v in SOURCES["actual_ecmwf_ifs"]}
    # When
    table = weather_rows({"hourly": hourly}, ["r_k_puram_dpcc", "sirifort_cpcb"])
    # Then: one row per station and hour, in UTC, with boundary-layer height left blank
    assert (len(table), str(table["time_utc"].dt.tz), table["temperature_2m"].tolist()[:2],
            table["boundary_layer_height"].isna().all()) == (4, "UTC", [1.0, 2.0], True)
    assert table["time_utc"].iloc[0] == pd.Timestamp("2026-11-21 08:00", tz="UTC")


def test_weather_from_another_grid_cell_is_refused() -> None:
    # Given: the forecast API snapped to a different cell than the one the station trained on
    answer = {"latitude": 28.5, "longitude": 77.25, "hourly": {}}
    # When / Then
    with pytest.raises(LiveInputError, match="grid"):
        check_grid(answer, (28.576448, 77.18678))
