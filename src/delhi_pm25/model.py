"""Stage 5: the forecasting model, gradient-boosted decision trees (LightGBM).

In plain words: the model grows small decision trees one after another, and each new tree
corrects the errors that the trees before it still make. It learns only from training rows
whose target was measured, uses every feature column, and handles blank features itself
(nothing is filled in). Settings live in [model] in config/pipeline.toml.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, assert_never

import lightgbm as lgb
import numpy as np
import pandas as pd

from delhi_pm25.features import NON_FEATURE_COLUMNS
from delhi_pm25.model_settings import Objective

SEED: Final = 0
GAIN_TAILS: Final = ["all hours", "smoggiest 10.0%"]


class ModelError(Exception):
    """A model request that cannot be right, e.g. removing a feature that does not exist."""


@dataclass(frozen=True, slots=True)
class Recipe:
    columns: tuple[str, ...]
    objective: Objective


@dataclass(frozen=True, slots=True)
class StopEarly:
    """Grow trees until `patience` more trees no longer improve the score on `validation`."""

    validation: pd.DataFrame
    max_trees: int
    patience: int


@dataclass(frozen=True, slots=True)
class FixedTrees:
    trees: int


@dataclass(frozen=True, slots=True)
class FittedModel:
    booster: lgb.Booster
    recipe: Recipe
    trees: int


def feature_columns(features: pd.DataFrame, dropped: Sequence[str]) -> tuple[str, ...]:
    """Every feature column of the stage 3 table, minus `dropped`."""
    columns = [name for name in features.columns if name not in NON_FEATURE_COLUMNS]
    unknown = sorted(set(dropped) - set(columns))
    if unknown:
        raise ModelError(f"cannot remove {unknown}: not feature columns (check [model.ablations] in config/pipeline.toml)")
    return tuple(name for name in columns if name not in dropped)


def _dataset(rows: pd.DataFrame, recipe: Recipe, reference: lgb.Dataset | None = None) -> lgb.Dataset:
    measured = rows[rows["target"].notna()]
    return lgb.Dataset(measured[list(recipe.columns)], label=measured["target"], reference=reference)


def fit(train: pd.DataFrame, recipe: Recipe, stopping: StopEarly | FixedTrees) -> FittedModel:
    """Train on the rows of `train` whose target was measured. LightGBM defaults otherwise;
    `deterministic` and a fixed seed make every run give the same model."""
    params = {"objective": recipe.objective, "seed": SEED, "deterministic": True,
              "force_row_wise": True, "verbosity": -1}
    train_set = _dataset(train, recipe)
    match stopping:
        case StopEarly(validation=validation, max_trees=max_trees, patience=patience):
            booster = lgb.train(
                params, train_set, num_boost_round=max_trees,
                valid_sets=[_dataset(validation, recipe, reference=train_set)],
                callbacks=[lgb.early_stopping(patience, verbose=False)],
            )
            trees = booster.best_iteration
        case FixedTrees(trees=trees):
            booster = lgb.train(params, train_set, num_boost_round=trees)
        case unreachable:
            assert_never(unreachable)
    return FittedModel(booster, recipe, trees)


def predict(model: FittedModel, rows: pd.DataFrame) -> pd.Series:
    """A forecast for every row, blank features included; never below zero (PM2.5 cannot be)."""
    values = model.booster.predict(rows[list(model.recipe.columns)], num_iteration=model.trees)
    return pd.Series(np.clip(values, 0.0, None), index=rows.index, name="model")


def importance(model: FittedModel) -> pd.DataFrame:
    """Share of the model's total error reduction ('gain') that each feature provides."""
    gain = model.booster.feature_importance("gain", iteration=model.trees)
    splits = model.booster.feature_importance("split", iteration=model.trees)
    table = pd.DataFrame({"feature": model.recipe.columns, "gain_pct": 100 * gain / gain.sum(), "splits": splits})
    return table.sort_values("gain_pct", ascending=False, ignore_index=True).round({"gain_pct": 2})


def worth_keeping(full: pd.DataFrame, without: pd.DataFrame, min_gain_pct: float) -> bool:
    """The keep rule: a feature group stays if removing it makes model MAE worse by at least
    `min_gain_pct` % on all hours or on the smoggiest 10% (score tables from baselines.score)."""
    before = full.set_index("hours").loc[GAIN_TAILS, "model_mae"]
    after = without.set_index("hours").loc[GAIN_TAILS, "model_mae"]
    return bool(((after - before) / before * 100 >= min_gain_pct).any())
