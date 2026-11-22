"""Live forecasts, stage C: features for the latest hour, from the last 10 days of live data.

1. readings  the last LIVE_DAYS of PM2.5, PM10, NO2 and CO for our 37 stations from OpenAQ
             (sensors in config/openaq_sensors.csv; needs OPENAQ_API_KEY), written in the CPCB
             file layout (data/live/raw/<slug>.csv) and read back with the training loader
2. weather   Open-Meteo forecast API, ECMWF IFS, the stations' training grid cells
3. features  live.live_features: the training steps (to_hourly, complete grid, D4 rules,
             build_features) for the latest hour at least half the stations reported

Output:  data/live/features_latest.parquet (one row per station)
Usage:   .venv/bin/python scripts/13_live_features.py   (about 150 OpenAQ requests: ~3 minutes)
"""

import os
import sys
from pathlib import Path
from typing import Final

import pandas as pd
import requests

from delhi_pm25.clean import IST_OFFSET, GridError
from delhi_pm25.config import ConfigError, load_config
from delhi_pm25.features import FeatureError
from delhi_pm25.guards import InputsOutOfDate
from delhi_pm25.live import LIVE_DAYS, live_features
from delhi_pm25.live_inputs import (
    FORECAST_API,
    WEATHER_VARIABLES,
    LiveInputError,
    check_grid,
    fetch_measurements,
    get_json,
    weather_rows,
)
from delhi_pm25.openaq import OpenAQFormatError, StationIdentity, api_rows, station_table
from delhi_pm25.paths import PIPELINE_TOML, PROJECT_ROOT, RAW_WEATHER_DIR, STATIONS_CSV
from delhi_pm25.raw_cpcb import RawFormatError, load_raw

SENSORS_CSV: Final = PROJECT_ROOT / "config" / "openaq_sensors.csv"
CELLS_CSV: Final = RAW_WEATHER_DIR / "station_cells.csv"
LIVE_DIR: Final = PROJECT_ROOT / "data" / "live"
OUT: Final = LIVE_DIR / "features_latest.parquet"


def fetch_readings(key: str, since: pd.Timestamp) -> list[Path]:
    """Each station's recent readings in the CPCB file layout; returns the files written."""
    names = pd.read_csv(STATIONS_CSV).set_index("slug")
    session = requests.Session()
    session.headers["X-API-Key"] = key
    paths = []
    for slug, group in pd.read_csv(SENSORS_CSV).groupby("slug"):
        rows = pd.concat([api_rows(fetch_measurements(session, int(sensor), since)) for sensor in group["sensor_id"]],
                         ignore_index=True)
        if rows.empty:
            print(f"{slug}: no readings since {since:%Y-%m-%d %H:%M} UTC", flush=True)
            continue
        identity = StationIdentity(names.loc[slug, "station_id"], names.loc[slug, "station_name"].strip())
        table = station_table(rows, identity)
        path = LIVE_DIR / "raw" / f"{slug}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(path.with_suffix(".part"), index=False)
        path.with_suffix(".part").rename(path)
        paths.append(path)
        print(f"{slug}: {len(table)} readings, newest {table['Timestamp'].max()[:16]} Delhi time", flush=True)
    return paths


def fetch_weather(slugs: list[str]) -> pd.DataFrame:
    cells = pd.read_csv(CELLS_CSV)
    cells = cells[(cells["source"] == "actual_ecmwf_ifs") & cells["slug"].isin(slugs)]
    session, parts = requests.Session(), []
    for (lat, lon), group in cells.groupby(["grid_lat", "grid_lon"]):
        params = {"latitude": lat, "longitude": lon, "hourly": ",".join(WEATHER_VARIABLES), "models": "ecmwf_ifs",
                  "past_days": LIVE_DAYS + 1, "forecast_days": 1, "timezone": "GMT", "wind_speed_unit": "ms"}
        answer = get_json(session, FORECAST_API, params)
        check_grid(answer, (lat, lon))
        parts.append(weather_rows(answer, list(group["slug"])))
    return pd.concat(parts, ignore_index=True)


def summarise(features: pd.DataFrame, readings: pd.DataFrame) -> None:
    hour = features["hour_end_utc"].iloc[0]
    newest = (readings.groupby("slug", observed=True)["ts_label"].max() - IST_OFFSET).dt.tz_localize("UTC")
    age = (pd.Timestamp.now(tz="UTC") - newest).dt.total_seconds() / 3600
    print(f"\nForecast hour: ends {hour} ({(hour + IST_OFFSET).tz_localize(None):%d %b %H:%M} Delhi time)")
    print(f"stations with PM2.5 in that hour: {int(features['pm25_lag_0h'].notna().sum())} of {len(features)}")
    print(f"newest reading per station, hours old: min {age.min():.1f}, median {age.median():.1f}, max {age.max():.1f}")
    print(f"feature columns: {features.shape[1]}; blank values in the key ones: "
          f"{features[['pm25_lag_0h', 'pm25_lag_24h', 'pm25_mean_168h', 'city_pm25_median', 'wx_temperature']].isna().sum().to_dict()}")


def main() -> int:
    key = os.environ.get("OPENAQ_API_KEY", "")
    if not key:
        print("STOPPED: set OPENAQ_API_KEY (free key from explore.openaq.org/register)", file=sys.stderr)
        return 1
    try:
        config = load_config(PIPELINE_TOML)
        since = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=LIVE_DAYS)).floor("h")
        paths = fetch_readings(key, since)
        stations = pd.read_csv(STATIONS_CSV)
        ours = stations[stations["slug"].isin(pd.read_csv(SENSORS_CSV)["slug"])]
        readings = load_raw(paths, ours).readings
        features = live_features(readings, fetch_weather(sorted(ours["slug"])), config)
    except (ConfigError, LiveInputError, OpenAQFormatError, RawFormatError, GridError, InputsOutOfDate, FeatureError) as err:
        print(f"STOPPED: {err}", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(OUT, index=False)
    summarise(features, readings)
    print(f"Wrote {OUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
