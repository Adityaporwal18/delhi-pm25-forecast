"""OpenAQ archive rows -> the station-file layout the loader already reads (raw_cpcb.EXPECTED_HEADER).

OpenAQ copies CPCB's 15-minute feed. Checked against our training data (6 stations, 1-10 Dec
2025): the PM2.5 values are identical with no time shift, and each reading is stamped with the
END of its 15 minutes in Delhi time (+05:30), exactly like CPCB's own labels. OpenAQ calls the
gases "ppb", but the values are CPCB's own units (NO2 in ug/m3, CO in mg/m3: the ratio to our
data is exactly 1.00000), so every value is copied unchanged, never converted.
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from delhi_pm25.raw_cpcb import EXPECTED_HEADER

DELHI_OFFSET: Final = "+05:30"
LABEL_TAIL: Final = ".000000+0530"
PM_UNITS: Final = frozenset({"\u00b5g/m\u00b3", "\u03bcg/m\u00b3"})
COLUMN_FOR: Final = {
    "pm25": "PM2.5 (µg/m³)",
    "pm10": "PM10 (µg/m³)",
    "no": "NO (µg/m³)",
    "no2": "NO2 (µg/m³)",
    "nox": "NOx (ppb)",
    "so2": "SO2 (µg/m³)",
    "co": "CO (mg/m³)",
    "o3": "Ozone (µg/m³)",
    "temperature": "AT (°C)",
    "relativehumidity": "RH (%)",
    "wind_speed": "WS (m/s)",
    "wind_direction": "WD (deg)",
}


class OpenAQFormatError(Exception):
    """Archive rows that do not look like the CPCB feed we checked, so they cannot be trusted."""


@dataclass(frozen=True, slots=True)
class StationIdentity:
    """How the station appears in our files: CPCB station ID and name (config/stations.csv)."""

    station_id: str
    name: str


def _check(records: pd.DataFrame, station: StationIdentity) -> pd.DataFrame:
    offsets = records["datetime"].str[19:]
    if not offsets.eq(DELHI_OFFSET).all():
        odd = sorted(set(offsets) - {DELHI_OFFSET})[:3]
        raise OpenAQFormatError(f"{station.name}: times must end in {DELHI_OFFSET}, found {odd}")
    known = records[records["parameter"].isin(COLUMN_FOR)]
    pm_units = set(known.loc[known["parameter"] == "pm25", "units"])
    if not pm_units <= PM_UNITS:
        raise OpenAQFormatError(f"{station.name}: PM2.5 must be in ug/m3, found {sorted(pm_units)}")
    values = known.groupby(["datetime", "parameter"])["value"].nunique()
    if (values > 1).any():
        moment, parameter = values[values > 1].index[0]
        raise OpenAQFormatError(f"{station.name}: two different {parameter} values at {moment}")
    return known


def station_table(records: pd.DataFrame, station: StationIdentity) -> pd.DataFrame:
    """Long archive rows (datetime, parameter, units, value) -> one row per reading time, with
    the columns and label format of the CPCB station files. Unknown parameters are ignored."""
    known = _check(records, station)
    wide = known.pivot_table(index="datetime", columns="parameter", values="value", aggfunc="first")
    table = pd.DataFrame({column: np.nan for column in EXPECTED_HEADER}, index=wide.index)
    table["Station ID"], table["State"], table["City"] = station.station_id, "Delhi", "Delhi"
    table["Station Name"] = station.name
    table["Timestamp"] = wide.index.str[:19] + LABEL_TAIL
    for parameter, column in COLUMN_FOR.items():
        if parameter in wide.columns:
            table[column] = wide[parameter]
    return table.sort_index().reset_index(drop=True)[EXPECTED_HEADER]
