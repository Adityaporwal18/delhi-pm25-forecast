"""Unit tests for the Stage 3 features (src/delhi_pm25/features.py and weather.py)."""

import numpy as np
import pandas as pd
import pytest

from delhi_pm25.config import PipelineConfig
from delhi_pm25.features import FeatureError, calendar_features, city_features, station_history
from delhi_pm25.guards import InputsOutOfDate
from delhi_pm25.raw_cpcb import POLLUTANTS
from delhi_pm25.weather import SOURCES, weather_features

START = pd.Timestamp("2024-11-01 00:30", tz="UTC")
WX_TIMES = pd.date_range("2024-11-01 00:00", periods=30, freq="h", tz="UTC", unit="us")
NAN = np.nan


def hourly_grid(pm25: dict[str, list[float]]) -> pd.DataFrame:
    """A complete hourly grid as 05_clean.py writes it: one station after another, from START."""
    parts = [
        pd.DataFrame({"slug": slug, "hour_end_utc": pd.date_range(START, periods=len(values), freq="h", unit="us"),
                      "pm25": values})
        for slug, values in pm25.items()
    ]
    hourly = pd.concat(parts, ignore_index=True)
    hourly["slug"] = pd.Categorical(hourly["slug"], categories=list(pm25))
    for pollutant in (p for p in POLLUTANTS if p != "pm25"):
        hourly[pollutant] = 1.0
    hourly["n_pm25"] = np.where(hourly["pm25"].notna(), 4, 0).astype("int8")
    hourly["pm25_at_ceiling"] = hourly["pm25"] >= 1000
    return hourly


def target_hours(*ends_utc: str) -> pd.Series:
    return pd.Series(pd.DatetimeIndex(list(ends_utc), tz="UTC").as_unit("us"))


def calm_weather() -> pd.DataFrame:
    """Weather for station 'a' over WX_TIMES, every variable 1.0."""
    weather = pd.DataFrame({"slug": "a", "time_utc": WX_TIMES})
    for variable in (v for variables in SOURCES.values() for v in variables):
        weather[variable] = 1.0
    return weather


def keys_at(*ends_utc: str) -> pd.DataFrame:
    return pd.DataFrame({"slug": pd.Categorical(["a"] * len(ends_utc)), "hour_end_utc": target_hours(*ends_utc)})


def test_lags_never_reach_into_another_station(config: PipelineConfig) -> None:
    # Given: two stations, four hours each
    hourly = hourly_grid({"a": [1.0, 2.0, 3.0, 4.0], "b": [5.0, 6.0, 7.0, 8.0]})
    # When
    history = station_history(hourly, config.features, "pm25")
    # Then: a value from 3 hours earlier exists only for each station's 4th hour
    assert history["pm25_lag_3h"].fillna(-1).tolist() == [-1, -1, -1, 1.0, -1, -1, -1, 5.0]


def test_rolling_mean_needs_at_least_half_the_window(config: PipelineConfig) -> None:
    # Given: 6-hour windows holding 2 values (too thin) and 3 values (exactly half)
    hourly = hourly_grid({"thin": [10.0, NAN, NAN, NAN, NAN, 20.0], "half": [10.0, NAN, NAN, NAN, 30.0, 20.0]})
    # When
    history = station_history(hourly, config.features, "pm25")
    # Then
    assert history["pm25_mean_6h"].iloc[[5, 11]].fillna(-1).tolist() == [-1, 20.0]


def test_hours_since_last_value_counts_up_through_a_gap(config: PipelineConfig) -> None:
    history = station_history(hourly_grid({"a": [10.0, NAN, NAN, 20.0]}), config.features, "pm25")
    assert history["hours_since_pm25"].tolist() == [0.0, 1.0, 2.0, 0.0]


def test_limit_flag_stays_on_for_24_hours(config: PipelineConfig) -> None:
    history = station_history(hourly_grid({"a": [1000.0] + [50.0] * 24}), config.features, "pm25")
    assert history["pm25_hit_limit_24h"].tolist() == [1.0] * 24 + [0.0]


