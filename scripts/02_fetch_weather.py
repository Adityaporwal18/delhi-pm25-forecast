"""Stage 1b: download hourly weather for the Delhi stations from Open-Meteo (free, no key).

TWO KINDS OF WEATHER - AND WHY YOU NEED BOTH
  actual    Reanalysis: a weather model re-run over the past with all observations folded
            in, i.e. the best estimate of what the weather WAS at each hour.
  forecast  What a weather model PREDICTED for each hour, issued two days earlier
            (Open-Meteo "previous runs"; variable names end in _previous_day2).
  A live 48-hour PM2.5 forecast only ever has a FORECAST of the coming weather. Training
  on the actual future weather is leakage: great test scores that collapse in production.
  Both are downloaded now so that Stage 3 can make (and justify) that choice.

SOURCES - each pinned to ONE model, because Open-Meteo's default "best_match" silently
switches models over time (2024 and 2025 rows would come from different models).
  actual_ecmwf_ifs    archive API, ECMWF IFS (~9 km grid), 9 surface variables
  actual_era5_blh     archive API, ERA5 (~25 km grid), boundary-layer height only. ERA5
                      has it for 2023 and from Jul 2024; NO archive model has Jan-Jun 2024.
  forecast_day2_icon  previous-runs API, DWD ICON, the same 9 variables as forecast two
                      days ahead. Empty before ~2024-01-20 (all of 2023): the archive of
                      past forecasts starts then.

ONE DOWNLOAD PER GRID CELL, NOT PER STATION
  A weather model sees Delhi as a few grid boxes; stations in the same box get identical
  values. So the script first asks which box each station falls in, then fetches each box
  once (about 4x fewer API calls). Consequence worth remembering: weather explains WHEN the
  whole city is polluted, not WHY one station is dirtier than its neighbour.

OUTPUT (times in UTC, values exactly as returned, empty field = missing)
  data/raw/weather/station_cells.csv          per source: station -> grid cell
  data/raw/weather/<source>/<cell_id>.csv     cell_id, time_utc, <variables>
  data/raw/weather/manifest.csv               per file: model, grid point, units, nulls

Data: Open-Meteo.com, licence CC BY 4.0 (credit it in your README). The free tier is
non-commercial and limited to 600 calls/min, 5,000/hour, 10,000/day; a 3-year request
counts as ~79 calls. A full run is ~2,500 calls and ~8 minutes. Finished files are
skipped on re-runs, so an interrupted run can simply be started again.

USAGE (from the project root)
  .venv/bin/python scripts/02_fetch_weather.py
  .venv/bin/python scripts/02_fetch_weather.py --only r_k_puram_dpcc anand_vihar_dpcc
  .venv/bin/python scripts/02_fetch_weather.py --sources actual_ecmwf_ifs --force
"""

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Final

import requests

PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
STATIONS_CSV: Final = PROJECT_ROOT / "config" / "stations.csv"
OUT_DIR: Final = PROJECT_ROOT / "data" / "raw" / "weather"
CELLS_CSV: Final = OUT_DIR / "station_cells.csv"
MANIFEST_CSV: Final = OUT_DIR / "manifest.csv"
USER_AGENT: Final = "delhi-pm25-forecast-student-project/0.1"

ARCHIVE_API: Final = "https://archive-api.open-meteo.com/v1/archive"
PREVIOUS_RUNS_API: Final = "https://previous-runs-api.open-meteo.com/v1/forecast"
WEATHER_VARS: Final = (
    "temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation",
    "surface_pressure", "cloud_cover", "wind_speed_10m", "wind_direction_10m",
    "shortwave_radiation",
)
DISCOVERY_DAY: Final = "2025-01-01"  # any covered day works: only the grid coordinates are used


@dataclass(frozen=True, slots=True)
class Source:
    """One weather dataset: which API, which (pinned) model, which hourly variables."""

    api: str
    model: str
    variables: tuple[str, ...]

    def params(self) -> dict[str, str]:
        # GMT -> timestamps in UTC; m/s -> same unit as the CPCB stations' own wind sensors
        return {"models": self.model, "timezone": "GMT", "wind_speed_unit": "ms"}


