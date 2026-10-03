"""Tests for the CPCB National AQI calculation (src/delhi_pm25/aqi.py)."""

import math

import numpy as np
import pandas as pd
import pytest

from delhi_pm25.aqi import aqi_from_hourly, sub_index


@pytest.mark.parametrize(("pollutant", "concentration", "expected"), [
    ("pm25", 30.0, 50.0),    # top of "Good"
    ("pm25", 45.0, 75.0),    # half-way through "Satisfactory" (30-60 -> 50-100)
    ("pm25", 250.0, 400.0),  # top of "Very Poor"
    ("pm10", 100.0, 100.0),
    ("co", 2.0, 100.0),      # CO is in mg/m3
    ("o3", 168.0, 200.0),
])
def test_sub_index_interpolates_linearly_between_cpcb_breakpoints(
    pollutant: str, concentration: float, expected: float,
) -> None:
    assert sub_index(pollutant, np.array([concentration]))[0] == pytest.approx(expected)


def test_sub_index_is_capped_at_500() -> None:
    assert sub_index("pm25", np.array([1000.0]))[0] == 500.0


def test_sub_index_of_missing_reading_stays_missing() -> None:
    assert math.isnan(sub_index("pm25", np.array([np.nan]))[0])


def hourly_frame(hours: int, **columns: float) -> pd.DataFrame:
    index = pd.date_range("2024-11-01", periods=hours, freq="h")
    return pd.DataFrame({name: np.full(hours, value) for name, value in columns.items()}, index=index)


def test_aqi_is_the_worst_sub_index_and_names_it() -> None:
    # Given: 24 full hours of PM2.5 = 45 (75), PM10 = 300 (250), NO2 = 40 (50)
    hourly = hourly_frame(24, pm25=45.0, pm10=300.0, no2=40.0)
    # When
    result = aqi_from_hourly(hourly).iloc[-1]
    # Then
    assert (result["aqi"], result["prominent"]) == (pytest.approx(250.0), "pm10")


def test_24h_average_needs_16_valid_hours() -> None:
    # Given: PM2.5 present in only 15 of the last 24 hours
    hourly = hourly_frame(24, pm25=45.0, pm10=300.0, no2=40.0)
    hourly.loc[hourly.index[:9], "pm25"] = np.nan
    # When
    result = aqi_from_hourly(hourly).iloc[-1]
    # Then
    assert math.isnan(result["si_pm25"])


def test_aqi_needs_three_pollutants() -> None:
    # Given: only PM2.5 and PM10 measured
    hourly = hourly_frame(24, pm25=45.0, pm10=300.0)
    # When
    result = aqi_from_hourly(hourly).iloc[-1]
    # Then
    assert math.isnan(result["aqi"])


def test_aqi_needs_pm25_or_pm10_among_them() -> None:
    # Given: three gases but no particulate matter
    hourly = hourly_frame(24, no2=40.0, so2=40.0, co=1.0)
    # When
    result = aqi_from_hourly(hourly).iloc[-1]
    # Then
    assert math.isnan(result["aqi"])
