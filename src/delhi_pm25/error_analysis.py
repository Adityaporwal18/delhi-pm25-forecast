"""Stage 6: slices of the test-year forecasts that show where the model is weakest.

Every table compares forecasts on the same rows (target measured and every forecast present)
and reports the mean absolute error (MAE) and the bias: the average of forecast minus truth,
so a negative bias means forecasts that are too low.
"""

from collections.abc import Mapping
from typing import Final

import numpy as np
import pandas as pd

from delhi_pm25.clean import HOUR
from delhi_pm25.features import DELHI

SEASON_ORDER: Final = ("winter", "summer", "monsoon", "post-monsoon")
SEASONS: Final = {12: "winter", 1: "winter", 2: "winter", 3: "summer", 4: "summer", 5: "summer",
                  6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon", 10: "post-monsoon", 11: "post-monsoon"}
CHANGE_EDGES: Final = [-np.inf, -100.0, -30.0, 30.0, 100.0, np.inf]
CHANGE_LABELS: Final = ["fell 100+", "fell 30-100", "steady (within 30)", "rose 30-100", "rose 100+"]


def target_season(rows: pd.DataFrame) -> pd.Series:
    """IMD season of each row's target hour, on the Delhi calendar."""
    month = (rows["target_hour_end_utc"] - HOUR).dt.tz_convert(DELHI).dt.month
    return pd.Series(pd.Categorical(month.map(SEASONS), categories=SEASON_ORDER), index=rows.index, name="season")


def change_class(rows: pd.DataFrame, now: str) -> pd.Series:
    """How far PM2.5 actually moved over the 48 hours (target minus the value now, ug/m3).
    'Steady' = within 30 either way. Blank where either value is missing."""
    change = rows["target"] - rows[now]
    return pd.cut(change, CHANGE_EDGES, labels=CHANGE_LABELS).rename("change_48h")


def outcome_tail(rows: pd.DataFrame, share: float) -> pd.Series:
    """Rows whose TARGET hour is among the smoggiest `share` of hours, ranked by the city median
    of the measured target. Chosen by the outcome, which favours forecasts that never pull back
    towards typical values (the 'forecaster's dilemma')."""
    measured = rows["target"].notna()
    city = rows.loc[measured, "target"].groupby(rows.loc[measured, "target_hour_end_utc"]).median()
    return rows["target_hour_end_utc"].map(city) >= city.quantile(1 - share)


def issue_time_tail(rows: pd.DataFrame, share: float, city_now: str) -> pd.Series:
    """Rows whose FORECAST hour is among the smoggiest `share` of hours, ranked by the city
    median known at that moment. Chosen without the outcome, so it is fair to every forecast."""
    city = rows.drop_duplicates("hour_end_utc")[city_now]
    return rows[city_now] >= city.quantile(1 - share)


def errors_by(rows: pd.DataFrame, forecasts: Mapping[str, pd.Series], groups: pd.Series) -> pd.DataFrame:
    """Rows scored, MAE and bias of every forecast per group, on the rows where the target and
    every forecast exist. Rows with a blank group are left out."""
    target = rows["target"].astype("float64")
    table = pd.concat(forecasts, axis=1).astype("float64")
    scored = target.notna() & table.notna().all(axis=1) & groups.notna()
    error = table[scored].sub(target[scored], axis=0)
    by_group = error.groupby(groups[scored], observed=True)
    mae = error.abs().groupby(groups[scored], observed=True).mean().add_suffix("_mae")
    bias = by_group.mean().add_suffix("_bias")
    return pd.concat([by_group.size().rename("n_rows"), mae, bias], axis=1).round(1)
