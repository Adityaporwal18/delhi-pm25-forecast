"""Stage 1a: download Delhi CPCB monitoring-station files from the OpenCity mirror.

WHERE THE DATA COMES FROM
  CPCB's Central Control Room portal (airquality.cpcb.gov.in/ccr) publishes per-station
  files, but it sits behind a captcha, so it cannot be scripted. OpenCity
  (data.opencity.in) republishes those same files as "Delhi Hourly Air Quality
  Reports" for 39 Delhi stations. We download from there. OpenCity labels them
  public domain, but they are copies of Vonter/india-cpcb-aqi (ODbL-1.0; see
  01b_fetch_cpcb_vonter.py), so we follow ODbL: credit CPCB, Vonter and OpenCity.

WHAT WE DOWNLOAD
  One file per station: 15-minute pollutant CONCENTRATIONS (PM2.5, PM10, NO2, ...)
  plus the station's own weather sensors, 2024-01-01 to 2025-12-31.
  29 columns, ~9-14 MB per station.

WHAT WE DELIBERATELY DO NOT DOWNLOAD
  The mirror also has "AQI Data 2017-2023" files. They are rejected: their hourly
  values jump e.g. 188 -> 465 within one hour, which is impossible for an AQI built
  on 24-hour averages, so they are mislabelled (probably raw concentrations or a
  sub-index). Mixing them in would silently change what we forecast partway through
  the dataset.

WHAT THIS SCRIPT DELIBERATELY DOES NOT DO
  No cleaning, no timezone fixes, no resampling. Files are saved byte-for-byte as
  published so every Stage 2 decision is visible and reversible. It only *reports*
  basic facts (row counts, first/last timestamp, station IDs) in a manifest.

OUTPUT
  data/raw/cpcb/conc_15min_2024_2025/<slug>.csv
  data/raw/cpcb/manifest.csv                  one row per downloaded file

USAGE (run from the project root)
  .venv/bin/python scripts/01_fetch_cpcb.py                      # all 39 stations
  .venv/bin/python scripts/01_fetch_cpcb.py --only r_k_puram_dpcc anand_vihar_dpcc
  .venv/bin/python scripts/01_fetch_cpcb.py --force              # re-download
"""

import argparse
import csv
import difflib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from delhi_pm25.download import DownloadError, download, sha256_of

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIONS_CSV = PROJECT_ROOT / "config" / "stations.csv"
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "cpcb"
FILES_DIR = OUT_DIR / "conc_15min_2024_2025"
MANIFEST_CSV = OUT_DIR / "manifest.csv"

CKAN_API = "https://data.opencity.in/api/3/action/package_show"
DATASET_ID = "0dc7b9fe-9fd4-46ee-a37e-88f0bd6f6362"
USER_AGENT = "delhi-pm25-forecast-student-project/0.1"
RESOURCE_COLUMN = "opencity_15min_resource"  # column of stations.csv with the file's name on OpenCity

# Exact header shared by all 39 15-minute files. The units use the micro sign (U+00B5)
# and superscript three (U+00B3); a look-alike character would make columns "missing".
EXPECTED_15MIN_HEADER = [
    "Station ID", "State", "City", "Station Name", "Timestamp",
    "PM2.5 (µg/m³)", "PM10 (µg/m³)", "NO (µg/m³)", "NO2 (µg/m³)", "NOx (ppb)",
    "NH3 (µg/m³)", "SO2 (µg/m³)", "CO (mg/m³)", "Ozone (µg/m³)", "Benzene (µg/m³)",
    "Toluene (µg/m³)", "Xylene (µg/m³)", "O Xylene (µg/m³)", "Eth-Benzene (µg/m³)",
    "MP-Xylene (µg/m³)", "AT (°C)", "RH (%)", "WS (m/s)", "WD (deg)", "RF (mm)",
    "TOT-RF (mm)", "SR (W/mt2)", "BP (mmHg)", "VWS (m/s)",
]

