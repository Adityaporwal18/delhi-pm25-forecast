"""Tests for why a station has no PM2.5 value for the forecast hour (src/delhi_pm25/station_status.py)."""

import numpy as np
import pandas as pd

from delhi_pm25.config import PipelineConfig
from delhi_pm25.paths import REPORTS_DIR
from delhi_pm25.station_status import HEAVY_SMOG_UG_M3, station_status, status_document

ISSUED = pd.Timestamp("2026-11-22 16:30", tz="UTC")  # the hour 21:00-22:00 Delhi time
NAN = np.nan


def readings(*rows: tuple[str, str, float, float]) -> pd.DataFrame:
    """15-minute readings as load_raw returns them: (station, Delhi label, PM2.5, PM10)."""
    table = pd.DataFrame(rows, columns=["slug", "ts_label", "pm25", "pm10"]).assign(no2=NAN, co=NAN)
    table["ts_label"] = pd.to_datetime(table["ts_label"])
    return table


def features(now: dict[str, float], city_median: float = 150.0) -> pd.DataFrame:
    """The live feature rows for the forecast hour (only the columns the status reads)."""
    return pd.DataFrame({"slug": list(now), "hour_end_utc": ISSUED, "pm25_lag_0h": list(now.values()),
                         "city_pm25_median": city_median})


READINGS = readings(
    ("reporting", "2026-11-22 21:15", 100.0, 180.0),
    ("set_aside", "2026-11-22 21:15", 640.0, 700.0),
    ("dark", "2026-11-22 18:00", 300.0, 400.0),
    ("dark", "2026-11-22 21:15", NAN, 450.0),
    ("delayed", "2026-11-22 19:00", 90.0, 160.0),
    ("silent", "2026-11-22 10:00", 80.0, 150.0),
)
NOW = {"reporting": 100.0, "set_aside": NAN, "dark": NAN, "delayed": NAN, "silent": NAN}


def test_each_missing_reading_gets_the_reason_the_data_can_show(config: PipelineConfig) -> None:
    # Given: PM2.5 now at one station; at the others, a value set aside by cleaning, PM10 without
    # PM2.5, nothing for 3 hours, and nothing for 12 hours
    # When
    table = station_status(READINGS, features(NOW), config)
    # Then
    assert table["status"].to_dict() == {"reporting": "reporting", "set_aside": "set_aside", "dark": "analyser_dark",
                                         "delayed": "delayed", "silent": "silent"}


def test_a_dark_analyser_reports_its_last_value_and_when_it_came(config: PipelineConfig) -> None:
    table = station_status(READINGS, features(NOW), config)
    assert (table.loc["dark", "last_value"], table.loc["dark", "last_value_utc"]) == (300.0, pd.Timestamp("2026-11-22 12:30", tz="UTC"))


def test_the_document_flags_heavy_smog_from_the_city_median(config: PipelineConfig) -> None:
    calm, smoggy = (status_document(READINGS, features(NOW, city), config) for city in (150.0, 300.0))
    assert (calm["heavy_smog_now"], smoggy["heavy_smog_now"], len(smoggy["station_status"])) == (False, True, 5)


def test_heavy_smog_starts_where_the_training_years_smoggiest_tenth_starts() -> None:
    # Given: the evaluation report of blank readings in the smoggiest hours
    table = pd.read_csv(REPORTS_DIR / "stage2" / "missing_in_worst_hours.csv").set_index(["period", "hours"])
    # When / Then: the site's heavy-smog threshold is that report's number, not a guess
    assert HEAVY_SMOG_UG_M3 == round(table.loc[("train", "smoggiest 10.0%"), "city_median_from_ug_m3"])
