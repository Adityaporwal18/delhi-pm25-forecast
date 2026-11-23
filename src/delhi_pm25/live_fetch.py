"""Live forecasts: fetch the last LIVE_DAYS of readings and weather for our stations.

Readings come from OpenAQ (config/openaq_sensors.csv; needs the free key), a few stations at a
time: slow answers overlap instead of adding up, while one shared rate limiter keeps every thread
together under the free key's 60 requests a minute. The whole fetch has a FETCH_MINUTES budget,
so a slow spell stops it with a clear reason, well inside the scheduled job's 40-minute limit.
Readings are written in the CPCB file layout (data/live/raw/<slug>.csv) and read back with the
training loader, so they reach the features exactly as training data did. Weather comes from
Open-Meteo's forecast API on the stations' training grid cells.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final

import pandas as pd
import requests

from delhi_pm25.live import LIVE_DAYS
from delhi_pm25.live_inputs import (
    FORECAST_API,
    SPACING_S,
    WEATHER_VARIABLES,
    Deadline,
    OpenAQ,
    RateLimiter,
    check_grid,
    get_json,
    weather_rows,
)
from delhi_pm25.openaq import StationIdentity, api_rows, station_table
from delhi_pm25.paths import LIVE_DIR, PROJECT_ROOT, RAW_WEATHER_DIR, STATIONS_CSV
from delhi_pm25.raw_cpcb import load_raw

SENSORS_CSV: Final = PROJECT_ROOT / "config" / "openaq_sensors.csv"
CELLS_CSV: Final = RAW_WEATHER_DIR / "station_cells.csv"
WORKERS: Final = 4
FETCH_MINUTES: Final = 25


def fetch_readings(key: str, since: pd.Timestamp) -> list[Path]:
    """Each station's recent readings in the CPCB file layout; returns the files written."""
    client = OpenAQ(key, RateLimiter(SPACING_S), Deadline(FETCH_MINUTES * 60))
    names = pd.read_csv(STATIONS_CSV).set_index("slug")

    def one_station(station: tuple[str, pd.DataFrame]) -> Path | None:
        slug, sensors = station
        rows = pd.concat([api_rows(client.measurements(int(sensor), since)) for sensor in sensors["sensor_id"]],
                         ignore_index=True)
        if rows.empty:
            print(f"{slug}: no readings since {since:%Y-%m-%d %H:%M} UTC", flush=True)
            return None
        identity = StationIdentity(names.loc[slug, "station_id"], names.loc[slug, "station_name"].strip())
        table = station_table(rows, identity)
        path = LIVE_DIR / "raw" / f"{slug}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(path.with_suffix(".part"), index=False)
        path.with_suffix(".part").rename(path)
        print(f"{slug}: {len(table)} readings, newest {table['Timestamp'].max()[:16]} Delhi time", flush=True)
        return path

    with ThreadPoolExecutor(WORKERS) as pool:
        written = list(pool.map(one_station, pd.read_csv(SENSORS_CSV).groupby("slug")))
    return [path for path in written if path is not None]


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
