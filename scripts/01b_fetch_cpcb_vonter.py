"""Stage 1c: add a year of CPCB station data from the upstream dataset on GitHub.

WHY THIS SOURCE
  The OpenCity files used by 01_fetch_cpcb.py are copies of Vonter/india-cpcb-aqi, a
  public GitHub dataset that collects CPCB Data Repository files for 2009-2025. We
  checked: for R K Puram 2024 all 631,295 non-empty values are identical in both, and
  the 2024 row counts match for all 39 stations. Taking 2023 from the same upstream
  keeps ONE source and ONE format, with no CPCB captcha involved.

WHAT IT DOES
  1. Downloads the year's release file (one parquet for all of India, ~700 MB) and
     checks its SHA-256 against the fingerprint GitHub publishes for it.
  2. Writes our 39 stations (matched by CPCB Station ID, config/stations.csv) to
     data/raw/cpcb/conc_15min_<year>/<slug>.csv in exactly the OpenCity layout, so
     the Stage 2 scripts pick the new year up with no code change.
  No cleaning: values and timestamp labels are copied as published.

QUIRKS INHERITED FROM UPSTREAM (handled in Stage 2, exactly as for 2024-25)
  - Labels end in "+0000" but are Indian local time: the upstream parser stamps CPCB's
    local times as UTC without shifting them.
  - Rows whose readings are ALL empty were deleted upstream, so a few 15-minute slots
    are absent instead of blank.

LICENCE: ODbL-1.0 -- credit CPCB and Vonter/india-cpcb-aqi wherever results are shown.
Raw data is never committed (see .gitignore).

OUTPUT
  data/raw/vonter/cpcb-air-quality-<year>.parquet  the release file, untouched
  data/raw/cpcb/conc_15min_<year>/<slug>.csv        one file per station
  data/raw/cpcb/manifest_vonter.csv                 fingerprints of all of the above

USAGE (run from the project root)
  .venv/bin/python scripts/01b_fetch_cpcb_vonter.py --year 2023
"""

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import pandas as pd
import pyarrow.parquet as pq
import requests

from delhi_aqi.download import DownloadError, download, sha256_of
from delhi_aqi.paths import PROJECT_ROOT, RAW_CPCB_DIR, STATIONS_CSV
from delhi_aqi.raw_cpcb import EXPECTED_HEADER

RELEASE_API: Final = "https://api.github.com/repos/Vonter/india-cpcb-aqi/releases/tags/{year}"
VONTER_DIR: Final = PROJECT_ROOT / "data" / "raw" / "vonter"
MANIFEST_CSV: Final = RAW_CPCB_DIR / "manifest_vonter.csv"
MANIFEST_FIELDS: Final = ["year", "slug", "file", "n_rows", "first_ts", "last_ts", "sha256",
                          "source_url", "source_sha256", "written_at_utc"]
USER_AGENT: Final = "delhi-pm25-forecast-student-project/0.1"
# Same text form as the OpenCity files, e.g. 2024-01-01T00:00:00.000000+0000
LABEL_FORMAT: Final = "%Y-%m-%dT%H:%M:%S.%f%z"


class SourceError(Exception):
    """The upstream release is not what this script expects: stop rather than guess."""


@dataclass(frozen=True, slots=True)
class ReleaseFile:
    name: str
    url: str
    sha256: str


def release_file(session: requests.Session, year: int) -> ReleaseFile:
    """Find the year's parquet in the GitHub release, with GitHub's SHA-256 for it."""
    resp = session.get(RELEASE_API.format(year=year), timeout=30)
    if resp.status_code == 404:
        raise SourceError(f"Vonter/india-cpcb-aqi has no release for {year}")
    resp.raise_for_status()
    name = f"cpcb-air-quality-{year}.parquet"
    assets = {asset["name"]: asset for asset in resp.json()["assets"]}
    if name not in assets:
        raise SourceError(f"release {year} has no {name}; it has {sorted(assets)}")
    digest = assets[name].get("digest") or ""
    if not digest.startswith("sha256:"):
        raise SourceError(f"GitHub publishes no SHA-256 for {name}, so the download can't be verified")
    return ReleaseFile(name, assets[name]["browser_download_url"], digest.removeprefix("sha256:"))


