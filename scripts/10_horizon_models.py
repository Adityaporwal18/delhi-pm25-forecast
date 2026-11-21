"""Stage 7, step 1: forecasts every 6 hours up to 48 hours ahead, with an uncertainty band.

For each horizon in [serving] (config/pipeline.toml), three direct models on the stage 5
feature set: the median (the "l1" recipe of the 48-hour model) and the 10th and 90th
percentiles (quantile models), which bound an 80% band. As in stage 5, each model's number of
trees is chosen on the validation year (train 2023, score 2024) and the final models train on
2023-2024. Every training row is a forecast made at least 48 hours before its fold boundary,
whatever the horizon. The test year 2025 then checks each horizon: MAE against the baselines,
and how often the measured value falls inside the band (it should be about 80%).

Outputs:
  data/models/h{HH}_{p10,p50,p90}.txt   the models
  reports/stage7/horizons.csv           per horizon: trees, MAE vs baselines, band coverage
  serving/replay_2025.parquet      forecasts issued at the replay hours on every day of
                                        2025, next to what was measured (served by the API)

Usage:
  .venv/bin/python scripts/10_horizon_models.py
"""

import sys
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from delhi_pm25.baselines import climatology, climatology_table, score
from delhi_pm25.clean import HOUR
from delhi_pm25.config import ConfigError, PipelineConfig, load_config
from delhi_pm25.error_analysis import outcome_tail
from delhi_pm25.features import DELHI, FeatureError, horizon_view
from delhi_pm25.guards import InputsOutOfDate, check_up_to_date
from delhi_pm25.model import FixedTrees, Quantile, Recipe, StopEarly, fit, load_model, predict
from delhi_pm25.model_settings import ModelSettings, ServingSettings, load_model_settings, load_serving_settings
from delhi_pm25.paths import MODELS_DIR, PIPELINE_TOML, PROCESSED_DIR, REPORTS_DIR, SERVING_DIR
from delhi_pm25.split import EmbargoError, folds, split

FEATURES_PARQUET: Final = PROCESSED_DIR / "features.parquet"
MODEL_48H: Final = MODELS_DIR / "pm25_48h.txt"
REPLAY: Final = SERVING_DIR / "replay_2025.parquet"
OUT: Final = REPORTS_DIR / "stage7"
MODEL_COMMAND: Final = ".venv/bin/python scripts/08_model.py"


@dataclass(frozen=True, slots=True)
class Plan:
    """Everything the per-horizon steps need: settings, the feature set and the last replay hour."""

    config: PipelineConfig
    model: ModelSettings
    serving: ServingSettings
    columns: tuple[str, ...]
    last_issue: pd.Timestamp


def band_models(view: pd.DataFrame, plan: Plan, hours: int) -> tuple[pd.DataFrame, dict[str, int]]:
    """Fit the median and band models for one horizon; return the test rows with forecasts."""
    validation, test = folds(plan.config)
    gap = plan.config.features.horizon_hours
    val_train, val_rows = split(view, validation, gap)
    train, rows = split(view, test, gap)
    low, high = plan.serving.band_quantiles
    trees: dict[str, int] = {}
    for name, objective in {"p50": plan.model.objective, "p10": Quantile(low), "p90": Quantile(high)}.items():
        recipe = Recipe(plan.columns, objective)
        stop = StopEarly(val_rows, plan.model.max_trees, plan.model.early_stopping_rounds)
        final = fit(train, recipe, FixedTrees(fit(val_train, recipe, stop).trees))
        final.booster.save_model(MODELS_DIR / f"h{hours:02d}_{name}.txt", num_iteration=final.trees)
        rows[name] = predict(final, rows)
        trees[f"trees_{name}"] = final.trees
    rows["p10"] = np.minimum(rows["p10"], rows["p50"])
    rows["p90"] = np.maximum(rows["p90"], rows["p50"])
    rows["climatology"] = climatology(rows, climatology_table(train, plan.config.baselines))
    return rows, trees


