"""The live path must be the training path: same steps, same features (src/delhi_pm25/live.py)."""

import numpy as np
import pytest
import pandas as pd

from delhi_pm25.clean import check_complete_grid, to_hourly
from delhi_pm25.clean_rules import apply_rules
from delhi_pm25.config import PipelineConfig
from delhi_pm25.features import NON_FEATURE_COLUMNS, build_features
from delhi_pm25.live import LIVE_DAYS, NoForecastHour, latest_hour, live_features
from delhi_pm25.raw_cpcb import MEASUREMENTS
from delhi_pm25.weather import SOURCES

STATIONS = ["a", "b", "c"]
LABELS = pd.date_range("2024-11-01 00:15", "2024-11-16 00:00", freq="15min", unit="us")


def raw_readings(seed: int) -> pd.DataFrame:
    """15-minute readings as load_raw returns them, Delhi-time labels, some blanks."""
    rng = np.random.default_rng(seed)
    parts = []
    for slug in STATIONS:
        frame = pd.DataFrame({column: rng.gamma(2.0, 60.0, len(LABELS)).astype("float32") for column in MEASUREMENTS})
        frame.loc[rng.random(len(LABELS)) < 0.05, "pm25"] = np.nan
        parts.append(frame.assign(slug=slug, ts_label=LABELS))
    readings = pd.concat(parts, ignore_index=True)
    readings["slug"] = pd.Categorical(readings["slug"], categories=STATIONS)
    return readings


def weather() -> pd.DataFrame:
    hours = pd.date_range("2024-10-24", "2024-11-17", freq="h", tz="UTC", unit="us")
    rng = np.random.default_rng(3)
    return pd.concat([pd.DataFrame({"slug": slug, "time_utc": hours} | {v: rng.uniform(0, 360, len(hours))
                      for vs in SOURCES.values() for v in vs}) for slug in STATIONS], ignore_index=True)


def training_path(readings: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """What scripts/05_clean.py and 06_features.py do, written out step by step."""
    hourly = to_hourly(readings, config.hourly, config.ceiling)
    check_complete_grid(hourly)
    return build_features(apply_rules(hourly, config).cleaned, weather(), config)


def test_live_features_equal_the_training_features_for_the_same_hour(config: PipelineConfig) -> None:
    # Given: 15 days of readings; the live path sees only the last LIVE_DAYS of them
    readings = raw_readings(seed=1)
    recent = readings[readings["ts_label"] > LABELS[-1] - pd.Timedelta(days=LIVE_DAYS)]
    # When
    live = live_features(recent, weather(), config)
    trained = training_path(readings, config)
    # Then: the forecast hour's features are identical, column for column
    trained = trained[trained["hour_end_utc"] == live["hour_end_utc"].iloc[0]]
    columns = [c for c in live.columns if c not in NON_FEATURE_COLUMNS]
    pd.testing.assert_frame_equal(live[columns].reset_index(drop=True), trained[columns].reset_index(drop=True))


def test_the_forecast_hour_is_the_latest_hour_most_stations_have_reported(config: PipelineConfig) -> None:
    # Given: station c reports one hour later than a and b
    hourly = to_hourly(raw_readings(seed=2), config.hourly, config.ceiling)
    last = hourly["hour_end_utc"].max()
    hourly.loc[(hourly["hour_end_utc"] == last) & (hourly["slug"] != "c"), "pm25"] = np.nan
    # When / Then: one station of three is not "most", so the forecast is made an hour earlier
    assert latest_hour(hourly, "pm25") == last - pd.Timedelta(hours=1)


def test_a_forecast_needs_an_hour_that_two_thirds_of_the_stations_reported(config: PipelineConfig) -> None:
    # Given: only one station of three ever reports PM2.5
    hourly = to_hourly(raw_readings(seed=3), config.hourly, config.ceiling)
    hourly.loc[hourly["slug"] != "a", "pm25"] = np.nan
    # When / Then: no hour qualifies, so the refresh stops with a reason instead of crashing
    with pytest.raises(NoForecastHour, match="two thirds"):
        latest_hour(hourly, "pm25")
