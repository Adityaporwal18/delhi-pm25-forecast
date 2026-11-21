"""Read raw CPCB station files exactly as published -- no cleaning decisions.

What this module does:
  * checks every file has the 29 published columns (stops if the format changes)
  * drops lines that are not readings (e.g. the lone "2025" line where two yearly
    exports were glued together) and counts them
  * identifies the station by the CPCB ID INSIDE the file (e.g. site_124), never by
    the file name -- so a manually downloaded 2023 file with any name can be put in
    a new folder under data/raw/cpcb/ and is picked up automatically
  * keeps each timestamp label exactly as written, as a plain (naive) date-time.
    Labels end in "+0000" (the CPCB-derived files, really Delhi time: stage 2) or "+0530"
    (OpenAQ-derived files, Delhi time stated outright); both are kept as Delhi wall-clock labels.

What it deliberately does NOT do: fill gaps, remove outliers, average to hourly,
shift time zones or convert units. Those are decisions, made later, on purpose.
"""

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pandas as pd

from delhi_pm25.paths import RAW_CPCB_DIR

ID_COLUMNS: Final = ["Station ID", "State", "City", "Station Name", "Timestamp"]

# Published column name -> short name used in code. Units stay as published:
# ug/m3, except CO (mg/m3) and NOx (ppb). BP says mmHg, but most stations report
# values around 980, which only makes sense in hPa (see the Stage 2 inspection).
SHORT_NAMES: Final[dict[str, str]] = {
    "PM2.5 (µg/m³)": "pm25", "PM10 (µg/m³)": "pm10", "NO (µg/m³)": "no",
    "NO2 (µg/m³)": "no2", "NOx (ppb)": "nox", "NH3 (µg/m³)": "nh3",
    "SO2 (µg/m³)": "so2", "CO (mg/m³)": "co", "Ozone (µg/m³)": "o3",
    "Benzene (µg/m³)": "benzene", "Toluene (µg/m³)": "toluene", "Xylene (µg/m³)": "xylene",
    "O Xylene (µg/m³)": "o_xylene", "Eth-Benzene (µg/m³)": "eth_benzene",
    "MP-Xylene (µg/m³)": "mp_xylene", "AT (°C)": "at", "RH (%)": "rh", "WS (m/s)": "ws",
    "WD (deg)": "wd", "RF (mm)": "rf", "TOT-RF (mm)": "tot_rf", "SR (W/mt2)": "sr",
    "BP (mmHg)": "bp", "VWS (m/s)": "vws",
}
MEASUREMENTS: Final = list(SHORT_NAMES.values())
# The 7 pollutants with CPCB AQI breakpoints; the only measurements kept after cleaning.
POLLUTANTS: Final = ["pm25", "pm10", "no2", "so2", "co", "o3", "nh3"]
EXPECTED_HEADER: Final = ID_COLUMNS + list(SHORT_NAMES)
LABEL_SUFFIXES: Final = ("+0000", "+0530")
LABEL_FORMAT: Final = "%Y-%m-%dT%H:%M:%S.%f"


class RawFormatError(Exception):
    """A raw file is not in the format this pipeline was built and checked for."""


@dataclass(frozen=True, slots=True)
class FileFacts:
    """What one raw file contained (saved to reports/stage2/files.csv)."""

    file: str
    station_id: str
    names_in_file: tuple[str, ...]
    n_readings: int
    n_dropped_rows: int
    first_label: pd.Timestamp
    last_label: pd.Timestamp


@dataclass(frozen=True, slots=True)
class RawData:
    """All stations stacked: one row per (station slug, 15-minute timestamp label)."""

    readings: pd.DataFrame
    files: list[FileFacts]
    n_identical_duplicates_dropped: int


def station_files(root: Path = RAW_CPCB_DIR) -> list[Path]:
    """Every CSV in any sub-folder of data/raw/cpcb/ (the manifest sits one level up)."""
    return sorted(root.glob("*/*.csv"))


