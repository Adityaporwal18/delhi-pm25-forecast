"""Tests for reading raw CPCB station files (src/delhi_pm25/raw_cpcb.py)."""

from pathlib import Path

import pandas as pd
import pytest

from delhi_pm25.raw_cpcb import EXPECTED_HEADER, RawFormatError, load_raw, read_station_file

STATIONS = pd.DataFrame({"slug": ["r_k_puram_dpcc"], "station_id": ["site_124"]})


def write_station_csv(path: Path, lines: list[str], header: list[str] = EXPECTED_HEADER) -> Path:
    """Write a CPCB-shaped CSV. Each line is 'station_id|timestamp|pm25' or a raw string."""
    out = [",".join(header)]
    for line in lines:
        if "|" not in line:
            out.append(line)
            continue
        station_id, label, pm25 = line.split("|")
        cells = [station_id, "Delhi", "Delhi", '"R K Puram, Delhi - DPCC"', label, pm25]
        out.append(",".join(cells + [""] * (len(header) - len(cells))))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def test_lone_year_line_between_exports_is_dropped_and_counted(tmp_path: Path) -> None:
    # Given: two yearly exports glued together with a lone "2025" line between them
    path = write_station_csv(tmp_path / "rkp.csv", [
        "site_124|2024-12-31T23:45:00.000000+0000|50.0",
        "2025",
        "site_124|2025-01-01T00:00:00.000000+0000|60.0",
    ])
    # When
    readings, facts = read_station_file(path)
    # Then
    assert (len(readings), facts.n_dropped_rows) == (2, 1)


def test_timestamp_label_is_kept_as_written_without_timezone(tmp_path: Path) -> None:
    # Given: a label that says +0000 (whether it is really UTC is a Stage 2 decision)
    path = write_station_csv(tmp_path / "rkp.csv", ["site_124|2024-01-01T05:30:00.000000+0000|50.0"])
    # When
    readings, _ = read_station_file(path)
    # Then: same wall-clock time, no timezone attached, nothing shifted
    assert readings["ts_label"].iloc[0] == pd.Timestamp("2024-01-01 05:30")


def test_file_with_unexpected_columns_is_rejected(tmp_path: Path) -> None:
    # Given: a header missing the last column
    path = write_station_csv(tmp_path / "odd.csv", [], header=EXPECTED_HEADER[:-1])
    # When / Then
    with pytest.raises(RawFormatError, match="header"):
        read_station_file(path)


def test_explicit_delhi_offset_gives_the_same_label_as_the_cpcb_files(tmp_path: Path) -> None:
    # Given: an OpenAQ-derived file, whose labels say +0530 (Delhi time) explicitly
    path = write_station_csv(tmp_path / "rkp.csv", ["site_124|2026-01-01T05:30:00.000000+0530|50.0"])
    # When
    readings, _ = read_station_file(path)
    # Then: the same Delhi wall-clock label a CPCB "+0000" file would give
    assert readings["ts_label"].iloc[0] == pd.Timestamp("2026-01-01 05:30")


def test_any_other_offset_is_rejected(tmp_path: Path) -> None:
    # Given: an offset that is neither CPCB's "+0000" (really Delhi time) nor Delhi's "+0530"
    path = write_station_csv(tmp_path / "rkp.csv", ["site_124|2024-01-01T05:30:00.000000+0100|50.0"])
    # When / Then: the time-zone fix cannot vouch for it, so the pipeline stops
    with pytest.raises(RawFormatError, match=r"\+0000.*\+0530"):
        read_station_file(path)


def test_station_is_identified_by_id_inside_file_not_file_name(tmp_path: Path) -> None:
    # Given: a manually downloaded file with an arbitrary name in a new sub-folder
    folder = tmp_path / "manual_2023"
    folder.mkdir()
    path = write_station_csv(folder / "download (3).csv", ["site_124|2023-06-01T00:00:00.000000+0000|40.0"])
    # When
    raw = load_raw([path], STATIONS)
    # Then
    assert raw.readings["slug"].tolist() == ["r_k_puram_dpcc"]


def test_station_id_missing_from_config_is_rejected(tmp_path: Path) -> None:
    # Given: a file from a station that config/stations.csv does not know
    path = write_station_csv(tmp_path / "x.csv", ["site_999|2024-01-01T00:00:00.000000+0000|40.0"])
    # When / Then
    with pytest.raises(RawFormatError, match="site_999"):
        load_raw([path], STATIONS)


def test_identical_overlap_between_files_is_dropped_once(tmp_path: Path) -> None:
    # Given: two files that both contain the same reading for the same 15-minute slot
    line = "site_124|2024-01-01T00:00:00.000000+0000|40.0"
    a = write_station_csv(tmp_path / "a.csv", [line])
    b = write_station_csv(tmp_path / "b.csv", [line, "site_124|2024-01-01T00:15:00.000000+0000|41.0"])
    # When
    raw = load_raw([a, b], STATIONS)
    # Then
    assert (len(raw.readings), raw.n_identical_duplicates_dropped) == (2, 1)


def test_conflicting_overlap_between_files_is_rejected(tmp_path: Path) -> None:
    # Given: two files that disagree about the same 15-minute slot
    a = write_station_csv(tmp_path / "a.csv", ["site_124|2024-01-01T00:00:00.000000+0000|40.0"])
    b = write_station_csv(tmp_path / "b.csv", ["site_124|2024-01-01T00:00:00.000000+0000|99.0"])
    # When / Then: picking one silently would be a hidden cleaning decision
    with pytest.raises(RawFormatError, match="disagree"):
        load_raw([a, b], STATIONS)
