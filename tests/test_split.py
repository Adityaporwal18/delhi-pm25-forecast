"""Tests for the time split and its 48-hour gap (src/delhi_pm25/split.py)."""

import pandas as pd
import pytest

from delhi_pm25.clean import HOUR
from delhi_pm25.config import load_config
from delhi_pm25.paths import PIPELINE_TOML
from delhi_pm25.split import EmbargoError, check_embargo, folds, split

CONFIG = load_config(PIPELINE_TOML)
HORIZON = CONFIG.features.horizon_hours
VALIDATION, TEST = folds(CONFIG)


def feature_rows(first: str, last: str) -> pd.DataFrame:
    """Two stations, one forecast row per hour, each with its target hour `HORIZON` hours later."""
    hours = pd.date_range(first, last, freq="h", tz="UTC", unit="us")
    rows = pd.concat([pd.DataFrame({"slug": slug, "hour_end_utc": hours}) for slug in ("a", "b")], ignore_index=True)
    rows["target_hour_end_utc"] = rows["hour_end_utc"] + HORIZON * HOUR
    rows["target"] = 100.0
    return rows


ROWS = feature_rows("2023-12-20 00:30", "2025-01-10 00:30")


def test_no_training_row_has_a_target_hour_on_or_after_the_test_start() -> None:
    # Given / When
    train, _ = split(ROWS, TEST, embargo_hours=HORIZON)
    # Then: rows are stamped with the END of their hour, so a target hour that starts
    # before the test start ends at or before it
    assert train["target_hour_end_utc"].max() <= CONFIG.test_start


@pytest.mark.parametrize("fold", folds(CONFIG), ids=lambda fold: fold.name)
def test_the_gap_before_each_boundary_is_exactly_the_horizon(fold) -> None:
    # Given / When
    train, _ = split(ROWS, fold, embargo_hours=HORIZON)
    # Then
    assert fold.boundary - train["hour_end_utc"].max() == HORIZON * HOUR


def test_a_gap_shorter_than_the_horizon_stops_the_run() -> None:
    with pytest.raises(EmbargoError, match="target hour"):
        split(ROWS, TEST, embargo_hours=HORIZON // 2)


def test_check_embargo_rejects_a_table_with_a_late_target() -> None:
    # Given: rows up to one target hour past the test start
    late = ROWS[ROWS["target_hour_end_utc"] <= CONFIG.test_start + HOUR]
    # When / Then
    with pytest.raises(EmbargoError):
        check_embargo(late, CONFIG.test_start)


def test_validation_scores_only_target_hours_between_its_start_and_the_test_start() -> None:
    # Given / When
    _, evaluate = split(ROWS, VALIDATION, embargo_hours=HORIZON)
    targets = evaluate["target_hour_end_utc"]
    # Then
    assert (targets.min(), targets.max()) == (CONFIG.validation_start + HOUR, CONFIG.test_start)


def test_test_rows_start_with_the_first_hour_of_the_test_year() -> None:
    # Given / When
    _, evaluate = split(ROWS, TEST, embargo_hours=HORIZON)
    # Then
    assert evaluate["target_hour_end_utc"].min() == CONFIG.test_start + HOUR


def test_the_test_fold_scores_only_the_test_year_even_when_newer_data_exists() -> None:
    # Given: feature rows running into 2026 (newer data, used only by the live model)
    rows = feature_rows("2025-12-20 00:30", "2026-01-10 00:30")
    # When
    _, evaluate = split(rows, TEST, embargo_hours=HORIZON)
    # Then: no 2026 target hour is scored, so the published 2025 numbers stay comparable
    assert evaluate["target_hour_end_utc"].max() == CONFIG.test_end