def read_station_file(path: Path) -> tuple[pd.DataFrame, FileFacts]:
    """One station file -> `ts_label` plus one float column per measurement."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), [])
    if header != EXPECTED_HEADER:
        raise RawFormatError(f"{path}: header is not the 29 published CPCB columns: {header}")
    dtypes = {name: "str" for name in ID_COLUMNS} | {name: "float32" for name in SHORT_NAMES}
    try:
        table = pd.read_csv(path, encoding="utf-8-sig", dtype=dtypes)
    except ValueError as err:  # a value that is not a number in a measurement column
        raise RawFormatError(f"{path}: {err}") from err

    is_reading = table["Station ID"].str.startswith("site_", na=False)
    table = table.loc[is_reading]
    station_ids = sorted(table["Station ID"].unique())
    if len(station_ids) != 1:
        raise RawFormatError(f"{path}: expected readings from one station, found {station_ids}")

    labels = table["Timestamp"]
    as_published = labels.notna() & labels.str[-5:].isin(LABEL_SUFFIXES)
    if not as_published.all():
        odd = labels[~as_published].iloc[0]
        raise RawFormatError(
            f"{path}: timestamp {odd!r} does not end in '+0000' or '+0530'. The time-zone fix "
            "knows only those two forms (both mean Delhi time), so check this file by hand first."
        )
    try:
        ts_label = pd.to_datetime(labels.str[:-5], format=LABEL_FORMAT)
    except ValueError as err:
        raise RawFormatError(f"{path}: unreadable timestamp ({err})") from err

    readings = table[list(SHORT_NAMES)].rename(columns=SHORT_NAMES)
    readings.insert(0, "ts_label", ts_label)
    facts = FileFacts(
        file=f"{path.parent.name}/{path.name}",
        station_id=station_ids[0],
        names_in_file=tuple(sorted(table["Station Name"].dropna().unique())),
        n_readings=len(readings),
        n_dropped_rows=int((~is_reading).sum()),
        first_label=ts_label.min(),
        last_label=ts_label.max(),
    )
    return readings.reset_index(drop=True), facts


def load_raw(files: Sequence[Path], stations: pd.DataFrame) -> RawData:
    """Stack station files, name readings by station slug, and resolve overlaps.

    Two files may overlap (e.g. a manual 2023 download that runs into 2024). If they
    agree, the repeat is dropped and counted; if they DISAGREE, we stop: choosing
    one silently would be a cleaning decision hidden inside a loader.
    """
    if not files:
        raise RawFormatError("no station files found in the sub-folders of data/raw/cpcb/")
    slug_of = dict(zip(stations["station_id"], stations["slug"], strict=True))
    parts: list[pd.DataFrame] = []
    facts: list[FileFacts] = []
    for path in files:
        readings, fact = read_station_file(path)
        if fact.station_id not in slug_of:
            raise RawFormatError(f"{path}: station ID {fact.station_id} is not in config/stations.csv")
        parts.append(readings.assign(slug=slug_of[fact.station_id], source_file=fact.file))
        facts.append(fact)

    stacked = pd.concat(parts, ignore_index=True)
    stacked["slug"] = pd.Categorical(stacked["slug"], categories=sorted(slug_of.values()))
    stacked["source_file"] = stacked["source_file"].astype("category")
    key = ["slug", "ts_label"]
    repeated = stacked.loc[stacked.duplicated(key, keep=False)]
    versions = repeated.drop_duplicates(key + MEASUREMENTS)
    conflicting = versions.loc[versions.duplicated(key, keep=False)]
    if not conflicting.empty:
        first = conflicting.iloc[0]
        raise RawFormatError(
            f"files disagree about {first['slug']} at {first['ts_label']} "
            f"({len(conflicting)} conflicting rows in total). Decide which file to trust."
        )
    readings = stacked.drop_duplicates(key).sort_values(key, ignore_index=True)
    columns = ["slug", "ts_label", *MEASUREMENTS, "source_file"]
    return RawData(readings[columns], facts, len(stacked) - len(readings))