SOURCES: Final = {
    "actual_ecmwf_ifs": Source(ARCHIVE_API, "ecmwf_ifs", WEATHER_VARS),
    "actual_era5_blh": Source(ARCHIVE_API, "era5", ("boundary_layer_height",)),
    "forecast_day2_icon": Source(PREVIOUS_RUNS_API, "icon_seamless",
                                 tuple(f"{v}_previous_day2" for v in WEATHER_VARS)),
}
CELL_FIELDS: Final = ["source", "slug", "station_name", "station_lat", "station_lon",
                      "cell_id", "grid_lat", "grid_lon"]
META_FIELDS: Final = ["grid_lat", "grid_lon", "elevation_m", "units", "start_date",
                      "end_date", "fetched_at_utc"]
MANIFEST_FIELDS: Final = ["source", "cell_id", "api", "model", *META_FIELDS, "n_rows",
                          "first_time_utc", "last_time_utc", "empty_pct", "null_counts",
                          "stations"]


@dataclass(frozen=True, slots=True)
class Options:
    """Command-line choices, parsed once."""

    sources: tuple[str, ...]
    only: frozenset[str]  # empty = all stations
    start: str
    end: str
    pause_s: float
    force: bool


@dataclass(frozen=True, slots=True)
class CellJob:
    """Fetch one source's hourly series for one grid cell."""

    source: str
    cell_id: str
    grid_lat: str
    grid_lon: str
    stations: tuple[str, ...]  # every station in this cell (not only the --only ones)

    @property
    def dest(self) -> Path:
        return OUT_DIR / self.source / f"{self.cell_id}.csv"


class OpenMeteoError(Exception):
    """A request failed in a way that retrying right now will not fix."""


class QuotaExhaustedError(OpenMeteoError):
    """The hourly or daily free quota is used up: stop now and re-run later."""


class OpenMeteo:
    """Tiny API client: one HTTP session, a polite pause between calls, retries for hiccups."""

    def __init__(self, pause_s: float) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.pause_s = pause_s
        self.last_call = 0.0  # mutated on purpose: remembers when we last called the API

    def get(self, url: str, params: dict[str, str]) -> dict | list:
        """GET and decode JSON; waits out per-minute limits, 5xx errors and network blips."""
        reason = ""
        for attempt in range(1, 6):
            time.sleep(max(0.0, self.last_call + self.pause_s - time.monotonic()))
            self.last_call = time.monotonic()
            try:
                resp = self.session.get(url, params=params, timeout=(15, 300))
            except requests.RequestException as exc:
                reason, wait = f"network error ({exc})", 15 * attempt
            else:
                if resp.ok:
                    return resp.json()
                reason = error_reason(resp)
                if resp.status_code == 429 and "minute" not in reason.lower():
                    raise QuotaExhaustedError(reason)  # hourly/daily limit: waiting won't help
                if resp.status_code != 429 and resp.status_code < 500:
                    raise OpenMeteoError(f"HTTP {resp.status_code}: {reason}")
                wait = 65 if resp.status_code == 429 else 15 * attempt
            print(f"\n    {reason} - waiting {wait}s (attempt {attempt}/5)", flush=True)
            time.sleep(wait)
        raise OpenMeteoError(f"gave up after 5 attempts: {reason}")


def error_reason(resp: requests.Response) -> str:
    """Open-Meteo explains errors as JSON: {"error": true, "reason": "..."}."""
    try:
        return str(resp.json().get("reason", resp.text[:200]))
    except ValueError:  # not JSON, e.g. an HTML page from a proxy
        return resp.text[:200]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def discover_cells(client: OpenMeteo, stations: list[dict[str, str]]) -> list[dict[str, str]]:
    """Ask each source which grid cell every station falls in (1 day, 1 variable)."""
    rows = []
    for name, src in SOURCES.items():
        params = src.params() | {
            "latitude": ",".join(s["latitude"] for s in stations),
            "longitude": ",".join(s["longitude"] for s in stations),
            "start_date": DISCOVERY_DAY, "end_date": DISCOVERY_DAY, "hourly": src.variables[0],
        }
        answer = client.get(src.api, params)
        points = answer if isinstance(answer, list) else [answer]  # 1 location -> plain object
        for st, point in zip(stations, points, strict=True):
            rows.append({"source": name, "slug": st["slug"], "station_name": st["station_name"],
                         "station_lat": st["latitude"], "station_lon": st["longitude"],
                         "cell_id": f"{point['latitude']:.4f}N_{point['longitude']:.4f}E",
                         "grid_lat": str(point["latitude"]), "grid_lon": str(point["longitude"])})
    return rows


