"""Live forecasts, stage B: download CPCB readings for 2026 from OpenAQ's public archive.

OpenAQ copies CPCB's 15-minute feed (src/delhi_pm25/openaq.py describes the checks). Its public
archive needs no key: one gzipped CSV per location per day, a few days behind real time. For
each of our 37 stations (config/openaq_locations.csv) and each day from --start to --end:
  1. the archive file is kept unchanged in data/raw/openaq/<location>/<YYYYMMDD>.csv.gz
     (days already downloaded are skipped; days the archive does not have stay missing);
  2. the station's rows become a CPCB-layout station file,
     data/raw/cpcb/conc_15min_<year>_openaq/<slug>.csv, which the existing loader reads as is.
Manifest: data/raw/cpcb/manifest_openaq.csv (days found, rows, first and last label, SHA-256).

Usage:
  .venv/bin/python scripts/01c_fetch_openaq.py --start 2026-01-01 --end 2026-11-16
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Final

import pandas as pd
import requests

from delhi_pm25.download import sha256_of
from delhi_pm25.openaq import OpenAQFormatError, StationIdentity, station_table
from delhi_pm25.paths import PROJECT_ROOT, RAW_CPCB_DIR, STATIONS_CSV

ARCHIVE: Final = "https://openaq-data-archive.s3.amazonaws.com/records/csv.gz"
LOCATIONS_CSV: Final = PROJECT_ROOT / "config" / "openaq_locations.csv"
CACHE: Final = PROJECT_ROOT / "data" / "raw" / "openaq"
MANIFEST: Final = RAW_CPCB_DIR / "manifest_openaq.csv"
WORKERS: Final = 8
ATTEMPTS: Final = 3


class ArchiveError(Exception):
    """The archive kept failing for a file it should have (not a simply missing day)."""


def day_file(session: requests.Session, location: int, day: date) -> Path | None:
    """One location-day from the archive, downloaded once; None if the archive has no such day."""
    path = CACHE / str(location) / f"{day:%Y%m%d}.csv.gz"
    if path.exists():
        return path
    url = f"{ARCHIVE}/locationid={location}/year={day:%Y}/month={day:%m}/location-{location}-{day:%Y%m%d}.csv.gz"
    for attempt in range(ATTEMPTS):
        try:
            response = session.get(url, timeout=60)
        except requests.RequestException:
            time.sleep(2**attempt)
            continue
        if response.status_code == 404:
            return None
        if response.ok:
            path.parent.mkdir(parents=True, exist_ok=True)
            part = path.with_suffix(".part")
            part.write_bytes(response.content)
            part.rename(path)
            return path
        time.sleep(2**attempt)
    raise ArchiveError(f"could not download {url} after {ATTEMPTS} attempts")


def archive_rows(paths: list[Path]) -> pd.DataFrame:
    columns = ["datetime", "parameter", "units", "value"]
    frames = [pd.read_csv(path, usecols=columns, dtype={"datetime": str, "parameter": str, "units": str}) for path in paths]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)


def write_atomically(table: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".part")
    table.to_csv(part, index=False)
    part.rename(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="last day to fetch (the archive is a few days behind)")
    parser.add_argument("--only", nargs="*", default=[], help="station slugs (default: all 37)")
    args = parser.parse_args()
    if args.start.year != args.end.year or args.start > args.end:
        parser.error("--start and --end must be in the same year, start first (one output folder per year)")
    return args


def main() -> int:
    args = parse_args()
    locations = pd.read_csv(LOCATIONS_CSV)
    if args.only:
        locations = locations[locations["slug"].isin(args.only)]
    names = pd.read_csv(STATIONS_CSV).set_index("slug")
    days = list(pd.date_range(args.start, args.end).date)
    session = requests.Session()
    lines = []
    for number, station in enumerate(locations.itertuples(), 1):
        identity = StationIdentity(names.loc[station.slug, "station_id"], names.loc[station.slug, "station_name"].strip())
        try:
            with ThreadPoolExecutor(WORKERS) as pool:
                found = [p for p in pool.map(lambda day: day_file(session, station.openaq_location_id, day), days) if p is not None]
            table = station_table(archive_rows(found), identity)
        except (ArchiveError, OpenAQFormatError, requests.RequestException) as err:
            print(f"STOPPED at {station.slug}: {err}", file=sys.stderr)
            return 1
        path = RAW_CPCB_DIR / f"conc_15min_{args.start.year}_openaq" / f"{station.slug}.csv"
        write_atomically(table, path)
        lines.append({"slug": station.slug, "openaq_location_id": station.openaq_location_id, "year": args.start.year,
                      "days_requested": len(days), "days_found": len(found), "n_rows": len(table),
                      "first_ts": table["Timestamp"].min(), "last_ts": table["Timestamp"].max(),
                      "sha256": sha256_of(path), "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        print(f"[{number:2d}/{len(locations)}] {station.slug}: {len(found)}/{len(days)} days, {len(table):,} rows", flush=True)
    manifest = pd.DataFrame(lines)
    if MANIFEST.exists():
        old = pd.read_csv(MANIFEST)
        keep = ~old.set_index(["slug", "year"]).index.isin(manifest.set_index(["slug", "year"]).index)
        manifest = pd.concat([old[keep], manifest], ignore_index=True)
    manifest.sort_values(["year", "slug"]).to_csv(MANIFEST, index=False)
    print(f"Wrote {len(lines)} station files and {MANIFEST.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