def check_horizon(rows: pd.DataFrame, plan: Plan, hours: int) -> dict[str, object]:
    """Test-year MAE against the baselines (same rows) and how often the band holds the truth."""
    forecasts = {"persistence": rows[f"{plan.config.target}_lag_0h"], "climatology": rows["climatology"],
                 "model": rows["p50"]}
    mae = score(rows, forecasts).set_index("hours").loc["all hours"]
    target, measured = rows["target"], rows["target"].notna()
    inside = (target >= rows["p10"]) & (target <= rows["p90"])
    smog = outcome_tail(rows, 0.10) & measured
    return {
        "horizon_h": hours, "persistence_mae": mae["persistence_mae"],
        "climatology_mae": mae["climatology_mae"], "model_mae": mae["model_mae"],
        "inside_band_pct": round(inside[measured].mean() * 100, 1),
        "below_p10_pct": round((target < rows["p10"])[measured].mean() * 100, 1),
        "above_p90_pct": round((target > rows["p90"])[measured].mean() * 100, 1),
        "inside_band_smoggiest_10pct": round(inside[smog].mean() * 100, 1),
    }


def replay_rows(rows: pd.DataFrame, plan: Plan, hours: int) -> pd.DataFrame:
    """Forecasts issued at the replay hours in 2025, with the value measured at the target hour."""
    issued = rows["hour_end_utc"]
    keep = (issued.dt.tz_convert(DELHI).dt.hour.isin(plan.serving.replay_issue_hours_ist)
            & (issued > plan.config.test_start) & (issued <= plan.last_issue))
    picked = rows[keep]
    return pd.DataFrame({
        "slug": picked["slug"].astype(str), "issued_utc": picked["hour_end_utc"], "horizon_h": hours,
        "p10": picked["p10"], "p50": picked["p50"], "p90": picked["p90"], "measured": picked["target"],
    }).astype({"p10": "float32", "p50": "float32", "p90": "float32", "measured": "float32"})


def main() -> int:
    try:
        config = load_config(PIPELINE_TOML)
        check_up_to_date(MODEL_48H, [FEATURES_PARQUET, PIPELINE_TOML], MODEL_COMMAND)
        model, serving = load_model_settings(PIPELINE_TOML), load_serving_settings(PIPELINE_TOML)
        features = pd.read_parquet(FEATURES_PARQUET)
        columns = load_model(MODEL_48H, model.objective).recipe.columns
        plan = Plan(config, model, serving, columns, features["hour_end_utc"].max() - 48 * HOUR)
        now = features.assign(p10=np.nan, p50=np.nan, p90=np.nan, target=features[f"{config.target}_lag_0h"])
        checks, replay = [], [replay_rows(now, plan, 0)]
        for hours in serving.horizons_hours:
            rows, trees = band_models(horizon_view(features, hours, config), plan, hours)
            checks.append(check_horizon(rows, plan, hours) | trees)
            replay.append(replay_rows(rows, plan, hours))
            print(f"horizon {hours:2d} h: {trees}", flush=True)
    except (ConfigError, InputsOutOfDate, EmbargoError, FeatureError) as err:
        print(f"STOPPED: {err}", file=sys.stderr)
        return 1
    table = pd.DataFrame(checks)
    OUT.mkdir(parents=True, exist_ok=True)
    SERVING_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "horizons.csv", index=False)
    replayed = pd.concat(replay, ignore_index=True).sort_values(["issued_utc", "slug", "horizon_h"], ignore_index=True)
    replayed.to_parquet(REPLAY, index=False)
    pd.set_option("display.width", 220)
    print("\nTest year 2025, per horizon (MAE ug/m3; band = 10th to 90th percentile forecasts):")
    print(table.to_string(index=False))
    print(f"\nReplay: {replayed['issued_utc'].nunique()} issue times x {replayed['slug'].nunique()} stations "
          f"-> {REPLAY.relative_to(SERVING_DIR.parents[1])} ({len(replayed):,} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