def station_cells(client: OpenMeteo, stations: list[dict[str, str]], force: bool) -> list[dict[str, str]]:
    """Station -> grid-cell mapping for every source, cached in station_cells.csv."""
    expected = {(src, st["slug"]) for src in SOURCES for st in stations}
    if CELLS_CSV.exists() and not force:
        rows = read_csv(CELLS_CSV)
        if {(r["source"], r["slug"]) for r in rows} == expected:
            return rows
    print("Asking Open-Meteo which grid cell each station falls in ...")
    rows = discover_cells(client, stations)
    write_csv(CELLS_CSV, CELL_FIELDS, rows)
    return rows


def plan_jobs(cell_rows: list[dict[str, str]], opts: Options) -> list[CellJob]:
    """One job per (source, cell) containing at least one requested station."""
    members: dict[tuple[str, str, str, str], list[str]] = {}
    for r in cell_rows:
        members.setdefault((r["source"], r["cell_id"], r["grid_lat"], r["grid_lon"]), []).append(r["slug"])
    return [CellJob(source, cell_id, lat, lon, tuple(slugs))
            for (source, cell_id, lat, lon), slugs in sorted(members.items())
            if source in opts.sources and (not opts.only or opts.only & set(slugs))]


def fetch_cell(client: OpenMeteo, job: CellJob, opts: Options) -> dict[str, str]:
    """Download one cell's series, save it as CSV (atomically), return manifest metadata."""
    src = SOURCES[job.source]
    payload = client.get(src.api, src.params() | {
        "latitude": job.grid_lat, "longitude": job.grid_lon,
        "start_date": opts.start, "end_date": opts.end, "hourly": ",".join(src.variables)})
    if payload["utc_offset_seconds"] != 0:
        raise OpenMeteoError(f"expected UTC times, got offset {payload['utc_offset_seconds']}s")
    returned = f"{payload['latitude']:.4f}N_{payload['longitude']:.4f}E"
    if returned != job.cell_id:
        raise OpenMeteoError(f"asked for grid cell {job.cell_id}, API answered {returned}")
    # With one pinned model the keys are plain names; strip a "_<model>" suffix just in case.
    hourly = {k.removesuffix(f"_{src.model}"): v for k, v in payload["hourly"].items()}
    units = {k.removesuffix(f"_{src.model}"): v for k, v in payload["hourly_units"].items()}
    missing = [v for v in ("time", *src.variables) if v not in hourly]
    if missing:
        raise OpenMeteoError(f"response lacks {missing}")
    job.dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = job.dest.with_name(job.dest.name + ".part")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["cell_id", "time_utc", *src.variables])
        for i, t in enumerate(hourly["time"]):  # "2024-01-01T00:00" -> explicit UTC offset
            values = ("" if hourly[v][i] is None else hourly[v][i] for v in src.variables)
            writer.writerow([job.cell_id, f"{t}:00+00:00", *values])
    tmp.replace(job.dest)  # rename only when complete: no half-written CSVs
    return {"grid_lat": str(payload["latitude"]), "grid_lon": str(payload["longitude"]),
            "elevation_m": str(payload.get("elevation", "")),
            "units": "; ".join(f"{v}={units.get(v, '?')}" for v in src.variables),
            "start_date": opts.start, "end_date": opts.end, "fetched_at_utc": utc_now()}


