"""Stage 7: the replay that the API serves, kept apart from the web framework so it is easy to test.

The replay file (scripts/10_horizon_models.py) holds forecasts issued twice a day through the
test year 2025 for every station and horizon, next to what was measured later. Colours use
CPCB's PM2.5 bands. CPCB defines them on 24-hour averages, so on an hourly forecast they are an
approximation: the site calls them a "PM2.5-based category", never AQI.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pandas as pd

CREDITS: Final = (
    "PM2.5 data: Central Pollution Control Board (CPCB), via Vonter/india-cpcb-aqi (ODbL-1.0) "
    "and OpenCity. Weather: Open-Meteo (CC BY 4.0). Map: © OpenStreetMap contributors."
)


@dataclass(frozen=True, slots=True)
class Category:
    label: str
    upper_ug_m3: float
    colour: str


CATEGORIES: Final = (
    Category("Good", 30.0, "#00b050"),
    Category("Satisfactory", 60.0, "#92d050"),
    Category("Moderate", 90.0, "#ffff00"),
    Category("Poor", 120.0, "#ff9900"),
    Category("Very Poor", 250.0, "#ff0000"),
    Category("Severe", math.inf, "#c00000"),
)


class ReplayError(Exception):
    """A request for a station, issue time or horizon that the replay does not hold."""


def category(ug_m3: float) -> Category | None:
    """The CPCB PM2.5 band a value falls in; None for a blank value."""
    if math.isnan(ug_m3):
        return None
    return next(band for band in CATEGORIES if ug_m3 <= band.upper_ug_m3)


@dataclass(frozen=True, slots=True)
class Replay:
    """Rows: slug, issued_utc, horizon_h (0 = the value measured at the issue time), p10, p50,
    p90 (the band and the median forecast) and measured (blank if never measured)."""

    table: pd.DataFrame
    stations: pd.DataFrame

    @classmethod
    def load(cls, replay_path: Path, stations_csv: Path) -> "Replay":
        table = pd.read_parquet(replay_path)
        table["issued_utc"] = pd.to_datetime(table["issued_utc"], utc=True)
        stations = pd.read_csv(stations_csv)
        served = stations[stations["slug"].isin(table["slug"].unique())].sort_values("slug", ignore_index=True)
        return cls(table, served[["slug", "station_name", "latitude", "longitude"]])

    def issue_times(self) -> list[pd.Timestamp]:
        return self.table["issued_utc"].drop_duplicates().sort_values().tolist()

    def horizons(self) -> list[int]:
        return sorted(int(hours) for hours in self.table["horizon_h"].unique())

    def _issued(self, issued: pd.Timestamp) -> pd.DataFrame:
        rows = self.table[self.table["issued_utc"] == issued]
        if rows.empty:
            raise ReplayError(f"no forecasts issued at {issued.isoformat()}; /api/meta lists the issue times")
        return rows

    def map_points(self, issued: pd.Timestamp, horizon: int) -> pd.DataFrame:
        rows = self._issued(issued)
        rows = rows[rows["horizon_h"] == horizon]
        if rows.empty:
            raise ReplayError(f"no {horizon}-hour forecasts; the horizons are {self.horizons()}")
        return rows.sort_values("slug")

    def station_forecast(self, slug: str, issued: pd.Timestamp) -> pd.DataFrame:
        rows = self._issued(issued)
        rows = rows[rows["slug"] == slug]
        if rows.empty:
            raise ReplayError(f"unknown station {slug!r}; /api/meta lists the stations")
        return rows.sort_values("horizon_h")
