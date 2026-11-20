"""Tests for the stage 5 model wrapper (src/delhi_pm25/model.py)."""

import numpy as np
import pandas as pd
import pytest

from delhi_pm25.model import (
    FixedTrees,
    ModelError,
    Recipe,
    StopEarly,
    feature_columns,
    fit,
    importance,
    predict,
    worth_keeping,
)


def rows_where_target_is_2x_plus_10(n: int, seed: int) -> pd.DataFrame:
    """Feature rows in the pipeline's layout. `noise` carries no information about the target."""
    rng = np.random.default_rng(seed)
    hours = pd.Series(pd.date_range("2024-01-01 00:30", periods=n, freq="h", tz="UTC"))
    rows = pd.DataFrame({
        "slug": pd.Categorical(rng.choice(["a", "b"], n), categories=["a", "b"]),
        "hour_end_utc": hours,
        "x": rng.uniform(0, 100, n).astype("float32"),
        "noise": rng.normal(size=n).astype("float32"),
    })
    rows["target_hour_end_utc"] = hours + pd.Timedelta(hours=48)
    rows["target"] = 2 * rows["x"] + 10
    return rows


TRAIN = rows_where_target_is_2x_plus_10(2000, seed=1)
FRESH = rows_where_target_is_2x_plus_10(500, seed=2)
RECIPE = Recipe(columns=("slug", "x", "noise"), objective="l1")


def test_feature_columns_are_everything_but_the_time_stamps_and_the_target() -> None:
    assert feature_columns(TRAIN, dropped=()) == ("slug", "x", "noise")


def test_a_dropped_group_leaves_the_feature_list() -> None:
    assert feature_columns(TRAIN, dropped=("x",)) == ("slug", "noise")


def test_dropping_a_feature_that_does_not_exist_is_an_error() -> None:
    with pytest.raises(ModelError, match="wx_blh"):
        feature_columns(TRAIN, dropped=("wx_blh",))


def test_model_learns_from_the_rows_whose_target_was_measured() -> None:
    # Given: a third of the training targets are blank
    train = TRAIN.assign(target=TRAIN["target"].mask(TRAIN.index % 3 == 0))
    # When
    model = fit(train, RECIPE, FixedTrees(trees=200))
    # Then: forecasts for fresh rows are close (targets run from 10 to 210)
    assert (predict(model, FRESH) - FRESH["target"]).abs().mean() < 5.0


def test_forecasts_are_never_below_zero() -> None:
    # Given: a relation that would push every forecast below zero
    model = fit(TRAIN.assign(target=TRAIN["x"] - 1000), RECIPE, FixedTrees(trees=20))
    # When / Then
    assert (predict(model, FRESH) == 0.0).all()


def test_early_stopping_stops_once_the_validation_rows_stop_improving() -> None:
    # Given: validation targets that are pure noise, so more trees cannot help them
    noisy = FRESH.assign(target=np.random.default_rng(3).uniform(10, 210, len(FRESH)))
    # When
    model = fit(TRAIN, RECIPE, StopEarly(validation=noisy, max_trees=500, patience=10))
    # Then
    assert model.trees < 500


def test_importance_puts_the_informative_feature_first() -> None:
    table = importance(fit(TRAIN, RECIPE, FixedTrees(trees=50)))
    assert (table["feature"].iloc[0], round(table["gain_pct"].sum())) == ("x", 100)


def score_table(all_hours: float, smoggiest_10: float, smoggiest_1: float = 300.0) -> pd.DataFrame:
    """The part of baselines.score's output that the keep rule reads."""
    return pd.DataFrame({
        "hours": ["all hours", "smoggiest 10.0%", "smoggiest 1.0%"],
        "model_mae": [all_hours, smoggiest_10, smoggiest_1],
    })


@pytest.mark.parametrize(
    ("without", "kept"),
    [
        pytest.param(score_table(40.2, 100.5), False, id="0.5% worse: drop"),
        pytest.param(score_table(40.5, 100.0), True, id="1.25% worse on all hours: keep"),
        pytest.param(score_table(40.0, 101.0), True, id="1% worse on the smoggiest 10%: keep"),
        pytest.param(score_table(40.0, 100.0, 400.0), False, id="worse only on the smoggiest 1%: drop"),
    ],
)
def test_keep_rule_needs_a_gain_on_all_hours_or_the_smoggiest_tenth(without: pd.DataFrame, kept: bool) -> None:
    assert worth_keeping(score_table(40.0, 100.0), without, min_gain_pct=1.0) is kept
