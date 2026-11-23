"""Live inputs: the last few days of OpenAQ readings and Open-Meteo weather for our stations.

Only the network lives here. Everything after it goes through the training functions
(live.live_features), so live and training cannot drift apart in how features are made.
  readings  OpenAQ API, /v3/sensors/{id}/measurements: one call per station and pollutant. Every
            request, from whichever thread, waits its turn on one RateLimiter (the free key allows
            60 a minute), and a Deadline stops a fetch that runs too long, with the reason. Sensors are chosen by
            newest_sensors and kept in config/openaq_sensors.csv. The key travels only in the
            OpenAQ session's header, never to another host.
  weather   Open-Meteo's forecast API with the ECMWF IFS model on the training grid cells; its
            past hours were identical to the archive used for training (144 of 144 checked).
"""

import sys
import threading
import time
from collections.abc import Callable
from typing import Final

import numpy as np
import pandas as pd
import requests
from pydantic import BaseModel, ValidationError

from delhi_pm25.weather import SOURCES

OPENAQ_API: Final = "https://api.openaq.org/v3"
FORECAST_API: Final = "https://api.open-meteo.com/v1/forecast"
LIVE_PARAMETERS: Final = ("pm25", "pm10", "no2", "co")
WEATHER_VARIABLES: Final = SOURCES["actual_ecmwf_ifs"]
PAGE: Final = 1000
SPACING_S: Final = 1.05
ATTEMPTS: Final = 4
REQUEST_TIMEOUT_S: Final = 30


class LiveInputError(Exception):
    """A live source refused, kept failing, or answered in an unexpected shape."""


class _Last(BaseModel):
    utc: str


class _SensorParameter(BaseModel):
    name: str


class _Sensor(BaseModel):
    id: int
    parameter: _SensorParameter
    datetimeLast: _Last | None = None


class _Page(BaseModel):
    results: list[dict[str, object]]


class _Grid(BaseModel):
    latitude: float
    longitude: float


class _Forecast(BaseModel):
    hourly: dict[str, list[float | str | None]]


def newest_sensors(sensors: list[dict[str, object]], wanted: tuple[str, ...]) -> dict[str, int]:
    """For each wanted pollutant, the sensor that reported most recently (locations keep old,
    dead sensors next to the current one)."""
    try:
        parsed = [_Sensor.model_validate(sensor) for sensor in sensors]
    except ValidationError as err:
        raise LiveInputError(f"unexpected sensor list from OpenAQ: {err}") from err
    best: dict[str, tuple[str, int]] = {}
    for sensor in parsed:
        name, last = sensor.parameter.name, sensor.datetimeLast
        if name in wanted and last is not None and (name not in best or last.utc > best[name][0]):
            best[name] = (last.utc, sensor.id)
    return {name: sensor_id for name, (_, sensor_id) in best.items()}


def weather_rows(response: dict[str, object], slugs: list[str]) -> pd.DataFrame:
    """One grid cell's forecast-API answer -> the weather table weather_features reads, for every
    station in the cell. Boundary-layer height stays blank: the model does not use it."""
    try:
        hourly = _Forecast.model_validate(response).hourly
    except ValidationError as err:
        raise LiveInputError(f"unexpected weather response: {err}") from err
    frame = pd.DataFrame(hourly).rename(columns={"time": "time_utc"})
    frame["time_utc"] = pd.to_datetime(frame["time_utc"], utc=True).dt.as_unit("us")
    frame["boundary_layer_height"] = np.nan
    columns = ["slug", "time_utc", *WEATHER_VARIABLES, "boundary_layer_height"]
    return pd.concat([frame.assign(slug=slug) for slug in slugs], ignore_index=True)[columns]


def _wait(reason: str, seconds: float) -> None:
    print(f"  {reason}: waiting {seconds:.0f} s before retrying", file=sys.stderr, flush=True)
    time.sleep(seconds)


def get_json(session: requests.Session, url: str, params: dict[str, object]) -> dict[str, object]:
    """GET with retries: waits out rate limits (429) and server errors; other refusals stop."""
    for attempt in range(ATTEMPTS):
        try:
            response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
        except requests.RequestException as err:
            _wait(f"network error ({type(err).__name__})", 2**attempt * 5)
            continue
        if response.status_code == 429:
            _wait("rate limit", int(response.headers.get("X-Ratelimit-Reset", "60")) + 1)
            continue
        if response.status_code >= 500:
            _wait(f"server error {response.status_code}", 2**attempt * 5)
            continue
        if not response.ok:
            raise LiveInputError(f"{url} refused the request: HTTP {response.status_code} {response.text[:200]}")
        return response.json()
    raise LiveInputError(f"{url} kept failing after {ATTEMPTS} attempts")






def check_grid(response: dict[str, object], cell: tuple[float, float]) -> None:
    """Stop if Open-Meteo answered for another grid cell than the station trained on."""
    try:
        grid = _Grid.model_validate(response)
    except ValidationError as err:
        raise LiveInputError(f"unexpected weather response: {err}") from err
    if abs(grid.latitude - cell[0]) > 1e-3 or abs(grid.longitude - cell[1]) > 1e-3:
        raise LiveInputError(f"weather grid moved: asked for cell {cell}, got ({grid.latitude}, {grid.longitude})")


class RateLimiter:
    """At most one request start per `spacing_s` seconds, shared by every thread."""

    def __init__(self, spacing_s: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._spacing, self._clock, self._sleep = spacing_s, clock, sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            start = max(now, self._next)
            self._next = start + self._spacing
        self._sleep(start - now)


class Deadline:
    """Stops a fetch that runs past its budget, with the reason, before the job's own time limit
    kills it without one (as happened to a refresh during a slow OpenAQ spell)."""

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._seconds, self._clock = seconds, clock
        self._end = clock() + seconds

    def check(self) -> None:
        if self._clock() > self._end:
            raise LiveInputError(f"OpenAQ was too slow: the fetch passed its {self._seconds / 60:.0f}-minute budget")


class OpenAQ:
    """The OpenAQ API for several threads at once: one session per thread, one shared rate limit,
    one deadline. The key travels only in these sessions' header."""

    def __init__(self, key: str, limiter: RateLimiter, deadline: Deadline) -> None:
        self._key, self._limiter, self._deadline = key, limiter, deadline
        self._local = threading.local()

    def _get(self, url: str, params: dict[str, object]) -> list[dict[str, object]]:
        self._deadline.check()
        self._limiter.wait()
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers["X-API-Key"] = self._key
            self._local.session = session
        try:
            return _Page.model_validate(get_json(session, url, params)).results
        except ValidationError as err:
            raise LiveInputError(f"unexpected answer from {url}: {err}") from err

    def measurements(self, sensor_id: int, since: pd.Timestamp) -> list[dict[str, object]]:
        """Every measurement of one sensor from `since` until now, page by page."""
        results: list[dict[str, object]] = []
        page_number = 1
        while True:
            params = {"datetime_from": since.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": PAGE, "page": page_number}
            page = self._get(f"{OPENAQ_API}/sensors/{sensor_id}/measurements", params)
            results += page
            if len(page) < PAGE:
                return results
            page_number += 1

    def sensors(self, location_id: int) -> list[dict[str, object]]:
        """The sensor list of one location (each with its parameter and last report)."""
        return self._get(f"{OPENAQ_API}/locations/{location_id}/sensors", {})
