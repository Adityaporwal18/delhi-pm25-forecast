"""Stage 5: train the model, compare it with the two baselines, and test BLH and the stubble flag.

The order was fixed before any model was trained ([model] in config/pipeline.toml):
1. Validation fold (train on 2023, score 2024): the model with every feature. Training stops
   once 100 more trees no longer improve the 2024 score; that tree count is kept.
2. Same fold, the same number of trees, without each group in [model.ablations], so only the
   features differ. A group stays only if
   removing it makes the validation MAE worse by at least min_gain_pct % (all hours or the
   smoggiest 10% of hours).
3. Test fold: the final model trains on 2023-2024 with the kept features and the tree count
   from steps 1-2, and is scored ONCE on 2025.
Forecasts are scored on the same rows as the baselines. The model is also scored on every
measured row, including rows where 'PM2.5 now' is blank and persistence has no forecast.

Outputs:
  reports/stage5/scores.csv       MAE of persistence, climatology and the model, per fold
  reports/stage5/ablation.csv     validation MAE with and without each feature group
  reports/stage5/importance.csv   how much each feature contributes to the final model
  data/models/pm25_48h.txt        the final model (LightGBM text format)

Usage:
  .venv/bin/python scripts/08_model.py
"""

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import pandas as pd

from delhi_pm25.baselines import climatology, climatology_table, score
from delhi_pm25.config import ConfigError, PipelineConfig, load_config
from delhi_pm25.feature_notes import feature_notes
from delhi_pm25.guards import InputsOutOfDate, check_up_to_date
from delhi_pm25.model import (
    FittedModel,
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
from delhi_pm25.model_settings import ModelSettings, load_model_settings
from delhi_pm25.paths import INTERIM_DIR, MODELS_DIR, PIPELINE_TOML, PROCESSED_DIR, REPORTS_DIR
from delhi_pm25.split import EmbargoError, Fold, folds, split

FEATURES_PARQUET: Final = PROCESSED_DIR / "features.parquet"
MODEL_FILE: Final = MODELS_DIR / "pm25_48h.txt"
OUT: Final = REPORTS_DIR / "stage5"
FEATURES_COMMAND: Final = ".venv/bin/python scripts/06_features.py"
SAME_ROWS: Final = "same rows as baselines"
TAILS: Final = {"all hours": "all_hours", "smoggiest 10.0%": "smoggiest_10pct", "smoggiest 1.0%": "smoggiest_1pct"}


@dataclass(frozen=True, slots=True)
class FoldData:
    """One fold: its training rows, the rows it scores, and the baseline forecasts for them."""

    train: pd.DataFrame
    evaluate: pd.DataFrame
    baselines: Mapping[str, pd.Series]


@dataclass(frozen=True, slots=True)
class Choice:
    """What the validation fold decided: the final model's features and tree count."""

    columns: tuple[str, ...]
    trees: int
    ablation: pd.DataFrame
    validation_scores: pd.DataFrame


def load_inputs() -> tuple[PipelineConfig, ModelSettings, pd.DataFrame]:
    config, settings = load_config(PIPELINE_TOML), load_model_settings(PIPELINE_TOML)
    check_up_to_date(FEATURES_PARQUET, [INTERIM_DIR / "hourly_clean.parquet", PIPELINE_TOML], FEATURES_COMMAND)
    return config, settings, pd.read_parquet(FEATURES_PARQUET)


def prepare(features: pd.DataFrame, fold: Fold, config: PipelineConfig) -> FoldData:
    train, evaluate = split(features, fold, config.features.horizon_hours)
    table = climatology_table(train, config.baselines)
    baselines = {"persistence": evaluate[f"{config.target}_lag_0h"], "climatology": climatology(evaluate, table)}
    return FoldData(train, evaluate, baselines)


def scores(data: FoldData, model: FittedModel) -> pd.DataFrame:
    """MAE on the rows the baselines also cover, then the model alone on every measured row."""
    forecast = predict(model, data.evaluate)
    same = score(data.evaluate, {**data.baselines, "model": forecast}).assign(rows=SAME_ROWS)
    every = score(data.evaluate, {"model": forecast}).assign(rows="all measured rows")
    return pd.concat([same, every], ignore_index=True)


def same_rows(table: pd.DataFrame) -> pd.DataFrame:
    return table[table["rows"] == SAME_ROWS]


def ablation_line(variant: str, model: FittedModel, table: pd.DataFrame) -> dict[str, object]:
    mae = same_rows(table).set_index("hours")["model_mae"]
    line: dict[str, object] = {"variant": variant, "features": len(model.recipe.columns), "trees": model.trees}
    return line | {f"mae_{name}": mae[tail] for tail, name in TAILS.items()}


def with_changes(lines: list[dict[str, object]]) -> pd.DataFrame:
    """Each variant's MAE change against the first line (all features), in percent."""
    table = pd.DataFrame(lines)
    for name in ("all_hours", "smoggiest_10pct"):
        base = table[f"mae_{name}"].iloc[0]
        table[f"worse_{name}_pct"] = ((table[f"mae_{name}"] - base) / base * 100).round(2)
    return table


def choose(features: pd.DataFrame, data: FoldData, settings: ModelSettings) -> Choice:
    """Steps 1-2: the full model, each ablation, the keep rule, then the final feature set."""
    early = StopEarly(data.evaluate, settings.max_trees, settings.early_stopping_rounds)
    full = fit(data.train, Recipe(feature_columns(features, ()), settings.objective), early)
    full_scores = scores(data, full)
    same_size = FixedTrees(full.trees)
    lines = [ablation_line("all features", full, full_scores) | {"decision": ""}]
    dropped: list[str] = []
    for name, group in settings.ablations.items():
        variant = fit(data.train, Recipe(feature_columns(features, group), settings.objective), same_size)
        variant_scores = scores(data, variant)
        keep = worth_keeping(same_rows(full_scores), same_rows(variant_scores), settings.min_gain_pct)
        lines.append(ablation_line(name, variant, variant_scores) | {"decision": "keep" if keep else "drop"})
        dropped.extend(() if keep else group)
    if not dropped:
        return Choice(full.recipe.columns, full.trees, with_changes(lines), full_scores)
    final = fit(data.train, Recipe(feature_columns(features, dropped), settings.objective), early)
    final_scores = scores(data, final)
    lines.append(ablation_line("final feature set", final, final_scores) | {"decision": ""})
    return Choice(final.recipe.columns, final.trees, with_changes(lines), final_scores)


def print_summary(table: pd.DataFrame, choice: Choice, weights: pd.DataFrame) -> None:
    view = ["fold", "rows", "hours", "n_rows", "persistence_mae", "climatology_mae", "model_mae"]
    print("MAE of PM2.5 48 h ahead (ug/m3):")
    print(table[view].to_string(index=False))
    print("\nValidation comparisons (train 2023, score 2024; same rows as the baselines):")
    print(choice.ablation.to_string(index=False))
    print(f"\nFinal model: {len(choice.columns)} features, {choice.trees} trees. Top features by gain:")
    print(weights.head(12).to_string(index=False))


def main() -> int:
    try:
        config, settings, features = load_inputs()
        validation, test = folds(config)
        choice = choose(features, prepare(features, validation, config), settings)
        data = prepare(features, test, config)
        final = fit(data.train, Recipe(choice.columns, settings.objective), FixedTrees(choice.trees))
        test_scores = scores(data, final)
    except (ConfigError, InputsOutOfDate, EmbargoError, ModelError) as err:
        print(f"STOPPED: {err}", file=sys.stderr)
        return 1
    table = pd.concat([choice.validation_scores.assign(fold="validation"), test_scores.assign(fold="test")])
    table = table[["fold", "rows", *table.columns.drop(["fold", "rows"])]]
    notes = feature_notes(list(final.recipe.columns), config.target)[["feature", "group"]]
    weights = importance(final).merge(notes, on="feature")
    OUT.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "scores.csv", index=False)
    choice.ablation.to_csv(OUT / "ablation.csv", index=False)
    weights.to_csv(OUT / "importance.csv", index=False)
    final.booster.save_model(MODEL_FILE, num_iteration=final.trees)
    print_summary(table, choice, weights)
    print(f"\nWrote reports/stage5/ (scores, ablation, importance) and {MODEL_FILE.relative_to(MODELS_DIR.parents[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
