"""Stage 1a: download Delhi CPCB monitoring-station files from the OpenCity mirror.

WHERE THE DATA COMES FROM
  CPCB's Central Control Room portal (airquality.cpcb.gov.in/ccr) publishes per-station
  files, but it sits behind a captcha, so it cannot be scripted. OpenCity
  (data.opencity.in, public-domain licence) republishes those same files as
  "Delhi Hourly Air Quality Reports" for 39 Delhi stations. We download from there.

TWO KINDS OF FILE PER STATION
  conc_15min   15-minute pollutant CONCENTRATIONS (PM2.5, PM10, NO2, ...) plus the
               station's own weather sensors, 2024-01-01 to 2025-12-31.
               29 columns, ~9-14 MB per station.  <- the core dataset (default)
  aqi_hourly   Hourly AQI values only (no concentrations), 2017-2023, laid out in
               month blocks. ~0.1-0.3 MB per station.  <- optional (--kinds aqi_hourly)

WHAT THIS SCRIPT DELIBERATELY DOES NOT DO
  No cleaning, no timezone fixes, no resampling. Files are saved byte-for-byte as
  published so every Stage 2 decision is visible and reversible. It only *reports*
  basic facts (row counts, first/last timestamp, station IDs) in a manifest.

OUTPUT
  data/raw/cpcb/conc_15min_2024_2025/<slug>.csv
  data/raw/cpcb/aqi_hourly_2017_2023/<slug>.csv     (only with --kinds aqi_hourly)
  data/raw/cpcb/manifest.csv                         one row per downloaded file

USAGE (run from the project root)
  .venv/bin/python scripts/01_fetch_cpcb.py                      # all 39 stations
  .venv/bin/python scripts/01_fetch_cpcb.py --only r_k_puram_dpcc anand_vihar_dpcc
  .venv/bin/python scripts/01_fetch_cpcb.py --kinds conc_15min aqi_hourly
  .venv/bin/python scripts/01_fetch_cpcb.py --force              # re-download
"""

import argparse
import csv
import difflib
import hashlib
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIONS_CSV = PROJECT_ROOT / "config" / "stations.csv"
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "cpcb"
MANIFEST_CSV = OUT_DIR / "manifest.csv"

CKAN_API = "https://data.opencity.in/api/3/action/package_show"
DATASET_ID = "0dc7b9fe-9fd4-46ee-a37e-88f0bd6f6362"
USER_AGENT = "delhi-aqi-forecast-student-project/0.1"

# kind -> (column of stations.csv holding the OpenCity resource name, output sub-folder)
KINDS = {
    "conc_15min": ("opencity_15min_resource", "conc_15min_2024_2025"),
    "aqi_hourly": ("opencity_aqi_resource", "aqi_hourly_2017_2023"),
}

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
MONTH_LABEL = re.compile(r"[A-Za-z]+-\d{4}")  # "January-2017" in the aqi_hourly layout

MANIFEST_FIELDS = [
    "slug", "kind", "file", "url", "bytes", "sha256", "header_ok", "n_rows",
    "n_blank_rows", "n_bad_width_rows", "first_ts", "last_ts", "file_station_ids",
    "file_station_names", "station_id_matches_config", "downloaded_at_utc",
]


class DownloadError(Exception):
    """The server refused the file (e.g. HTTP 404): retrying will not help."""


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


def download(session: requests.Session, url: str, dest: Path) -> tuple[int, str]:
    """Stream `url` into `dest`, returning (bytes, sha256).

    Writes to `<dest>.part` first and renames only when complete, so an interrupted
    run never leaves a half-written CSV that looks valid. Retries network errors.
    """
    tmp = dest.with_name(dest.name + ".part")
    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            sha, size = hashlib.sha256(), 0
            # identity = no gzip, so Content-Length is the true file size we can check
            with session.get(url, stream=True, timeout=(15, 120),
                             headers={"Accept-Encoding": "identity"}) as resp:
                if 400 <= resp.status_code < 500:  # 404 etc.: not retried (see except below)
                    raise DownloadError(f"HTTP {resp.status_code} for {url}")
                resp.raise_for_status()
                expected = resp.headers.get("Content-Length")
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 16):
                        fh.write(chunk)
                        sha.update(chunk)
                        size += len(chunk)
            if expected is not None and int(expected) != size:
                raise OSError(f"truncated: got {size} of {expected} bytes")
            tmp.replace(dest)
            return size, sha.hexdigest()
        except (requests.RequestException, OSError) as exc:
            tmp.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            print(f"    attempt {attempt} failed ({exc}); retrying in {2 ** attempt}s")
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def inspect_aqi_hourly(path: Path) -> dict:
    """Facts from the month-block layout: 'Year,2017' / 'January-2017,00:00:00,...' / day rows."""
    facts = {"header_ok": False, "n_rows": 0, "n_blank_rows": 0, "n_bad_width_rows": 0,
             "first_ts": "", "last_ts": "", "ids": set(), "names": set()}
    months: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            first = row[0].strip() if row else ""
            if not any(cell.strip() for cell in row):
                facts["n_blank_rows"] += 1
            elif first == "Year":
                continue
            elif MONTH_LABEL.fullmatch(first):
                months.append(first)
            elif first.isdigit() and len(row) == 25:  # day number + 24 hourly values
                facts["n_rows"] += 1
            else:
                facts["n_bad_width_rows"] += 1
    if months:
        facts.update(header_ok=True, first_ts=months[0], last_ts=months[-1])
    return facts


