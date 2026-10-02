import numpy as np
import pandas as pd

from delhi_aqi.inspect_coverage import (
    HOURLY_COLUMNS,
    hourly_by_label,
    missing_after_level,
    temperature_alignment,
)


def readings_frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """Minimal stacked-readings table: (slug, label, pm25); other columns empty."""
    slugs, labels, pm25 = zip(*rows, strict=True)
    frame = pd.DataFrame({column: np.nan for column in HOURLY_COLUMNS}, index=range(len(rows)))
    frame["pm25"] = pm25
    frame.insert(0, "ts_label", pd.to_datetime(list(labels)))
    frame.insert(0, "slug", pd.Categorical(slugs, categories=["a", "b"]))
    return frame


def test_hourly_by_label_makes_missing_hours_explicit_rows() -> None:
    # Given: station a has readings at 00:00, 00:15 and 02:00; station b only one empty slot
    readings = readings_frame([
        ("a", "2024-01-01 00:00", 10.0), ("a", "2024-01-01 00:15", 20.0),
        ("a", "2024-01-01 02:00", 30.0), ("b", "2024-01-01 00:00", np.nan),
    ])
    # When
    hourly = hourly_by_label(readings)
    # Then: every station gets every hour 00..02, and slots count real PM2.5 readings
    assert (len(hourly), hourly.loc["a", "pm25_slots"].tolist()) == (6, [2, 0, 1])


def test_hourly_by_label_averages_the_readings_inside_the_hour() -> None:
    readings = readings_frame([("a", "2024-01-01 00:00", 10.0), ("a", "2024-01-01 00:15", 20.0)])
    hourly = hourly_by_label(readings)
    assert hourly.loc[("a", pd.Timestamp("2024-01-01 00:00")), "pm25"] == 15.0


def test_temperature_alignment_peaks_at_the_true_clock_offset() -> None:
    # Given: a daily temperature cycle; Open-Meteo hourly on UTC, station labelled UTC+5:30
    utc = pd.date_range("2024-03-01", periods=10 * 96, freq="15min")
    temperature = 25 + 8 * np.sin(2 * np.pi * (utc.hour + utc.minute / 60 - 9) / 24)
    open_meteo = pd.Series(temperature, index=utc)[utc.minute == 0]
    station = pd.Series(temperature, index=utc + pd.Timedelta(hours=5.5))
    # When
    scan = temperature_alignment(station, open_meteo)
    # Then
    assert scan.idxmax() == 5.5


def test_missing_after_level_shows_blanks_that_follow_high_readings() -> None:
    # Given: a 960 reading is followed by a blank slot; ordinary readings are not
    readings = readings_frame([
        ("a", "2024-01-01 00:00", 100.0), ("a", "2024-01-01 00:15", 960.0),
        ("a", "2024-01-01 00:30", np.nan), ("a", "2024-01-01 00:45", 120.0),
        ("a", "2024-01-01 01:00", 130.0),
    ])
    # When
    table = missing_after_level(readings, "pm25")
    # Then: bands [0, 300) and [950, ...): next reading blank 0% and 100% of the time
    assert table["next_missing_pct"].tolist() == [0.0, 100.0]
