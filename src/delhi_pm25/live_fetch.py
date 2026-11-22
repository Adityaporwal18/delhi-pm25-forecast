"""Live forecasts: fetch the last LIVE_DAYS of readings and weather for our stations.

Readings come from OpenAQ (config/openaq_sensors.csv; needs the free key), are written in the
CPCB file layout (data/live/raw/<slug>.csv) and read back with the training loader, so they
reach the features exactly as training data did. Weather comes from Open-Meteo's forecast API
on the stations' training grid cells.
"""

from pathlib import Path
from typing import Final

import pandas as pd
import requests

from delhi_pm25.live import LIVE_DAYS
from delhi_pm25.live_inputs import FORECAST_API, WEATHER_VARIABLES, check_grid, fetch_measurements, get_json, weather_rows
from delhi_pm25.openaq import StationIdentity, api_rows, station_table
from delhi_pm25.paths import LIVE_DIR, PROJECT_ROOT, RAW_WEATHER_DIR, STATIONS_CSV
from delhi_pm25.raw_cpcb import load_raw

SENSORS_CSV: Final = PROJECT_ROOT / "config" / "openaq_sensors.csv"
CELLS_CSV: Final = RAW_WEATHER_DIR / "station_cells.csv"


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


def fetch_live(key: str, now: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(readings as load_raw returns them, weather as weather_features reads it) for our stations."""
    paths = fetch_readings(key, (now - pd.Timedelta(days=LIVE_DAYS)).floor("h"))
    stations = pd.read_csv(STATIONS_CSV)
    ours = stations[stations["slug"].isin(pd.read_csv(SENSORS_CSV)["slug"])]
    return load_raw(paths, ours).readings, fetch_weather(sorted(ours["slug"]))
