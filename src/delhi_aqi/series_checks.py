"""Small checks on ONE station's time series, used by the Stage 2 inspection.

Every function assumes the series is in time order on a COMPLETE regular grid:
one row per hour, missing readings stored as NaN. If whole rows were missing,
"the previous value" (shift) would silently be some other hour -- the same trap
that breaks lag features in Stage 3.
"""

import pandas as pd


def _runs(values: pd.Series) -> pd.DataFrame:
    """One row per run of consecutive equal values: the value and how long the run lasts.

    [5, 5, 7, 5] -> runs (5, 2), (7, 1), (5, 1). NaN never equals NaN, so every
    missing value forms its own run of length 1 with value NaN.
    """
    run_id = values.ne(values.shift()).cumsum()
    return values.groupby(run_id).agg(value="first", length="size")


def gap_lengths(present: pd.Series) -> pd.Series:
    """Length (in rows) of every run of consecutive missing readings.

    `present` is True where a reading exists.
    """
    runs = _runs(present.astype("int8"))
    return runs.loc[runs["value"] == 0, "length"].reset_index(drop=True)


def flat_runs(values: pd.Series, min_hours: int) -> pd.Series:
    """Length of every run of identical consecutive readings lasting at least `min_hours`.

    Real air quality always wobbles a little; the exact same value for many hours
    usually means a stuck instrument or a value copied forward by the data logger.
    """
    runs = _runs(values)
    long_runs = runs["value"].notna() & (runs["length"] >= min_hours)
    return runs.loc[long_runs, "length"].reset_index(drop=True)


def isolated_spikes(values: pd.Series, jump: float) -> pd.Series:
    """True where a reading is more than `jump` above BOTH its neighbours.

    Jumping up and straight back down within one step is typical of a glitch;
    a real pollution episode (e.g. Diwali night) rises and stays high for hours,
    so it is NOT flagged here.
    """
    rise = values - values.shift(1)
    fall = values - values.shift(-1)
    return (rise > jump) & (fall > jump)
