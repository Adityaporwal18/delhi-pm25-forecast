"""Tests for the time-series checks used in the Stage 2 inspection (src/delhi_aqi/series_checks.py)."""

import numpy as np
import pandas as pd

from delhi_aqi.series_checks import flat_mask, flat_runs, gap_lengths, isolated_spikes


def test_gap_lengths_counts_each_run_of_missing_hours() -> None:
    present = pd.Series([True, False, False, True, False, True, True, False])
    assert gap_lengths(present).tolist() == [2, 1, 1]


def test_flat_runs_reports_only_long_runs_of_identical_readings() -> None:
    values = pd.Series([5.0, 5.0, 5.0, 7.0, 7.0, 8.0])
    assert flat_runs(values, min_hours=3).tolist() == [3]


def test_flat_runs_ignores_runs_of_missing_values() -> None:
    values = pd.Series([1.0, np.nan, np.nan, np.nan, 2.0])
    assert flat_runs(values, min_hours=3).tolist() == []


def test_flat_mask_marks_every_hour_of_a_long_frozen_run() -> None:
    values = pd.Series([5.0, 5.0, 5.0, 7.0, 7.0, 8.0])
    assert flat_mask(values, min_hours=3).tolist() == [True, True, True, False, False, False]


def test_flat_mask_never_marks_missing_values() -> None:
    values = pd.Series([np.nan, np.nan, np.nan])
    assert flat_mask(values, min_hours=3).tolist() == [False, False, False]


def test_isolated_spike_jumps_up_and_straight_back_down() -> None:
    values = pd.Series([100.0, 400.0, 110.0])
    assert isolated_spikes(values, jump=200.0).tolist() == [False, True, False]


def test_sustained_rise_is_not_an_isolated_spike() -> None:
    values = pd.Series([100.0, 400.0, 380.0])
    assert isolated_spikes(values, jump=200.0).tolist() == [False, False, False]