def file_stats(path: Path, variables: tuple[str, ...]) -> dict[str, str]:
    """Row count, first/last timestamp and empty-value counts, recomputed from disk."""
    rows = read_csv(path)
    nulls = {v: sum(r[v] == "" for r in rows) for v in variables}
    n_values = max(1, len(rows) * len(variables))
    return {"n_rows": str(len(rows)),
            "first_time_utc": rows[0]["time_utc"] if rows else "",
            "last_time_utc": rows[-1]["time_utc"] if rows else "",
            "empty_pct": f"{100 * sum(nulls.values()) / n_values:.1f}",
            "null_counts": "; ".join(f"{v}={n}" for v, n in nulls.items())}


def parse_args() -> Options:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", metavar="SLUG", default=[],
                        help="station slugs from config/stations.csv (default: all 39)")
    parser.add_argument("--sources", nargs="+", choices=list(SOURCES), default=list(SOURCES))
    parser.add_argument("--start", type=date.fromisoformat, default=date(2022, 12, 25),
                        help="first UTC day (default 2022-12-25: a week of history before the "
                             "CPCB data starts on 2023-01-01, for lag features)")
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 1, 1),
                        help="last UTC day (default 2026-01-01: CPCB data ends 2025-12-31)")
    parser.add_argument("--pause", type=float, default=12.0,
                        help="seconds between API calls (default 12; keeps under 600 calls/min)")
    parser.add_argument("--force", action="store_true",
                        help="re-fetch existing files and redo the station->cell mapping")
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("--start must not be after --end")
    return Options(tuple(args.sources), frozenset(args.only), args.start.isoformat(),
                   args.end.isoformat(), args.pause, args.force)


def main() -> int:
    opts = parse_args()
    stations = read_csv(STATIONS_CSV)
    unknown = sorted(opts.only - {s["slug"] for s in stations})
    if unknown:
        sys.exit(f"Unknown slug(s) {unknown}; valid slugs are in {STATIONS_CSV}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenMeteo(opts.pause_s)
    try:
        jobs = plan_jobs(station_cells(client, stations, opts.force), opts)
    except OpenMeteoError as exc:
        sys.exit(f"Could not map stations to grid cells: {exc}")
    manifest = {(r["source"], r["cell_id"]): r for r in read_csv(MANIFEST_CSV)} if MANIFEST_CSV.exists() else {}
    problems: list[str] = []
    try:
        for i, job in enumerate(jobs, 1):
            src, old = SOURCES[job.source], manifest.get((job.source, job.cell_id))
            print(f"[{i:>2}/{len(jobs)}] {job.source}/{job.cell_id} ({len(job.stations)} stations): ",
                  end="", flush=True)
            if job.dest.exists() and old and not opts.force:
                meta = {k: old[k] for k in META_FIELDS}
                covered = (old["start_date"], old["end_date"])
                note = "" if covered == (opts.start, opts.end) else \
                    f" (covers {covered[0]}..{covered[1]}; add --force to re-download)"
                print(f"already present{note}", end=", ")
            else:
                try:
                    meta = fetch_cell(client, job, opts)
                except QuotaExhaustedError:
                    raise
                except OpenMeteoError as exc:
                    problems.append(f"{job.source}/{job.cell_id}: {exc}")
                    print(f"FAILED ({exc})")
                    continue
            stats = file_stats(job.dest, src.variables)
            manifest[(job.source, job.cell_id)] = {
                "source": job.source, "cell_id": job.cell_id, "api": src.api, "model": src.model,
                **meta, **stats, "stations": ";".join(job.stations)}
            print(f"{stats['n_rows']} rows, {stats['empty_pct']}% empty values")
    except QuotaExhaustedError as exc:
        problems.append(f"Open-Meteo quota reached ({exc}). Re-run later; finished files are skipped.")
    finally:
        write_csv(MANIFEST_CSV, MANIFEST_FIELDS, [manifest[k] for k in sorted(manifest)])
    print(f"\nManifest: {MANIFEST_CSV.relative_to(PROJECT_ROOT)} ({len(manifest)} files listed)")
    print(f"Station -> grid cell map: {CELLS_CSV.relative_to(PROJECT_ROOT)}")
    if problems:
        print("\nPROBLEMS:\n  " + "\n  ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
