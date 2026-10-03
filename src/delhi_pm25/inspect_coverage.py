"""Stage 2 inspection, part 1: timestamps, time zone and missing data.

Every function MEASURES a problem and returns a table of evidence; nothing is
filled, dropped or shifted. The hourly table is provisional: it groups the
15-minute readings by their *label* hour, before the time-zone decision is made.
"""

from typing import Final

import numpy as np
import pandas as pd

from delhi_pm25.raw_cpcb import POLLUTANTS
from delhi_pm25.series_checks import gap_lengths

STATION_MET: Final = ["at", "rh", "ws", "wd", "sr", "bp"]
HOURLY_COLUMNS: Final = [*POLLUTANTS, "at"]
SLOT: Final = pd.Timedelta(minutes=15)
SHIFTS_H: Final = np.arange(0.0, 8.5, 0.5)
# Delhi is at 77.2 E, so the sun is highest at about 12:20 IST = 06:50 UTC.
SOLAR_NOON_IST_H: Final = 12.33
SOLAR_NOON_UTC_H: Final = 6.83
GAP_BUCKETS: Final = {"1-3 h": (1, 3), "4-24 h": (4, 24), "1-7 days": (25, 168), "over 7 days": (169, 10**9)}
# Concentration bands (ug/m3) for the "are high readings deleted?" check. The top band
# reaches the analysers' 1000 ug/m3 limit (and the few readings written as exactly 1000).
LEVEL_BANDS: Final = [0, 300, 600, 800, 900, 950, np.inf]


def hourly_by_label(readings: pd.DataFrame) -> pd.DataFrame:
    """Mean of the 15-min readings in each label hour, on a COMPLETE station x hour grid.

    Hours without any row become explicit NaN rows. `pm25_slots` (0-4) counts how many
    15-minute PM2.5 readings went into each hourly value.
    """
    hour = readings["ts_label"].dt.floor("h").rename("hour")
    grouped = readings.groupby([readings["slug"], hour], observed=True)
    hourly = grouped[HOURLY_COLUMNS].mean()
    hourly["pm25_slots"] = grouped["pm25"].count()
    hours = pd.date_range(hour.min(), hour.max(), freq="h", unit=hour.dt.unit, name="hour")
    grid = pd.MultiIndex.from_product([readings["slug"].cat.categories, hours], names=["slug", "hour"])
    hourly = hourly.reindex(grid)
    hourly["pm25_slots"] = hourly["pm25_slots"].fillna(0).astype("int8")
    return hourly


def coverage_table(readings: pd.DataFrame) -> pd.DataFrame:
    """Per station: missing 15-min rows, off-grid labels, and % of slots with each value."""
    labels = readings["ts_label"]
    expected = int((labels.max() - labels.min()) / SLOT) + 1
    by_station = readings.groupby("slug", observed=True)
    table = by_station[POLLUTANTS + STATION_MET].count().mul(100 / expected).round(1).add_suffix("_pct")
    off_grid = labels.ne(labels.dt.floor("15min")).groupby(readings["slug"], observed=True).sum()
    table.insert(0, "missing_rows", expected - by_station.size())
    table.insert(1, "off_grid_labels", off_grid)
    return table


def slots_per_hour(hourly: pd.DataFrame) -> pd.DataFrame:
    """% of each station's hours that contain 0, 1, 2, 3 or 4 PM2.5 readings."""
    shares = hourly["pm25_slots"].groupby(level="slug", observed=True).value_counts(normalize=True)
    return shares.unstack(fill_value=0).mul(100).round(1).add_prefix("slots_")


def gap_table(hourly: pd.DataFrame) -> pd.DataFrame:
    """Per station: how many PM2.5 gaps of each length, the hours they cover, the longest."""
    rows = []
    for slug, pm25 in hourly["pm25"].groupby(level="slug", observed=True):
        gaps = gap_lengths(pm25.notna())
        row: dict[str, object] = {"slug": slug, "longest_gap_h": int(gaps.max()) if len(gaps) else 0}
        for name, (low, high) in GAP_BUCKETS.items():
            inside = gaps[gaps.between(low, high)]
            row[f"gaps_{name}"] = len(inside)
            row[f"hours_{name}"] = int(inside.sum())
        rows.append(row)
    return pd.DataFrame(rows).set_index("slug")


