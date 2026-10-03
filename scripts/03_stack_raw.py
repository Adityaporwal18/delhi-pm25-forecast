"""Stage 2, step 1: stack every raw CPCB station file into ONE table, unchanged.

Reads every CSV in every sub-folder of data/raw/cpcb/ (so a folder of manually
downloaded 2023 files is picked up automatically), checks the format, and writes

  data/interim/cpcb_15min_raw.parquet   one row per (station, 15-min timestamp label)
  reports/stage2/files.csv              what each raw file contained

No cleaning happens here: values, gaps and timestamp labels are exactly as published.
Parquet is used instead of CSV because it keeps the column types (dates stay dates)
and loads in about a second instead of a minute.

Usage:
  .venv/bin/python scripts/03_stack_raw.py
"""

import dataclasses
import sys

import pandas as pd

from delhi_pm25.paths import INTERIM_DIR, REPORTS_DIR, STATIONS_CSV
from delhi_pm25.raw_cpcb import RawFormatError, load_raw, station_files

OUT_PARQUET = INTERIM_DIR / "cpcb_15min_raw.parquet"
OUT_FILES = REPORTS_DIR / "stage2" / "files.csv"


def main() -> int:
    stations = pd.read_csv(STATIONS_CSV)
    files = station_files()
    print(f"Reading {len(files)} station files ...")
    try:
        raw = load_raw(files, stations)
    except RawFormatError as err:
        print(f"STOPPED: {err}", file=sys.stderr)
        return 1

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILES.parent.mkdir(parents=True, exist_ok=True)
    raw.readings.to_parquet(OUT_PARQUET, index=False)
    facts = pd.DataFrame([dataclasses.asdict(fact) for fact in raw.files])
    facts["names_in_file"] = facts["names_in_file"].map(lambda names: " | ".join(map(repr, names)))
    facts.to_csv(OUT_FILES, index=False)

    readings = raw.readings
    print(f"Stations: {readings['slug'].nunique()} of {len(stations)} in config")
    print(f"Readings: {len(readings):,} rows, labels {readings['ts_label'].min()} -> {readings['ts_label'].max()}")
    print(f"Non-reading lines dropped: {facts['n_dropped_rows'].sum()}")
    print(f"Identical repeats across files dropped: {raw.n_identical_duplicates_dropped}")
    print(f"Wrote {OUT_PARQUET.relative_to(OUT_PARQUET.parents[2])} and {OUT_FILES.relative_to(OUT_FILES.parents[2])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
