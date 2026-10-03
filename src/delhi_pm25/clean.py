"""Stage 2 cleaning, part 1: 15-minute readings -> one row per station per hour, in true UTC.

D1  CPCB labels are Delhi time (IST) wrongly marked "+0000". True UTC = label - 5:30
    (India has no daylight saving, so the offset never changes).
D2  An hourly value is the mean of the 15-min readings present (at least `min_readings`).
D6  Every station gets every hour, blank when nothing was measured, so "24 rows back"
    always means "24 hours back".

Each row is stamped with the END of its hour (`hour_end_utc`): the moment its value is
complete and could be known. That is safe whether CPCB labels mark the start or the end
of an interval. Only the 7 pollutants are kept: station weather sensors are dropped (D4.4,
Open-Meteo replaces them), NO/NOx overlap NO2, and benzene etc. are mostly empty.
"""

from typing import Final, assert_never

import numpy as np
import pandas as pd

from delhi_pm25.config import CeilingRule, Clock, HourlyRules
from delhi_pm25.raw_cpcb import POLLUTANTS

IST_OFFSET: Final = pd.Timedelta(hours=5, minutes=30)
HOUR: Final = pd.Timedelta(hours=1)


class GridError(Exception):
    """The hourly table is not one row per station per hour over one shared time span."""


def true_utc(labels: pd.Series) -> pd.Series:
    """CPCB labels (IST wall-clock, written as UTC) -> real UTC instants."""
    return (labels - IST_OFFSET).dt.tz_localize("UTC")


def hour_end_utc(labels: pd.Series, clock: Clock) -> pd.Series:
    """End of the hour each 15-min label belongs to, as a UTC instant.

    "ist": Delhi clock hours, e.g. labels 10:00-10:45 IST -> ends 11:00 IST = 05:30 UTC.
    "utc": whole UTC hours, e.g. labels 10:00-10:15 IST (04:30-04:45 UTC) -> ends 05:00 UTC.
    """
    match clock:
        case "ist":
            return true_utc(labels.dt.floor("h") + HOUR)
        case "utc":
            return true_utc(labels).dt.floor("h") + HOUR
        case unreachable:
            assert_never(unreachable)


def to_hourly(readings: pd.DataFrame, rules: HourlyRules, ceiling: CeilingRule) -> pd.DataFrame:
    """Average 15-min readings into a complete station x hour grid.

    Columns: slug, hour_end_utc, one mean per pollutant (blank when fewer than
    `min_readings` readings), `n_<pollutant>` = how many readings went into it, and
    `<pollutant>_at_ceiling` = a reading in that hour hit the analyser's limit.
    """
    end = hour_end_utc(readings["ts_label"], rules.clock).rename("hour_end_utc")
    grouped = readings.groupby([readings["slug"], end], observed=True)
    counts = grouped[POLLUTANTS].count()
    means = grouped[POLLUTANTS].mean().where(counts >= rules.min_readings).astype("float32")
    at_ceiling = grouped[list(ceiling.pollutants)].max().ge(ceiling.ug_m3)
    hourly = pd.concat([means, counts.add_prefix("n_"), at_ceiling.add_suffix("_at_ceiling")], axis=1)

    slugs = readings["slug"].cat.categories
    hours = pd.date_range(end.min(), end.max(), freq="h", unit=end.dt.unit, name="hour_end_utc")
    hourly = hourly.reindex(pd.MultiIndex.from_product([slugs, hours], names=["slug", "hour_end_utc"]))
    count_cols = [f"n_{p}" for p in POLLUTANTS]
    flag_cols = [f"{p}_at_ceiling" for p in ceiling.pollutants]
    hourly[count_cols] = hourly[count_cols].fillna(0).astype("int8")
    hourly[flag_cols] = hourly[flag_cols].fillna(False).astype("bool")
    hourly = hourly.reset_index()
    hourly["slug"] = pd.Categorical(hourly["slug"], categories=slugs)
    return hourly


def check_complete_grid(hourly: pd.DataFrame) -> None:
    """Raise GridError unless every station has every hour exactly once, in order,
    over the same first-to-last span. Lag features silently go wrong otherwise."""
    by_station = hourly.groupby("slug", observed=True)["hour_end_utc"]
    step = by_station.diff()
    broken = (step.notna() & (step != HOUR)).to_numpy()
    if broken.any():
        row = hourly.iloc[int(np.argmax(broken))]
        raise GridError(f"{row['slug']}: hour {row['hour_end_utc']} is missing, repeated or out of order")
    spans = by_station.agg(["min", "max"])
    odd = spans.index[(spans["min"] != spans["min"].min()) | (spans["max"] != spans["max"].max())]
    if len(odd):
        raise GridError(f"stations cover a different span of hours than the rest: {list(odd)}")