def fetch_release(session: requests.Session, release: ReleaseFile) -> Path:
    """Download the release file once; later runs reuse it while its fingerprint matches."""
    dest = VONTER_DIR / release.name
    if dest.exists() and sha256_of(dest) == release.sha256:
        print(f"{release.name}: already present, SHA-256 matches GitHub's")
        return dest
    VONTER_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{release.name}: downloading (~700 MB) ...", flush=True)
    size, digest = download(session, release.url, dest)
    if digest != release.sha256:
        dest.unlink()
        raise SourceError(f"{release.name}: SHA-256 {digest} differs from GitHub's {release.sha256}")
    print(f"{release.name}: {size / 1e6:.0f} MB, SHA-256 matches GitHub's")
    return dest


def station_rows(parquet: Path, stations: pd.DataFrame) -> pd.DataFrame:
    """Rows of our 39 stations, after checking the columns match the 2024-25 files."""
    ids = stations["station_id"].tolist()
    table = pq.read_table(parquet, filters=[("Station ID", "in", ids)])
    if table.column_names != EXPECTED_HEADER:
        raise SourceError(f"{parquet.name}: columns differ from the 2024-25 files: {table.column_names}")
    rows = table.to_pandas().sort_values(["Station ID", "Timestamp"], ignore_index=True)
    missing = sorted(set(ids) - set(rows["Station ID"]))
    if missing:
        raise SourceError(f"{parquet.name}: no rows for station IDs {missing}")
    rows["Timestamp"] = rows["Timestamp"].dt.strftime(LABEL_FORMAT)
    return rows


def write_year(rows: pd.DataFrame, stations: pd.DataFrame, year: int) -> list[dict]:
    """One CSV per station in data/raw/cpcb/conc_15min_<year>/, each written atomically."""
    out_dir = RAW_CPCB_DIR / f"conc_15min_{year}"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for slug, station_id in zip(stations["slug"], stations["station_id"], strict=True):
        part = rows[rows["Station ID"] == station_id]
        dest = out_dir / f"{slug}.csv"
        tmp = dest.with_name(dest.name + ".part")
        part.to_csv(tmp, index=False)
        tmp.replace(dest)
        written.append({"year": str(year), "slug": slug, "file": str(dest.relative_to(PROJECT_ROOT)),
                        "n_rows": len(part), "first_ts": part["Timestamp"].iloc[0],
                        "last_ts": part["Timestamp"].iloc[-1], "sha256": sha256_of(dest)})
    return written


def update_manifest(new_rows: list[dict]) -> None:
    """Merge into manifest_vonter.csv, one row per (year, station)."""
    rows: dict[tuple[str, str], dict] = {}
    if MANIFEST_CSV.exists():
        with MANIFEST_CSV.open(newline="", encoding="utf-8") as fh:
            rows = {(r["year"], r["slug"]): r for r in csv.DictReader(fh)}
    rows.update({(r["year"], r["slug"]): r for r in new_rows})
    with MANIFEST_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows[key] for key in sorted(rows))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, required=True, help="calendar year, e.g. 2023")
    args = parser.parse_args()
    stations = pd.read_csv(STATIONS_CSV, dtype=str)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    try:
        release = release_file(session, args.year)
        rows = station_rows(fetch_release(session, release), stations)
    except (SourceError, DownloadError, requests.RequestException, OSError) as exc:
        print(f"STOPPED: {exc}")
        return 1

    written = write_year(rows, stations, args.year)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for row in written:
        row.update(source_url=release.url, source_sha256=release.sha256, written_at_utc=stamp)
    update_manifest(written)

    full_year = (pd.Timestamp(args.year + 1, 1, 1) - pd.Timestamp(args.year, 1, 1)).days * 96
    short = {r["slug"]: r["n_rows"] for r in written if r["n_rows"] < full_year}
    print(f"Wrote {len(written)} station files to data/raw/cpcb/conc_15min_{args.year}/ "
          f"({len(rows):,} rows; a full year is {full_year:,} rows per station)")
    print(f"Stations with fewer rows (upstream deletes all-empty rows): {short or 'none'}")
    print(f"Manifest: {MANIFEST_CSV.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
