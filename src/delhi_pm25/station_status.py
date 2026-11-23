"""Live forecasts: why a station has no value for the forecast hour, as far as the data can tell.

  reporting      the hour has a value.
  set_aside      readings arrived for the hour, but the cleaning rules set them aside (a one-hour
                 spike in a calm city, or a stuck analyser).
  analyser_dark  the station's other pollutants (PM10, NO2, CO) arrived for the hour, the target
                 did not: the station is online but that analyser gave no value. In heavy smog
                 this is how the worst readings go missing (README, "The most important limitation").
  delayed        nothing at all arrived for the hour, but the station reported within SILENT_AFTER
                 before it: usually the feed is just running late.
  silent         nothing from the station for SILENT_AFTER or longer.

What the data cannot say is WHY an analyser is dark: a deleted extreme reading and routine
maintenance look exactly alike.
"""

from typing import Final

import numpy as np
import pandas as pd

from delhi_pm25.clean import hour_end_utc, true_utc
from delhi_pm25.config import PipelineConfig

SILENT_AFTER: Final = pd.Timedelta(hours=6)
OTHERS: Final = ("pm10", "no2", "co")
# Heavy smog = the smoggiest 10% of hours in the training years, which start at a city median of
# 224.9 ug/m3 (reports/stage2/missing_in_worst_hours.csv; tests/test_station_status.py checks it).
HEAVY_SMOG_UG_M3: Final = 225.0
STATUSES: Final = ("reporting", "set_aside", "analyser_dark", "delayed")


def station_status(readings: pd.DataFrame, features: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """Per station (index): status, last_value and last_value_utc (the newest target reading),
    and last_reading_utc (the newest reading of anything). `readings` are the raw 15-minute
    readings as load_raw returns them; `features` the live rows for the forecast hour."""
    target, issued = config.target, features["hour_end_utc"].iloc[0]
    slug = readings["slug"].astype(str)
    when = true_utc(readings["ts_label"])
    in_hour = hour_end_utc(readings["ts_label"], config.hourly.clock) == issued
    measured = readings[target].notna()
    others = readings[[column for column in OTHERS if column in readings]].notna().any(axis=1)
    newest = readings.assign(slug=slug, when=when)[measured].sort_values("when").groupby("slug").last()
    table = pd.DataFrame({"now": features[f"{target}_lag_0h"].to_numpy()},
                         index=pd.Index(features["slug"].astype(str), name="slug"))
    table["last_value"] = newest[target].reindex(table.index)
    table["last_value_utc"] = newest["when"].reindex(table.index)
    table["last_reading_utc"] = when[measured | others].groupby(slug[measured | others]).max().reindex(table.index)
    conditions = [table["now"].notna(), table.index.isin(slug[measured & in_hour]),
                  table.index.isin(slug[others & in_hour]), table["last_reading_utc"] >= issued - SILENT_AFTER]
    table["status"] = np.select(conditions, list(STATUSES), default="silent")
    return table.drop(columns="now")


def _iso(moment: object) -> str | None:
    return None if pd.isna(moment) else pd.Timestamp(moment).isoformat()


def status_document(readings: pd.DataFrame, features: pd.DataFrame, config: PipelineConfig) -> dict[str, object]:
    """The part of serving/live_forecast.json that explains missing readings."""
    table = station_status(readings, features, config)
    city = features[f"city_{config.target}_median"].iloc[0]
    rows = [{"slug": slug, "status": row.status,
             "last_value": None if pd.isna(row.last_value) else round(float(row.last_value), 1),
             "last_value_utc": _iso(row.last_value_utc), "last_reading_utc": _iso(row.last_reading_utc)}
            for slug, row in table.iterrows()]
    return {"city_median_now": None if pd.isna(city) else round(float(city), 1),
            "heavy_smog_now": bool(city >= HEAVY_SMOG_UG_M3), "station_status": rows}
