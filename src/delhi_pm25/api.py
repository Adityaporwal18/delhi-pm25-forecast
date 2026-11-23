"""Stage 7: the HTTP API (FastAPI) over the replay, plus the built website when it exists.

Endpoints:
  GET /api/health                               liveness check
  GET /api/meta                                 issue times, horizons, stations, colour bands, credits
  GET /api/map?issued=...&horizon=48            every station's forecast for one horizon, with its colour
  GET /api/stations/{slug}/forecast?issued=...  one station's 48-hour path: band, median, measured
  GET /api/live                                 the latest live forecast (every station, now to 48 h)
  GET /api/accuracy                             the held-out 2025 accuracy numbers (evaluation model)
"""

import math
from datetime import datetime
from pathlib import Path
from typing import Final

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from delhi_pm25.accuracy import AccuracySummary
from delhi_pm25.live_source import LivePoint, LiveSource, LiveWindow, StationState
from delhi_pm25.serving import CATEGORIES, CREDITS, Replay, ReplayError, category

NOTE: Final = (
    "Replay of the 2025 test year: what the model would have forecast at the chosen time, next to "
    "what was measured. Colours are a PM2.5-based category (CPCB PM2.5 bands, which CPCB defines on "
    "24-hour averages), not AQI."
)


class StationOut(BaseModel):
    slug: str
    name: str
    latitude: float
    longitude: float


class CategoryOut(BaseModel):
    label: str
    upper_ug_m3: float | None
    colour: str


class Meta(BaseModel):
    issue_times_utc: list[datetime]
    horizons_h: list[int]
    stations: list[StationOut]
    categories: list[CategoryOut]
    credits: str
    note: str


class MapPoint(BaseModel):
    slug: str
    p10: float | None
    p50: float | None
    p90: float | None
    measured: float | None
    category: str | None
    colour: str | None


class ForecastPoint(BaseModel):
    horizon_h: int
    valid_utc: datetime
    p10: float | None
    p50: float | None
    p90: float | None
    measured: float | None


class LivePointOut(LivePoint):
    category: str | None
    colour: str | None


class LiveForecastOut(BaseModel):
    generated_at_utc: datetime
    issued_utc: datetime
    stations_reporting: int
    stations: int
    training_window: LiveWindow
    rows: list[LivePointOut]
    city_median_now: float | None
    heavy_smog_now: bool
    station_status: list[StationState]


def _coloured(point: LivePoint) -> LivePointOut:
    band = None if point.p50 is None else category(point.p50)
    return LivePointOut(**point.model_dump(), category=None if band is None else band.label,
                        colour=None if band is None else band.colour)


def _value(number: float) -> float | None:
    return None if math.isnan(number) else round(float(number), 1)


def _utc(moment: datetime) -> pd.Timestamp:
    stamp = pd.Timestamp(moment)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _not_found(err: ReplayError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(err))


def create_app(replay: Replay, frontend: Path | None = None, live: LiveSource | None = None) -> FastAPI:
    app = FastAPI(title="Delhi PM2.5 forecast (replay of 2025)")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta() -> Meta:
        stations = [StationOut(slug=row.slug, name=row.station_name, latitude=row.latitude, longitude=row.longitude)
                    for row in replay.stations.itertuples()]
        bands = [CategoryOut(label=band.label, upper_ug_m3=None if math.isinf(band.upper_ug_m3) else band.upper_ug_m3,
                             colour=band.colour) for band in CATEGORIES]
        return Meta(issue_times_utc=replay.issue_times(), horizons_h=replay.horizons(), stations=stations,
                    categories=bands, credits=CREDITS, note=NOTE)

    @app.get("/api/map")
    def map_points(issued: datetime, horizon: int = 48) -> list[MapPoint]:
        try:
            rows = replay.map_points(_utc(issued), horizon)
        except ReplayError as err:
            raise _not_found(err) from err
        points = []
        for row in rows.itertuples():
            band = category(row.p50)
            points.append(MapPoint(slug=row.slug, p10=_value(row.p10), p50=_value(row.p50), p90=_value(row.p90),
                                   measured=_value(row.measured), category=None if band is None else band.label,
                                   colour=None if band is None else band.colour))
        return points

    @app.get("/api/stations/{slug}/forecast")
    def station_forecast(slug: str, issued: datetime) -> list[ForecastPoint]:
        try:
            rows = replay.station_forecast(slug, _utc(issued))
        except ReplayError as err:
            raise _not_found(err) from err
        return [ForecastPoint(horizon_h=int(row.horizon_h), valid_utc=row.issued_utc + pd.Timedelta(hours=int(row.horizon_h)),
                              p10=_value(row.p10), p50=_value(row.p50), p90=_value(row.p90), measured=_value(row.measured))
                for row in rows.itertuples()]

    @app.get("/api/live")
    def live_forecast() -> LiveForecastOut:
        document = None if live is None else live.latest()
        if document is None:
            raise HTTPException(status_code=503, detail="no live forecast is available yet")
        return LiveForecastOut(**document.model_dump(exclude={"rows"}), rows=[_coloured(row) for row in document.rows])

    @app.get("/api/accuracy")
    def accuracy() -> AccuracySummary:
        return replay.accuracy

    if frontend is not None and frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="site")
    return app