def load_manifest() -> dict[tuple[str, str], dict]:
    if not MANIFEST_CSV.exists():
        return {}
    with MANIFEST_CSV.open(newline="", encoding="utf-8") as fh:
        return {(r["slug"], r["kind"]): r for r in csv.DictReader(fh)}


def write_manifest(rows: dict[tuple[str, str], dict]) -> None:
    with MANIFEST_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for key in sorted(rows, key=lambda k: (k[1], k[0])):
            writer.writerow(rows[key])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", metavar="SLUG",
                        help="station slugs from config/stations.csv (default: all 39)")
    parser.add_argument("--kinds", nargs="+", choices=sorted(KINDS), default=["conc_15min"],
                        help="file kinds to fetch (default: conc_15min)")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args()

    stations = load_stations(args.only)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    print(f"Fetching file list of OpenCity dataset {DATASET_ID} ...")
    urls = resource_urls(session)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    problems: list[str] = []

    for kind in args.kinds:
        name_column, subdir = KINDS[kind]
        (OUT_DIR / subdir).mkdir(exist_ok=True)
        for i, st in enumerate(stations, 1):
            slug, label = st["slug"], f"[{kind} {i:>2}/{len(stations)}] {st['slug']}"
            dest = OUT_DIR / subdir / f"{slug}.csv"
            url = urls.get(st[name_column])
            if url is None:
                close = difflib.get_close_matches(st[name_column], list(urls), n=2)
                problems.append(f"{slug}/{kind}: '{st[name_column]}' not on OpenCity (close: {close})")
                print(f"{label}: NOT FOUND")
                continue
            previous = manifest.get((slug, kind), {})
            if dest.exists() and not args.force:
                size, digest = dest.stat().st_size, sha256_of(dest)
                fetched_at = previous.get("downloaded_at_utc", "")
                print(f"{label}: already present ({size / 1e6:.1f} MB), not re-downloading")
            else:
                print(f"{label}: downloading ...", end=" ", flush=True)
                started = time.monotonic()
                try:
                    size, digest = download(session, url, dest)
                except (requests.RequestException, OSError, DownloadError) as exc:
                    problems.append(f"{slug}/{kind}: download failed ({exc})")
                    print(f"FAILED ({exc})")
                    continue
                fetched_at = utc_now()
                print(f"{size / 1e6:.1f} MB in {time.monotonic() - started:.0f}s")

            facts = inspect_conc_15min(dest) if kind == "conc_15min" else inspect_aqi_hourly(dest)
            if kind == "conc_15min":
                ids_match = facts["ids"] == {st["station_id"]}
                id_match = str(ids_match)
                if not ids_match:
                    problems.append(f"{slug}: file station IDs {sorted(facts['ids'])} != config {st['station_id']}")
                odd_names = sorted(n for n in facts["names"] if n != st["station_name"])
                if odd_names:
                    print(f"    note: the file names this station {odd_names!r}; "
                          f"config says {st['station_name']!r} (Stage 2: naming)")
            else:
                id_match = "n/a (no IDs in this layout)"
            if not facts["header_ok"]:
                problems.append(f"{slug}/{kind}: unexpected header/layout - inspect {dest}")

            manifest[(slug, kind)] = {
                "slug": slug, "kind": kind, "file": str(dest.relative_to(PROJECT_ROOT)),
                "url": url, "bytes": size, "sha256": digest, "header_ok": facts["header_ok"],
                "n_rows": facts["n_rows"], "n_blank_rows": facts["n_blank_rows"],
                "n_bad_width_rows": facts["n_bad_width_rows"], "first_ts": facts["first_ts"],
                "last_ts": facts["last_ts"], "file_station_ids": ";".join(sorted(facts["ids"])),
                "file_station_names": ";".join(sorted(facts["names"])),
                "station_id_matches_config": id_match, "downloaded_at_utc": fetched_at,
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
