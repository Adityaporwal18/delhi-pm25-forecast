"""Tests for reading the [model] settings in config/pipeline.toml (src/delhi_pm25/model_settings.py)."""

from pathlib import Path

import pytest

from delhi_pm25.config import ConfigError
from delhi_pm25.model_settings import load_model_settings, load_serving_settings
from delhi_pm25.paths import PIPELINE_TOML


def test_project_settings_compare_blh_and_stubble_with_an_l1_model() -> None:
    settings = load_model_settings(PIPELINE_TOML)
    assert (settings.objective, sorted(settings.ablations), settings.min_gain_pct) == (
        "l1", ["no_blh", "no_doy", "no_stubble"], 1.0,
    )


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('objective = "l1"', 'objective = "quantile"', "objective"),
        ("max_trees = 5000", "max_trees = 0", "max_trees"),
        ('no_stubble = ["target_in_stubble_season"]', "no_stubble = []", "no_stubble"),
        ("min_gain_pct = 1.0", "min_gain_pct = -1.0", "min_gain_pct"),
    ],
)
def test_invalid_model_settings_are_rejected_with_a_clear_message(
    tmp_path: Path, old: str, new: str, message: str,
) -> None:
    # Given: the project config with one model setting broken
    text = PIPELINE_TOML.read_text(encoding="utf-8")
    broken = tmp_path / "pipeline.toml"
    broken.write_text(text.replace(old, new), encoding="utf-8")
    # When / Then
    with pytest.raises(ConfigError, match=message):
        load_model_settings(broken)


def test_serving_settings_give_horizons_a_band_and_replay_hours() -> None:
    serving = load_serving_settings(PIPELINE_TOML)
    assert (serving.horizons_hours[-1], serving.band_quantiles, serving.replay_issue_hours_ist) == (48, (0.1, 0.9), (8, 20))


def test_a_band_must_straddle_the_median(tmp_path: Path) -> None:
    # Given: a band whose low end is above the median
    broken = tmp_path / "pipeline.toml"
    broken.write_text(PIPELINE_TOML.read_text(encoding="utf-8").replace("band_quantiles = [0.1, 0.9]", "band_quantiles = [0.6, 0.9]"), encoding="utf-8")
    # When / Then
    with pytest.raises(ConfigError, match="band_quantiles"):
        load_serving_settings(broken)
