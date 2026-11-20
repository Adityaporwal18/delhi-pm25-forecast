"""Stage 4: score the two baselines on the validation year (2024) and the test year (2025).

Folds ([split] in config/pipeline.toml): validation trains on 2023 and scores target hours in
2024; test trains on 2023-2024 and scores 2025. Training rows are forecasts made at least 48
hours before the boundary, so no training target lies past it (src/delhi_pm25/split.py stops
with an error otherwise).

Baselines:
  persistence  PM2.5 in 48 hours = PM2.5 now
  climatology  average at the same station and Delhi clock hour, on days within N either side
               of the same calendar day, training years only ([baselines])

Both are scored on the same rows: target measured AND both forecasts available. The stage 5
model is scored on these rows too.

Outputs:
  reports/stage4/baselines.csv   MAE per fold: all hours, smoggiest 10% and 1% of hours
  reports/stage4/split.csv       what each fold trains on and scores

Usage:
  .venv/bin/python scripts/07_baselines.py
"""

import sys
from typing import Final

import pandas as pd

from delhi_pm25.baselines import climatology, climatology_table, score
from delhi_pm25.clean import HOUR
from delhi_pm25.config import ConfigError, load_config
from delhi_pm25.guards import InputsOutOfDate, check_up_to_date
from delhi_pm25.paths import INTERIM_DIR, PIPELINE_TOML, PROCESSED_DIR, REPORTS_DIR
from delhi_pm25.split import EmbargoError, Fold, folds, split

FEATURES_PARQUET: Final = PROCESSED_DIR / "features.parquet"
OUT: Final = REPORTS_DIR / "stage4"
FEATURES_COMMAND: Final = ".venv/bin/python scripts/06_features.py"
COLUMNS: Final = ["slug", "hour_end_utc", "target_hour_end_utc", "target"]


def describe(fold: Fold, train: pd.DataFrame, evaluate: pd.DataFrame) -> dict[str, object]:
    """One line of reports/stage4/split.csv: what this fold trains on and what it scores."""
    targets = train["target_hour_end_utc"]
    scored = evaluate["target_hour_end_utc"]
    return {
        "fold": fold.name,
        "train_rows": len(train),
        "train_targets_measured": int(train["target"].notna().sum()),
        "train_target_hours_utc": f"{targets.min()} -> {targets.max()}",
        "last_training_forecast_utc": train["hour_end_utc"].max(),
        "gap_hours": int((fold.boundary - train["hour_end_utc"].max()) / HOUR),
        "evaluate_rows": len(evaluate),
        "evaluate_targets_measured": int(evaluate["target"].notna().sum()),
        "evaluate_target_hours_utc": f"{scored.min()} -> {scored.max()}",
    }


def main() -> int:
    try:
        config = load_config(PIPELINE_TOML)
        check_up_to_date(FEATURES_PARQUET, [INTERIM_DIR / "hourly_clean.parquet", PIPELINE_TOML], FEATURES_COMMAND)
        now = f"{config.target}_lag_0h"
        features = pd.read_parquet(FEATURES_PARQUET, columns=[*COLUMNS, now])
        scores, splits = [], []
        for fold in folds(config):
            train, evaluate = split(features, fold, config.features.horizon_hours)
            table = climatology_table(train, config.baselines)
            forecasts = {"persistence": evaluate[now], "climatology": climatology(evaluate, table)}
            scores.append(score(evaluate, forecasts).assign(fold=fold.name))
            splits.append(describe(fold, train, evaluate))
    except (ConfigError, InputsOutOfDate, EmbargoError) as err:
        print(f"STOPPED: {err}", file=sys.stderr)
        return 1
    baselines = pd.concat(scores, ignore_index=True)
    baselines = baselines[["fold", *baselines.columns.drop("fold")]]
    OUT.mkdir(parents=True, exist_ok=True)
    baselines.to_csv(OUT / "baselines.csv", index=False)
    pd.DataFrame(splits).to_csv(OUT / "split.csv", index=False)
    print(pd.DataFrame(splits).T.to_string(header=False))
    print(f"\nMAE of {config.target} {config.features.horizon_hours} h ahead (ug/m3), same rows for both:")
    print(baselines.to_string(index=False))
    print(f"\nWrote {OUT.relative_to(OUT.parents[1])}/baselines.csv and split.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
