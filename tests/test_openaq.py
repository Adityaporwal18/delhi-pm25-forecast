"""Tests for turning OpenAQ archive rows into our station-file layout (src/delhi_pm25/openaq.py)."""

from pathlib import Path

import pandas as pd
import pytest

from delhi_pm25.openaq import OpenAQFormatError, StationIdentity, api_rows, station_table
from delhi_pm25.raw_cpcb import EXPECTED_HEADER, read_station_file

RKP = StationIdentity(station_id="site_124", name="R K Puram, Delhi - DPCC")


def archive_rows(*rows: tuple[str, str, str, float]) -> pd.DataFrame:
    """Rows as in an OpenAQ archive file: (datetime, parameter, units, value)."""
    return pd.DataFrame(rows, columns=["datetime", "parameter", "units", "value"])


TWO_READINGS = archive_rows(
    ("2026-11-17T00:45:00+05:30", "pm25", "µg/m³", 89.0),
    ("2026-11-17T00:45:00+05:30", "no2", "ppb", 60.1),
    ("2026-11-17T00:45:00+05:30", "co", "ppb", 1.3),
    ("2026-11-17T01:00:00+05:30", "pm25", "µg/m³", 91.0),
)


def test_rows_become_one_station_file_row_per_reading_time() -> None:
    table = station_table(TWO_READINGS, RKP)
    assert (list(table.columns), table["Timestamp"].tolist()) == (
        EXPECTED_HEADER, ["2026-11-17T00:45:00.000000+0530", "2026-11-17T01:00:00.000000+0530"],
    )


def test_gas_values_are_copied_unchanged_although_openaq_calls_them_ppb() -> None:
    # Given: NO2 and CO labelled "ppb"; checked against our 2025 data, they are CPCB's own units
    # When
    first = station_table(TWO_READINGS, RKP).iloc[0]
    # Then: no unit conversion
    assert (first["PM2.5 (µg/m³)"], first["NO2 (µg/m³)"], first["CO (mg/m³)"]) == (89.0, 60.1, 1.3)


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param(archive_rows(("2026-11-17T00:45:00+00:00", "pm25", "µg/m³", 89.0)), id="offset not Delhi"),
        pytest.param(archive_rows(("2026-11-17T00:45:00+05:30", "pm25", "µg/m³", 89.0),
                                  ("2026-11-17T00:45:00+05:30", "pm25", "µg/m³", 95.0)), id="two values for one reading"),
        pytest.param(archive_rows(("2026-11-17T00:45:00+05:30", "pm25", "ppb", 89.0)), id="PM2.5 not in ug/m3"),
    ],
)
def test_rows_that_cannot_be_trusted_stop_the_conversion(rows: pd.DataFrame) -> None:
    with pytest.raises(OpenAQFormatError):
        station_table(rows, RKP)


def test_converted_file_reads_back_through_the_unchanged_loader(tmp_path: Path) -> None:
    # Given: a converted station file on disk
    path = tmp_path / "r_k_puram_dpcc.csv"
    station_table(TWO_READINGS, RKP).to_csv(path, index=False)
    # When
    readings, facts = read_station_file(path)
    # Then: Delhi wall-clock labels and the same values the loader gives for CPCB files
    assert (facts.station_id, readings["ts_label"].iloc[0], readings["pm25"].iloc[1]) == (
        "site_124", pd.Timestamp("2026-11-17 00:45"), 91.0,
    )


def api_result(ends_local: str, parameter: str, value: float) -> dict[str, object]:
    """One measurement as OpenAQ's /v3/sensors/{id}/measurements returns it (fields we use)."""
    return {"value": value, "parameter": {"name": parameter, "units": "µg/m³"},
            "period": {"datetimeFrom": {"local": "earlier"}, "datetimeTo": {"local": ends_local}}}


def test_api_readings_are_labelled_by_the_end_of_their_period() -> None:
    # Given: the API's reading for 00:30-00:45 Delhi time (the archive and CPCB label it 00:45)
    rows = api_rows([api_result("2026-11-17T00:45:00+05:30", "pm25", 89.0)])
    # When / Then: it reaches the station file with the same label as the archive copy
    assert station_table(rows, RKP)["Timestamp"].tolist() == ["2026-11-17T00:45:00.000000+0530"]