def monthly_coverage(hourly: pd.DataFrame) -> pd.DataFrame:
    """Station x month: % of hours with at least one PM2.5 reading."""
    present = hourly["pm25"].notna()
    month = present.index.get_level_values("hour").strftime("%Y-%m")
    by = [present.index.get_level_values("slug"), month]
    return present.groupby(by, observed=True).mean().mul(100).round(1).unstack()


def temperature_alignment(station_at: pd.Series, open_meteo_utc: pd.Series) -> pd.Series:
    """Correlation of station air temperature with Open-Meteo temperature, per clock offset.

    For each candidate offset s, the station label t is assumed to mean UTC time t - s.
    Whole-hour offsets use labels at :00, half-hour offsets labels at :30, so every
    candidate lands exactly on an Open-Meteo hour. The true offset gives the highest r.
    """
    scan = {}
    for shift in SHIFTS_H:
        minute = 30 if shift % 1 else 0
        picked = station_at[station_at.index.minute == minute]
        candidate_utc = picked.index - pd.Timedelta(hours=float(shift))
        reference = open_meteo_utc.reindex(candidate_utc).to_numpy()
        scan[float(shift)] = pd.Series(picked.to_numpy()).corr(pd.Series(reference))
    return pd.Series(scan, name="r")


def sun_peak_label_hour(station_sr: pd.Series) -> float:
    """Label time of day (decimal hours) at which mean solar radiation is highest."""
    clock = station_sr.index.hour + station_sr.index.minute / 60
    by_time = station_sr.groupby(clock).mean().dropna()
    return float(by_time.idxmax()) if len(by_time) else np.nan


def timezone_evidence(readings: pd.DataFrame, open_meteo_temp: pd.DataFrame) -> pd.DataFrame:
    """Per station: which clock do the labels follow? Two independent physical checks."""
    rows = []
    for slug, station in readings.groupby("slug", observed=True):
        series = station.set_index("ts_label")
        scan = temperature_alignment(series["at"], open_meteo_temp[slug])
        rows.append({
            "slug": slug,
            "sun_peak_label_hour": sun_peak_label_hour(series["sr"]),
            "temp_r_if_utc": round(scan[0.0], 3),
            "temp_r_if_ist": round(scan[5.5], 3),
            "temp_best_offset_h": scan.idxmax() if scan.notna().any() else np.nan,
        })
    table = pd.DataFrame(rows).set_index("slug")
    peak = table["sun_peak_label_hour"]
    nearer_ist = (peak - SOLAR_NOON_IST_H).abs() < (peak - SOLAR_NOON_UTC_H).abs()
    table["sun_says"] = np.select([peak.isna(), nearer_ist], ["no SR sensor", "IST"], default="UTC")
    return table


def missing_after_level(readings: pd.DataFrame, column: str) -> pd.DataFrame:
    """How often the NEXT 15-min reading is blank, by the level of the current reading.

    If blanks were random, the rate would be flat across levels. A rate that climbs
    near the analyser's limit means the worst values are being deleted ("missing not
    at random"). Only back-to-back slots of one station count; assumes readings are
    sorted by slug and label, which load_raw guarantees.
    """
    by_station = readings.groupby("slug", observed=True)
    following = by_station[column].shift(-1)
    back_to_back = by_station["ts_label"].shift(-1) == readings["ts_label"] + SLOT
    current = readings[column].where(back_to_back)
    band = pd.cut(current, LEVEL_BANDS, right=False).rename("band")
    table = following.isna().groupby(band, observed=True).agg(readings="size", next_missing_pct="mean")
    table["next_missing_pct"] = table["next_missing_pct"].mul(100).round(1)
    return table
