"""Tests for the evaluation/live model specs (src/delhi_pm25/model_spec.py)."""

import dataclasses

import pytest

from delhi_pm25.model_spec import (
    ModelSpec,
    SpecMismatch,
    TrainingWindow,
    assert_same_except_window,
    spec_from_json,
    spec_to_json,
)
from delhi_pm25.paths import REPORTS_DIR

EVALUATION = ModelSpec(
    window=TrainingWindow(first_target_utc="2023-01-01T01:30:00+00:00", last_target_utc="2024-12-31T18:30:00+00:00"),
    target="pm25",
    columns=("slug", "pm25_lag_0h", "city_pm25_median"),
    objective="l1",
    band_quantiles=(0.1, 0.9),
    horizons_hours=(6, 48),
    trees={"h06_p50": 215, "h06_p10": 77, "h06_p90": 90, "h48_p50": 51, "h48_p10": 43, "h48_p90": 45},
    lightgbm={"seed": 0, "deterministic": True, "force_row_wise": True, "verbosity": -1},
)
LIVE_WINDOW = TrainingWindow(first_target_utc="2023-01-01T01:30:00+00:00", last_target_utc="2026-11-16T18:30:00+00:00")


def test_specs_that_differ_only_in_the_training_window_pass() -> None:
    assert_same_except_window(EVALUATION, dataclasses.replace(EVALUATION, window=LIVE_WINDOW))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("columns", ("slug", "pm25_lag_0h")),
        ("objective", "l2"),
        ("band_quantiles", (0.05, 0.95)),
        ("horizons_hours", (48,)),
        ("trees", {**EVALUATION.trees, "h48_p50": 60}),
        ("lightgbm", {**EVALUATION.lightgbm, "seed": 1}),
    ],
)
def test_any_other_difference_is_caught_and_named(field: str, value: object) -> None:
    # Given: live models changed in one respect besides the window
    live = dataclasses.replace(EVALUATION, window=LIVE_WINDOW, **{field: value})
    # When / Then: the published accuracy would no longer describe them, so this must stop
    with pytest.raises(SpecMismatch, match=field):
        assert_same_except_window(EVALUATION, live)


def test_a_spec_survives_the_trip_through_json() -> None:
    assert spec_from_json(spec_to_json(EVALUATION)) == EVALUATION


def test_the_committed_live_spec_matches_the_evaluation_spec_except_for_the_window() -> None:
    # Given: the specs written by scripts/10_horizon_models.py and scripts/11_live_models.py
    evaluation = spec_from_json((REPORTS_DIR / "stage7" / "model_spec_evaluation.json").read_text())
    live = spec_from_json((REPORTS_DIR / "live" / "model_spec_live.json").read_text())
    # When / Then
    assert_same_except_window(evaluation, live)