MANIFEST_FIELDS = [
    "slug", "file", "url", "bytes", "sha256", "header_ok", "n_rows",
    "n_blank_rows", "n_bad_width_rows", "first_ts", "last_ts", "file_station_ids",
    "file_station_names", "station_id_matches_config", "downloaded_at_utc",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_stations(only: list[str] | None) -> list[dict[str, str]]:
    with STATIONS_CSV.open(newline="", encoding="utf-8") as fh:
        stations = list(csv.DictReader(fh))
    if only:
        unknown = sorted(set(only) - {s["slug"] for s in stations})
        if unknown:
            sys.exit(f"Unknown slug(s) {unknown}; valid slugs are listed in {STATIONS_CSV}")
        stations = [s for s in stations if s["slug"] in set(only)]
    return stations


def resource_urls(session: requests.Session) -> dict[str, str]:
    """Ask OpenCity's CKAN API for the dataset's file list: {resource name: URL}."""
    resp = session.get(CKAN_API, params={"id": DATASET_ID}, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        sys.exit(f"OpenCity API error: {payload.get('error')}")
    return {r["name"].strip(): r["url"] for r in payload["result"]["resources"]}


def inspect_conc_15min(path: Path) -> dict:
    """Read facts from a 15-minute file without changing anything."""
    facts = {"header_ok": False, "n_rows": 0, "n_blank_rows": 0, "n_bad_width_rows": 0,
             "first_ts": "", "last_ts": "", "ids": set(), "names": set()}
    with path.open(newline="", encoding="utf-8-sig") as fh:  # -sig: tolerate a BOM
        reader = csv.reader(fh)
        header = next(reader, [])
        facts["header_ok"] = header == EXPECTED_15MIN_HEADER
        for row in reader:
            if not any(cell.strip() for cell in row):
                facts["n_blank_rows"] += 1
            elif len(row) != len(header):
                facts["n_bad_width_rows"] += 1
            else:
                facts["n_rows"] += 1
                facts["ids"].add(row[0])
                facts["names"].add(row[3])
                facts["first_ts"] = facts["first_ts"] or row[4]
                facts["last_ts"] = row[4]
    return facts


def load_manifest() -> dict[str, dict]:
    if not MANIFEST_CSV.exists():
        return {}
    with MANIFEST_CSV.open(newline="", encoding="utf-8") as fh:
        return {r["slug"]: r for r in csv.DictReader(fh)}


def write_manifest(rows: dict[str, dict]) -> None:
    with MANIFEST_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for slug in sorted(rows):
            writer.writerow(rows[slug])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", metavar="SLUG",
                        help="station slugs from config/stations.csv (default: all 39)")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()

    stations = load_stations(args.only)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    print(f"Fetching file list of OpenCity dataset {DATASET_ID} ...")
    urls = resource_urls(session)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    problems: list[str] = []

    for i, st in enumerate(stations, 1):
        slug, label = st["slug"], f"[{i:>2}/{len(stations)}] {st['slug']}"
        dest = FILES_DIR / f"{slug}.csv"
        url = urls.get(st[RESOURCE_COLUMN])
        if url is None:
            close = difflib.get_close_matches(st[RESOURCE_COLUMN], list(urls), n=2)
            problems.append(f"{slug}: '{st[RESOURCE_COLUMN]}' not on OpenCity (close: {close})")
            print(f"{label}: NOT FOUND")
            continue
        if dest.exists() and not args.force:
            size, digest = dest.stat().st_size, sha256_of(dest)
            fetched_at = manifest.get(slug, {}).get("downloaded_at_utc", "")
            print(f"{label}: already present ({size / 1e6:.1f} MB), not re-downloading")
        else:
            print(f"{label}: downloading ...", end=" ", flush=True)
            started = time.monotonic()
            try:
                size, digest = download(session, url, dest)
            except (requests.RequestException, OSError, DownloadError) as exc:
                problems.append(f"{slug}: download failed ({exc})")
                print(f"FAILED ({exc})")
                continue
            fetched_at = utc_now()
            print(f"{size / 1e6:.1f} MB in {time.monotonic() - started:.0f}s")

        facts = inspect_conc_15min(dest)
        ids_match = facts["ids"] == {st["station_id"]}
        if not ids_match:
            problems.append(f"{slug}: file station IDs {sorted(facts['ids'])} != config {st['station_id']}")
        if not facts["header_ok"]:
            problems.append(f"{slug}: unexpected header - inspect {dest}")
        odd_names = sorted(n for n in facts["names"] if n != st["station_name"])
        if odd_names:
            print(f"    note: the file names this station {odd_names!r}; "
                  f"config says {st['station_name']!r} (Stage 2: naming)")

        manifest[slug] = {
            "slug": slug, "file": str(dest.relative_to(PROJECT_ROOT)),
            "url": url, "bytes": size, "sha256": digest, "header_ok": facts["header_ok"],
            "n_rows": facts["n_rows"], "n_blank_rows": facts["n_blank_rows"],
            "n_bad_width_rows": facts["n_bad_width_rows"], "first_ts": facts["first_ts"],
            "last_ts": facts["last_ts"], "file_station_ids": ";".join(sorted(facts["ids"])),
            "file_station_names": ";".join(sorted(facts["names"])),
            "station_id_matches_config": ids_match, "downloaded_at_utc": fetched_at,
        }

    write_manifest(manifest)
    print(f"\nManifest: {MANIFEST_CSV.relative_to(PROJECT_ROOT)} ({len(manifest)} files listed)")
    if problems:
        print("\nPROBLEMS:\n  " + "\n  ".join(problems))
        return 1
    print("All requested files present, headers as expected, station IDs match config.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