def test_city_median_uses_only_the_stations_that_reported(config: PipelineConfig) -> None:
    # Given: one hour, station b has no value
    hourly = hourly_grid({"a": [100.0], "b": [NAN], "c": [300.0]})
    # When
    city = city_features(hourly, "pm25").iloc[0]
    # Then
    assert [city["city_pm25_median"], city["city_pm25_n_stations"], city["pm25_minus_city"]] == [200.0, 2, -100.0]


@pytest.mark.parametrize(
    ("end_utc", "inside"),
    [
        pytest.param("2024-10-31 12:30", 0, id="17:00 IST on Diwali"),
        pytest.param("2024-10-31 13:30", 1, id="18:00 IST on Diwali"),
        pytest.param("2024-11-01 06:30", 1, id="11:00 IST next day"),
        pytest.param("2024-11-01 07:30", 0, id="12:00 IST next day"),
    ],
)
def test_diwali_window_is_judged_on_the_target_hour_in_delhi_time(
    config: PipelineConfig, end_utc: str, inside: int
) -> None:
    calendar = calendar_features(target_hours(end_utc), config.features)
    assert calendar["target_in_diwali_window"].tolist() == [inside]


@pytest.mark.parametrize(("day", "inside"), [("2024-10-14", 0), ("2024-10-15", 1), ("2024-11-15", 1), ("2024-11-16", 0)])
def test_stubble_season_includes_both_end_days(config: PipelineConfig, day: str, inside: int) -> None:
    calendar = calendar_features(target_hours(f"{day} 06:30"), config.features)
    assert calendar["target_in_stubble_season"].tolist() == [inside]


def test_a_year_without_a_diwali_date_stops_with_a_clear_message(config: PipelineConfig) -> None:
    with pytest.raises(FeatureError, match="Diwali"):
        calendar_features(target_hours("2027-06-01 06:30"), config.features)


def test_hour_of_day_is_a_point_on_a_circle(config: PipelineConfig) -> None:
    # Given: a target hour that starts at 06:00 Delhi time, a quarter of the way round the clock
    calendar = calendar_features(target_hours("2024-01-01 01:30"), config.features)
    # Then
    assert calendar["target_hour_sin"].iloc[0] == pytest.approx(1.0)


def test_weather_comes_from_the_last_whole_hour_before_the_forecast() -> None:
    # Given: temperature equal to the hour number, and a forecast made at 05:30 UTC
    weather = calm_weather()
    weather["temperature_2m"] = np.arange(30.0)
    # When
    features = weather_features(keys_at("2024-11-01 05:30"), weather)
    # Then: the 05:00 value, 30 minutes before the forecast
    assert features["wx_temperature"].tolist() == [5.0]


def test_wind_from_the_east_blows_towards_the_west() -> None:
    weather = calm_weather()
    weather["wind_direction_10m"] = 90.0
    weather["wind_speed_10m"] = 2.0
    features = weather_features(keys_at("2024-11-01 05:30"), weather).iloc[0]
    assert (features["wx_wind_u"], features["wx_wind_v"]) == pytest.approx((-2.0, 0.0), abs=1e-9)


def test_ventilation_is_mixing_depth_times_wind_speed() -> None:
    weather = calm_weather()
    weather["boundary_layer_height"] = 500.0
    weather["wind_speed_10m"] = 2.0
    assert weather_features(keys_at("2024-11-01 05:30"), weather)["wx_ventilation"].tolist() == [1000.0]


def test_rain_is_summed_over_the_last_24_hours() -> None:
    features = weather_features(keys_at("2024-11-02 01:30"), calm_weather())
    assert features["wx_rain_sum_24h"].tolist() == [24.0]


def test_missing_weather_stops_with_the_command_that_fetches_it() -> None:
    with pytest.raises(InputsOutOfDate, match="02_fetch_weather"):
        weather_features(keys_at("2024-11-05 05:30"), calm_weather())
