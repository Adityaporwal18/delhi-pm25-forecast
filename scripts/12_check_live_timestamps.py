"""Live forecasts, stage C: check the OpenAQ timestamps independently before trusting them.

Stage 2 proved that CPCB's labels are Delhi time. OpenAQ is a different pipeline, so its labels
are checked again, per station, three ways:
  same readings  OpenAQ's copy of 1-3 Dec 2025 against our verified 2025 data, reading by
                 reading: correct labels match at zero shift and not at +-1 h.
  temperature    2026 station air temperature against Open-Meteo, at clock offsets 0-8 h: Delhi
                 labels fit best near 5.5 h (UTC = label - 5:30); UTC labels would fit at 0 h.
  ozone          sunlight makes ozone, so it rises and falls with the sun. OpenAQ has no solar-
                 radiation sensor, so ozone stands in: each station's average daily ozone curve in
                 Jan-Nov 2026 should line up with Jan-Nov 2025 (verified) at zero lag, not 5-6 h.

Output:  reports/live/timestamp_check.csv
Usage:   .venv/bin/python scripts/12_check_live_timestamps.py
"""

import gzip
import io
import sys
from typing import Final

import numpy as np
import pandas as pd
import requests

from delhi_pm25.inspect_coverage import temperature_alignment
from delhi_pm25.paths import INTERIM_DIR, PROJECT_ROOT, REPORTS_DIR
from delhi_pm25.weather import load_station_weather

RAW_PARQUET: Final = INTERIM_DIR / "cpcb_15min_raw.parquet"
LOCATIONS_CSV: Final = PROJECT_ROOT / "config" / "openaq_locations.csv"
ARCHIVE: Final = "https://openaq-data-archive.s3.amazonaws.com/records/csv.gz"
OUT: Final = REPORTS_DIR / "live" / "timestamp_check.csv"
OVERLAP_DAYS: Final = pd.date_range("2025-12-01", "2025-12-03")
SHIFTS_MIN: Final = (0, -60, 60)
MIN_READINGS: Final = 500
LAGS: Final = range(-6, 7)


def openaq_overlap(session: requests.Session, location: int) -> pd.Series:
    """OpenAQ's PM2.5 for OVERLAP_DAYS, indexed by its Delhi-time label."""
    parts = []
    for day in OVERLAP_DAYS:
        url = f"{ARCHIVE}/locationid={location}/year=2025/month=12/location-{location}-{day:%Y%m%d}.csv.gz"
        response = session.get(url, timeout=60)
        if response.ok:
            rows = pd.read_csv(io.BytesIO(gzip.decompress(response.content)), usecols=["datetime", "parameter", "value"])
            parts.append(rows[rows["parameter"] == "pm25"])
    rows = pd.concat(parts) if parts else pd.DataFrame(columns=["datetime", "value"])
    return pd.Series(rows["value"].to_numpy(dtype=float), index=pd.to_datetime(rows["datetime"].str[:19]))


def identical_share(theirs: pd.Series, ours: pd.Series, minutes: int) -> float:
    shifted = pd.Series(theirs.to_numpy(), index=theirs.index + pd.Timedelta(minutes=minutes))
    both = pd.concat([shifted, ours], axis=1, join="inner").dropna()
    return round(float((np.abs(both.iloc[:, 0] - both.iloc[:, 1]) < 1e-3).mean()) * 100, 1) if len(both) else np.nan


def ozone_lag(new: pd.Series, old: pd.Series) -> float:
    """Lag (h) at which the 2026 average daily ozone curve best matches 2025's (same months)."""
    curves = [series.groupby(series.index.hour).mean().reindex(range(24)) for series in (new, old)]
    if any(curve.isna().any() for curve in curves):
        return np.nan
    scores = {lag: np.corrcoef(np.roll(curves[0].to_numpy(), -lag), curves[1].to_numpy())[0, 1] for lag in LAGS}
    return float(max(scores, key=scores.__getitem__))


def station_row(slug: str, raw: pd.DataFrame, temperature: pd.DataFrame, overlap: pd.Series) -> dict[str, object]:
    labels = raw.set_index("ts_label")
    in_months = labels.index.month <= 11
    new, old = labels[(labels.index.year == 2026) & in_months], labels[(labels.index.year == 2025) & in_months]
    row: dict[str, object] = {"slug": slug}
    for minutes in SHIFTS_MIN:
        row[f"identical_pct_shift_{minutes:+d}min"] = identical_share(overlap, labels["pm25"], minutes)
    row["temperature_readings_2026"] = int(new["at"].notna().sum())
    if row["temperature_readings_2026"] >= MIN_READINGS:
        scan = temperature_alignment(new["at"], temperature[slug])
        row |= {"temp_r_if_utc": round(scan.loc[0.0], 3), "temp_r_if_delhi": round(scan.loc[5.5], 3),
                "temp_best_offset_h": float(scan.idxmax())}
    return row | {"ozone_lag_h": ozone_lag(new["o3"], old["o3"])}


def main() -> int:
    raw = pd.read_parquet(RAW_PARQUET, columns=["slug", "ts_label", "pm25", "at", "o3"])
    raw["slug"] = raw["slug"].astype(str)
    locations = pd.read_csv(LOCATIONS_CSV).set_index("slug")["openaq_location_id"]
    weather = load_station_weather(list(locations.index))
    temperature = weather.pivot(index="time_utc", columns="slug", values="temperature_2m")
    temperature.index = temperature.index.tz_convert(None)
    session = requests.Session()
    table = pd.DataFrame([station_row(slug, raw[raw["slug"] == slug], temperature, openaq_overlap(session, int(location)))
                          for slug, location in locations.items()])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT, index=False)
    same = table["identical_pct_shift_+0min"]
    print(f"same readings, 1-3 Dec 2025: identical at zero shift median {same.median()}% (lowest {same.min()}%, "
          f"{table['slug'][same.idxmin()]}) | at -60 min median {table['identical_pct_shift_-60min'].median()}% | +60 min {table['identical_pct_shift_+60min'].median()}%")
    checked = table.dropna(subset=["temp_best_offset_h"])
    print(f"temperature (2026, {len(checked)} stations): best offset {checked['temp_best_offset_h'].value_counts().sort_index().to_dict()}")
    print(f"ozone curve lag 2026 vs 2025 (h): {table['ozone_lag_h'].value_counts().sort_index().to_dict()}")
    print(f"Wrote {OUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
