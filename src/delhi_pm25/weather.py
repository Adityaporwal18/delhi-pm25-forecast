"""Weather features, option (i) chosen 2 Oct 2026: only weather known when the forecast is made.

A forecast made at hour t (an hour END, hh:30 UTC) uses the Open-Meteo values stamped hh:00
UTC, 30 minutes earlier. Temperature, wind, humidity and pressure are instantaneous; rain and
sunshine cover the hour before the stamp, so they are known by t as well. The actual weather
at t + 48 h is never used. Sources: the ECMWF IFS archive (9 variables) and ERA5
boundary-layer height (BLH), which is blank for January-June 2024 (no archive model has it).
"""

from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from delhi_pm25.guards import WEATHER_HISTORY, InputsOutOfDate
from delhi_pm25.paths import RAW_WEATHER_DIR

SOURCES: Final = {
    "actual_ecmwf_ifs": [
        "temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation", "surface_pressure",
        "cloud_cover", "wind_speed_10m", "wind_direction_10m", "shortwave_radiation",
    ],
    "actual_era5_blh": ["boundary_layer_height"],
}
FETCH_COMMAND: Final = ".venv/bin/python scripts/02_fetch_weather.py"
TRAILING: Final = "24h"
TRAILING_MIN_HOURS: Final = 12


def _read_cells(cells: pd.DataFrame, folder: Path, variables: list[str]) -> pd.DataFrame:
    """Every grid-cell file of one source, attached to the stations inside each cell."""
    parts = [
        pd.read_csv(folder / f"{cell}.csv", usecols=["cell_id", "time_utc", *variables])
        for cell in cells["cell_id"].unique()
    ]
    values = pd.concat(parts, ignore_index=True)
    values["time_utc"] = pd.to_datetime(values["time_utc"], utc=True).dt.as_unit("us")
    return cells[["slug", "cell_id"]].merge(values, on="cell_id").drop(columns="cell_id")


def load_station_weather(slugs: list[str], weather_dir: Path = RAW_WEATHER_DIR) -> pd.DataFrame:
    """Hourly weather per station: slug, time_utc and every SOURCES variable."""
    cells = pd.read_csv(weather_dir / "station_cells.csv")
    cells = cells[cells["slug"].isin(slugs)]
    parts = [
        _read_cells(cells[cells["source"] == source], weather_dir / source, variables)
        for source, variables in SOURCES.items()
    ]
    weather = parts[0]
    for part in parts[1:]:
        weather = weather.merge(part, on=["slug", "time_utc"], how="left")
    return weather.sort_values(["slug", "time_utc"], ignore_index=True)


def _trailing(wx: pd.DataFrame, column: str, how: str) -> np.ndarray:
    """Per station, `how` ("mean", "sum" or "min") over the 24 hours up to and including each row.

    `wx` must be sorted by slug, then time: each station's rows are then one block, and the
    results come back in the same row order as `wx`.
    """
    by_station = wx.groupby("slug", sort=False, observed=True)
    rolled = by_station.rolling(TRAILING, on="time_utc", min_periods=TRAILING_MIN_HOURS)[column]
    return rolled.agg(how).to_numpy()


def _check_weather_present(joined: pd.DataFrame) -> None:
    """Stop when a forecast hour has no weather: the weather files must be re-downloaded."""
    missing = joined[joined["wx_temperature"].isna()]
    if missing.empty:
        return
    first = missing.iloc[0]
    start = (joined["time_utc"].min() - WEATHER_HISTORY).date()
    end = joined["time_utc"].max().date()
    raise InputsOutOfDate(
        f"Weather is missing for {len(missing):,} station-hours, e.g. {first['slug']} at "
        f"{first['time_utc']}. Re-download with: {FETCH_COMMAND} --start {start} --end {end} --force"
    )


def weather_features(keys: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Weather at the latest whole hour at or before each forecast hour t, plus 24-hour summaries.

    `keys` holds slug and hour_end_utc (t). Wind direction says where the wind comes FROM
    (90 = from the east), so the wind vector is u = -speed * sin, v = -speed * cos: u > 0 blows
    towards the east, v > 0 towards the north. Unlike a raw angle, this keeps 359 and 1 degrees
    close together.
    """
    wx = weather.sort_values(["slug", "time_utc"], ignore_index=True)
    speed = wx["wind_speed_10m"]
    from_angle = np.deg2rad(wx["wind_direction_10m"])
    table = pd.DataFrame({
        "slug": wx["slug"].astype(str),
        "time_utc": wx["time_utc"].dt.as_unit("us"),
        "wx_temperature": wx["temperature_2m"],
        "wx_rh": wx["relative_humidity_2m"],
        "wx_dew_point": wx["dew_point_2m"],
        "wx_pressure": wx["surface_pressure"],
        "wx_cloud": wx["cloud_cover"],
        "wx_shortwave": wx["shortwave_radiation"],
        "wx_wind_speed": speed,
        "wx_wind_u": -speed * np.sin(from_angle),
        "wx_wind_v": -speed * np.cos(from_angle),
        "wx_wind_speed_mean_24h": _trailing(wx, "wind_speed_10m", "mean"),
        "wx_rain_sum_24h": _trailing(wx, "precipitation", "sum"),
        "wx_blh": wx["boundary_layer_height"],
        "wx_blh_min_24h": _trailing(wx, "boundary_layer_height", "min"),
        "wx_ventilation": wx["boundary_layer_height"] * speed,
    })
    wanted = pd.DataFrame({
        "slug": keys["slug"].astype(str),
        "time_utc": keys["hour_end_utc"].dt.floor("h").dt.as_unit("us"),
    }).reset_index(drop=True)
    joined = wanted.merge(table, on=["slug", "time_utc"], how="left", validate="many_to_one")
    _check_weather_present(joined)
    return joined.drop(columns=["slug", "time_utc"]).set_index(keys.index)
