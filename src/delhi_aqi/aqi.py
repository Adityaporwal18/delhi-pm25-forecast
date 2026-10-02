"""CPCB National Air Quality Index (AQI), computed from pollutant concentrations.

HOW THE INDEX WORKS (plain language)
  1. Each pollutant is first AVERAGED: over the last 24 hours (PM2.5, PM10, NO2,
     SO2, NH3) or the last 8 hours (CO, O3). This is why the official AQI moves
     slowly -- it cannot jump from 188 to 465 within one hour.
  2. Each average is converted to a 0-500 "sub-index" by straight-line
     interpolation between CPCB breakpoints. E.g. PM2.5 30 -> 50, 60 -> 100,
     so PM2.5 45 -> 75.
  3. AQI = the WORST (largest) sub-index. That pollutant is the "prominent" one.
  4. Validity: an average needs enough hours of data (16 of 24; for the 8-hour
     ones we use 6 of 8), and an AQI needs at least 3 sub-indices, one of which
     must be PM2.5 or PM10.

APPROXIMATIONS (say these out loud if asked in an interview)
  * CPCB prints breakpoints as integer ranges (0-30, 31-60, ...). We interpolate
    between the band edges as continuous lines (30 -> 50, 60 -> 100); differences
    are below 1 index point.
  * The top of the "Severe" band is not printed by CPCB. We extend it with the
    width of the band below (common practice), and cap the index at 500.
  * The minimum hours for the 8-hour averages (6 of 8) is our choice. Lead (Pb)
    is part of the official index but is not in our data.
"""

from typing import Final

import numpy as np
import pandas as pd

INDEX_KNOTS: Final = np.array([0.0, 50.0, 100.0, 200.0, 300.0, 400.0, 500.0])

# Concentration at the edges of the bands Good | Satisfactory | Moderate | Poor |
# Very Poor | Severe. Units are ug/m3, except CO in mg/m3 (as in the CPCB files).
CONCENTRATION_KNOTS: Final[dict[str, np.ndarray]] = {
    "pm25": np.array([0.0, 30, 60, 90, 120, 250, 380]),
    "pm10": np.array([0.0, 50, 100, 250, 350, 430, 510]),
    "no2": np.array([0.0, 40, 80, 180, 280, 400, 520]),
    "o3": np.array([0.0, 50, 100, 168, 208, 748, 1287]),
    "co": np.array([0.0, 1, 2, 10, 17, 34, 51]),
    "so2": np.array([0.0, 40, 80, 380, 800, 1600, 2400]),
    "nh3": np.array([0.0, 200, 400, 800, 1200, 1800, 2400]),
}

# Averaging window and the minimum number of valid hourly values inside it.
AVERAGING: Final[dict[str, tuple[str, int]]] = {
    "pm25": ("24h", 16), "pm10": ("24h", 16), "no2": ("24h", 16), "so2": ("24h", 16),
    "nh3": ("24h", 16), "co": ("8h", 6), "o3": ("8h", 6),
}


def sub_index(pollutant: str, concentration: np.ndarray) -> np.ndarray:
    """0-500 sub-index for an array of averaged concentrations (NaN stays NaN)."""
    index = np.interp(concentration, CONCENTRATION_KNOTS[pollutant], INDEX_KNOTS)
    return np.where(np.isnan(concentration), np.nan, index)


def aqi_from_hourly(hourly: pd.DataFrame) -> pd.DataFrame:
    """AQI for ONE station, from hourly concentrations.

    `hourly` has a DatetimeIndex (one row per hour) and any of the pollutant
    columns pm25, pm10, no2, so2, nh3, co, o3. Returns si_<pollutant> columns,
    `aqi` and `prominent` (name of the pollutant with the worst sub-index).
    Averages use time-based windows ("the last 24 hours"), so a missing row
    shortens the window instead of silently reaching further back.
    """
    pollutants = [p for p in AVERAGING if p in hourly.columns]
    sub = pd.DataFrame(index=hourly.index)
    for p in pollutants:
        window, min_hours = AVERAGING[p]
        average = hourly[p].rolling(window, min_periods=min_hours).mean()
        sub[f"si_{p}"] = sub_index(p, average.to_numpy(dtype=float))

    n_valid = sub.notna().sum(axis=1)
    has_pm = sub.filter(items=["si_pm25", "si_pm10"]).notna().any(axis=1)
    valid = (n_valid >= 3) & has_pm

    values = sub.to_numpy()
    worst = np.where(np.isnan(values), -np.inf, values).argmax(axis=1)
    result = sub.copy()
    result["aqi"] = sub.max(axis=1).where(valid)
    result["prominent"] = pd.Series(np.array(pollutants)[worst], index=sub.index).where(valid)
    return result
