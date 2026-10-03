"""Leakage test: no feature at hour t may change when anything after t changes.

build_features runs twice on the same synthetic data: once as it is, once with every
pollution and weather value after hour T0 changed. Every feature column at the hours up
to T0 must come out identical. The check covers every column build_features returns, so a
feature added later (in code or through config/pipeline.toml) is checked automatically.
"""

import numpy as np
import pandas as pd
import pytest

from delhi_pm25.config import load_config
from delhi_pm25.feature_notes import feature_notes
from delhi_pm25.features import NON_FEATURE_COLUMNS, build_features
from delhi_pm25.paths import PIPELINE_TOML
from delhi_pm25.raw_cpcb import POLLUTANTS
from delhi_pm25.weather import SOURCES

CONFIG = load_config(PIPELINE_TOML)
TARGET = CONFIG.target
HORIZON = CONFIG.features.horizon_hours
STATIONS = ["a", "b", "c"]
HOURS = pd.date_range("2024-10-25 00:30", periods=400, freq="h", tz="UTC", unit="us")
T0 = HOURS[250]
RNG = np.random.default_rng(7)


def synthetic_hourly() -> pd.DataFrame:
    """Cleaned hourly rows as 05_clean.py writes them, with random values and gaps."""
    parts = []
    for slug in STATIONS:
        part = pd.DataFrame({"slug": slug, "hour_end_utc": HOURS})
        for pollutant in POLLUTANTS:
            values = RNG.gamma(2.0, 60.0, len(HOURS)).astype("float32")
            values[RNG.random(len(HOURS)) < 0.05] = np.nan
            part[pollutant] = values
            readings = np.where(np.isnan(values), 0, RNG.integers(1, 5, len(HOURS)))
            part[f"n_{pollutant}"] = readings.astype("int8")
        for pollutant in ("pm25", "pm10"):
            part[f"{pollutant}_at_ceiling"] = RNG.random(len(HOURS)) < 0.02
        parts.append(part)
    hourly = pd.concat(parts, ignore_index=True)
    hourly["slug"] = pd.Categorical(hourly["slug"], categories=STATIONS)
    return hourly


def synthetic_weather() -> pd.DataFrame:
    """Weather per station on whole UTC hours, from a week before the first forecast hour."""
    first = HOURS[0].floor("h") - pd.Timedelta(days=7)
    times = pd.date_range(first, HOURS[-1].ceil("h"), freq="h", unit="us")
    parts = []
    for slug in STATIONS:
        part = pd.DataFrame({"slug": slug, "time_utc": times})
        for variables in SOURCES.values():
            for variable in variables:
                part[variable] = RNG.uniform(0.0, 360.0, len(times))
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def changed_after(frame: pd.DataFrame, time_column: str) -> pd.DataFrame:
    """A copy with every measured value after T0 changed; times and stations kept."""
    changed = frame.copy()
    later = frame[time_column] > T0
    for column in frame.columns.drop(["slug", time_column]):
        values = frame[column]
        match values.dtype.kind:
            case "f":
                changed[column] = values.mask(later, (values * 3 + 17).fillna(42.0))
            case "i":
                changed[column] = values.mask(later, (values + 1) % 5).astype(values.dtype)
            case "b":
                changed[column] = values.mask(later, ~values)
            case kind:
                raise AssertionError(f"no rule to change {column} (dtype kind {kind!r})")
    return changed


def centred_mean(hourly: pd.DataFrame) -> pd.Series:
    """A deliberately leaky feature: a 5-hour mean centred on t, so it uses t+1 and t+2."""
    by_station = hourly.groupby("slug", observed=True)[TARGET]
    return by_station.transform(lambda values: values.rolling(5, center=True, min_periods=1).mean())


HOURLY, WEATHER = synthetic_hourly(), synthetic_weather()
BEFORE = build_features(HOURLY, WEATHER, CONFIG)
AFTER = build_features(changed_after(HOURLY, "hour_end_utc"), changed_after(WEATHER, "time_utc"), CONFIG)
FEATURE_COLUMNS = [column for column in BEFORE.columns if column not in NON_FEATURE_COLUMNS]
KNOWN = BEFORE["hour_end_utc"] <= T0


@pytest.mark.parametrize("column", FEATURE_COLUMNS)
def test_feature_ignores_everything_after_its_forecast_hour(column: str) -> None:
    # Given: BEFORE and AFTER differ only in values after T0
    # Then: the feature is identical at every hour up to T0
    pd.testing.assert_series_equal(AFTER.loc[KNOWN, column], BEFORE.loc[KNOWN, column])


@pytest.mark.parametrize("column", FEATURE_COLUMNS)
def test_feature_has_values_so_its_check_is_not_empty(column: str) -> None:
    assert BEFORE.loc[KNOWN, column].notna().any()


def test_the_check_catches_a_centred_window() -> None:
    # Given: the leaky centred mean, built from the original and the changed data
    known = HOURLY["hour_end_utc"] <= T0
    # When
    leaky_before = centred_mean(HOURLY)[known]
    leaky_after = centred_mean(changed_after(HOURLY, "hour_end_utc"))[known]
    # Then: the comparison used above sees it change before T0
    assert not leaky_before.equals(leaky_after)


def test_the_change_after_t0_reaches_the_target() -> None:
    assert not BEFORE.loc[KNOWN, "target"].equals(AFTER.loc[KNOWN, "target"])


def test_only_time_stamps_and_the_target_are_exempt_from_the_check() -> None:
    assert set(NON_FEATURE_COLUMNS) == {"hour_end_utc", "target_hour_end_utc", "target"}


def test_target_is_the_station_value_horizon_hours_later() -> None:
    station = BEFORE[BEFORE["slug"] == "a"]
    values = HOURLY.loc[HOURLY["slug"] == "a", TARGET].to_numpy()
    np.testing.assert_array_equal(station["target"].to_numpy()[:-HORIZON], values[HORIZON:])
    assert station["target"].iloc[-HORIZON:].isna().all()


def test_target_hour_is_horizon_hours_after_the_forecast_hour() -> None:
    gap = BEFORE["target_hour_end_utc"] - BEFORE["hour_end_utc"]
    assert (gap == pd.Timedelta(hours=HORIZON)).all()


def test_every_feature_has_a_plain_language_note() -> None:
    assert feature_notes(FEATURE_COLUMNS, TARGET)["feature"].tolist() == FEATURE_COLUMNS
