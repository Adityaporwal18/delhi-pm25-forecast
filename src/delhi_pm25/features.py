"""Stage 3: one row per station per forecast hour t, with only what is known at t.

t is the END of the latest complete hour (`hour_end_utc`). Every feature uses information
known at t, plus the calendar of the target hour (known in advance). The target is the
station's value for the hour ending t + horizon; it stays blank when that hour was not
measured and is never filled. tests/test_leakage.py checks every feature column for
information from after t. Assumes the complete hourly grid from cleaning (k rows = k hours).
"""

import math
from typing import Final

import numpy as np
import pandas as pd

from delhi_pm25.clean import HOUR
from delhi_pm25.config import DiwaliWindow, FeatureSettings, PipelineConfig
from delhi_pm25.weather import weather_features

DELHI: Final = "Asia/Kolkata"
NON_FEATURE_COLUMNS: Final = ("hour_end_utc", "target_hour_end_utc", "target")
CITY_WINDOW_HOURS: Final = 24
LIMIT_WINDOW_HOURS: Final = 24


class FeatureError(Exception):
    """A setting the features need is missing from config/pipeline.toml."""


def _trailing_mean(values: pd.Series, hours: int, need: int) -> pd.Series:
    return values.rolling(hours, min_periods=need).mean()


def _trailing_max(values: pd.Series, hours: int) -> pd.Series:
    return values.rolling(hours, min_periods=1).max()


def station_history(hourly: pd.DataFrame, settings: FeatureSettings, target: str) -> pd.DataFrame:
    """A: the station's own past values. B: trailing means. G: other pollutants now, data quality."""
    slug = hourly["slug"]
    values = hourly[target].groupby(slug, observed=True)
    out = {f"{target}_lag_{k}h": values.shift(k) for k in settings.lags_hours}
    for hours in settings.rolling_hours:
        need = math.ceil(hours * settings.rolling_min_share)
        out[f"{target}_mean_{hours}h"] = values.transform(_trailing_mean, hours=hours, need=need)
    for pollutant in settings.other_pollutants:
        out[f"{pollutant}_now"] = hourly[pollutant]
    out[f"n_{target}_now"] = hourly[f"n_{target}"]
    last_seen = hourly["hour_end_utc"].where(hourly[target].notna()).groupby(slug, observed=True).ffill()
    out[f"hours_since_{target}"] = (hourly["hour_end_utc"] - last_seen) / HOUR
    at_limit = hourly[f"{target}_at_ceiling"].astype("float32").groupby(slug, observed=True)
    out[f"{target}_hit_limit_24h"] = at_limit.transform(_trailing_max, hours=LIMIT_WINDOW_HOURS)
    return pd.DataFrame(out, index=hourly.index)


def city_features(hourly: pd.DataFrame, target: str) -> pd.DataFrame:
    """C: the city-wide level from the stations reporting at t, and this station's excess over it."""
    values = hourly[target]
    by_hour = values.groupby(hourly["hour_end_utc"])
    median = by_hour.transform("median")
    city = by_hour.median().sort_index()
    city_mean = city.rolling(CITY_WINDOW_HOURS, min_periods=CITY_WINDOW_HOURS // 2).mean()
    return pd.DataFrame({
        f"city_{target}_median": median,
        f"city_{target}_n_stations": by_hour.transform("count"),
        f"city_{target}_median_mean_24h": hourly["hour_end_utc"].map(city_mean),
        f"{target}_minus_city": values - median,
    }, index=hourly.index)


def _in_diwali_window(start: pd.Series, diwali: DiwaliWindow) -> pd.Series:
    """1 when the target hour starts inside a Diwali window (Delhi time), else 0."""
    missing = {int(year) for year in start.dt.year.unique()} - {day.year for day in diwali.dates}
    if missing:
        raise FeatureError(
            f"No Diwali date for {sorted(missing)}: add it to [features.diwali] dates in config/pipeline.toml"
        )
    inside = pd.Series(False, index=start.index)
    for day in diwali.dates:
        opens = pd.Timestamp(day.isoformat(), tz=DELHI) + pd.Timedelta(hours=diwali.start_hour_ist)
        inside |= (start >= opens) & (start < opens + pd.Timedelta(hours=diwali.hours))
    return inside.astype("int8")


def calendar_features(target_end: pd.Series, settings: FeatureSettings) -> pd.DataFrame:
    """D: clock time and season of the TARGET hour. E: event windows. All known in advance."""
    start = (target_end - HOUR).dt.tz_convert(DELHI)
    clock = start.dt.hour + start.dt.minute / 60
    year_days = np.where(start.dt.is_leap_year, 366, 365)
    season = (start.dt.dayofyear - 1 + clock / 24) / year_days
    first, last = settings.stubble_season
    return pd.DataFrame({
        "target_hour_sin": np.sin(2 * np.pi * clock / 24),
        "target_hour_cos": np.cos(2 * np.pi * clock / 24),
        "target_doy_sin": np.sin(2 * np.pi * season),
        "target_doy_cos": np.cos(2 * np.pi * season),
        "target_in_diwali_window": _in_diwali_window(start, settings.diwali),
        "target_in_stubble_season": (start.dt.month * 100 + start.dt.day).between(first, last).astype("int8"),
    }, index=target_end.index)


def build_features(hourly: pd.DataFrame, weather: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """The feature table: keys, features (groups A-G), target hour and target."""
    settings, target = config.features, config.target
    ordered = hourly.sort_values(["slug", "hour_end_utc"], ignore_index=True)
    keys = ordered[["slug", "hour_end_utc"]]
    target_end = ordered["hour_end_utc"] + settings.horizon_hours * HOUR
    table = pd.concat([
        keys,
        station_history(ordered, settings, target),
        city_features(ordered, target),
        calendar_features(target_end, settings),
        weather_features(keys, weather),
    ], axis=1)
    table["target_hour_end_utc"] = target_end
    table["target"] = ordered[target].groupby(ordered["slug"], observed=True).shift(-settings.horizon_hours)
    floats = table.select_dtypes("float64").columns
    return table.astype(dict.fromkeys(floats, "float32"))


def horizon_view(features: pd.DataFrame, hours: int, config: PipelineConfig) -> pd.DataFrame:
    """The feature table re-aimed `hours` ahead (stage 7 serves several horizons): the target,
    its hour and the calendar of the target hour change; everything known at the forecast hour
    stays. Rows must be in station, then time order on a complete grid (as build_features
    returns them)."""
    target_end = features["hour_end_utc"] + hours * HOUR
    calendar = calendar_features(target_end, config.features)
    calendar = calendar.astype({name: "float32" for name in calendar.select_dtypes("float64").columns})
    later = features[f"{config.target}_lag_0h"].groupby(features["slug"], observed=True).shift(-hours)
    return features.assign(target_hour_end_utc=target_end, target=later, **{name: calendar[name] for name in calendar.columns})
