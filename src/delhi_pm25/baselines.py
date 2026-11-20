"""Stage 4: the two baselines every model must beat, and the one way all forecasts are scored.

Persistence: PM2.5 in 48 hours = PM2.5 now (the feature `<target>_lag_0h`).
Climatology: the average at the same station and Delhi clock hour, on days within N either side
of the same calendar day, from training years only ([baselines] in config/pipeline.toml).
Scoring: mean absolute error (MAE) on the rows where the target AND every forecast exist, so all
methods are judged on exactly the same hours; repeated for the smoggiest 10% and 1% of hours.
"""

from collections.abc import Mapping
from typing import Final

import numpy as np
import pandas as pd

from delhi_pm25.clean import HOUR
from delhi_pm25.config import BaselineSettings
from delhi_pm25.features import DELHI

DAYS: Final = np.arange(1, 367)
SCORED_TAILS: Final = (0.10, 0.01)


def calendar_slot(stamps: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Delhi clock hour (0-23) and calendar day (1-366) of the hour that ENDS at each stamp.
    Days count on a leap-year calendar (1 March is day 61 every year), so dates line up
    across years."""
    start = (stamps - HOUR).dt.tz_convert(DELHI)
    short_year_after_feb = (~start.dt.is_leap_year & (start.dt.month > 2)).astype("int64")
    hour = start.dt.hour.astype("int64").rename("hour")
    day = (start.dt.dayofyear.astype("int64") + short_year_after_feb).rename("day")
    return hour, day


def climatology_table(history: pd.DataFrame, settings: BaselineSettings) -> pd.DataFrame:
    """Average target per (station, Delhi clock hour) row and calendar-day column (1-366), over
    the days within `climatology_days_either_side` of each day (31 Dec wraps to 1 Jan). Blank
    where fewer than `climatology_min_values` values fall in the window. `history` must hold
    training rows only: slug, target_hour_end_utc, target."""
    known = history.dropna(subset=["target"])
    hour, day = calendar_slot(known["target_hour_end_utc"])
    by_slot = known["target"].astype("float64").groupby([known["slug"].astype(str), hour, day])
    sums = by_slot.sum().unstack("day").reindex(columns=DAYS).fillna(0.0)
    counts = by_slot.count().unstack("day").reindex(columns=DAYS).fillna(0)
    width = settings.climatology_days_either_side
    shifts = range(-width, width + 1)
    window_sum = sum(np.roll(sums.to_numpy(), shift, axis=1) for shift in shifts)
    window_n = sum(np.roll(counts.to_numpy(), shift, axis=1) for shift in shifts)
    enough = window_n >= settings.climatology_min_values
    means = np.divide(window_sum, window_n, out=np.full(window_sum.shape, np.nan), where=enough)
    return pd.DataFrame(means, index=sums.index, columns=DAYS)


def climatology(rows: pd.DataFrame, table: pd.DataFrame) -> pd.Series:
    """The climatology forecast for each row's target hour; blank where the table has none."""
    hour, day = calendar_slot(rows["target_hour_end_utc"])
    keys = pd.MultiIndex.from_arrays([rows["slug"].astype(str), hour])
    position = table.index.get_indexer(keys)
    found = table.to_numpy()[position, day.to_numpy() - 1]
    return pd.Series(np.where(position >= 0, found, np.nan), index=rows.index, name="climatology")


def score(rows: pd.DataFrame, forecasts: Mapping[str, pd.Series]) -> pd.DataFrame:
    """MAE of each forecast on the rows where the target and EVERY forecast exist (the same rows
    for all methods): all hours, then the smoggiest 10% and 1% of target hours, ranked by the
    city median of the target. n_target_rows minus n_rows = rows some forecast could not cover."""
    target = rows["target"].astype("float64")
    measured = target.notna()
    scored = measured & pd.concat(forecasts, axis=1).notna().all(axis=1)
    city = target[measured].groupby(rows.loc[measured, "target_hour_end_utc"]).median()
    smog = rows["target_hour_end_utc"].map(city)
    tails = {f"smoggiest {share:.1%}": city.quantile(1 - share) for share in SCORED_TAILS}
    table = []
    for name, cutoff in ({"all hours": city.min()} | tails).items():
        inside = smog >= cutoff
        chosen = scored & inside
        row = {
            "hours": name, "city_median_from_ug_m3": round(float(cutoff), 1),
            "n_hours": rows.loc[measured & inside, "target_hour_end_utc"].nunique(),
            "n_target_rows": int((measured & inside).sum()), "n_rows": int(chosen.sum()),
        }
        for method, forecast in forecasts.items():
            error = (forecast[chosen].astype("float64") - target[chosen]).abs()
            row[f"{method}_mae"] = round(float(error.mean()), 2)
        table.append(row)
    return pd.DataFrame(table)
