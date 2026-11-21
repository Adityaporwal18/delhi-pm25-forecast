"""Live forecasts, stage B: train the LIVE models, identical to the evaluation models except for
the training window.

The evaluation models (scripts/10_horizon_models.py) learn from 2023-2024 and are scored on
2025; every published accuracy number comes from them. The live models learn from everything up
to the latest reading, so they have no held-out year and no accuracy number of their own: the
site quotes the evaluation numbers, labelled "based on held-out 2025 testing". For each horizon
and band this script trains the same recipe with the same number of trees as the evaluation spec
records, on every forecast whose target lies inside the data, with the same 48-hour gap rule
(the end of the data is the boundary). It stops before training if the settings have drifted
from the evaluation spec, and again before saving if the specs differ in anything but the window.

Outputs:
  data/models/live/h{HH}_{p10,p50,p90}.txt   the live models
  reports/live/model_spec_live.json          their spec (tests/test_model_spec.py compares it)

Usage:
  .venv/bin/python scripts/11_live_models.py
"""

import sys
from typing import Final

import pandas as pd

from delhi_pm25.config import ConfigError, load_config
from delhi_pm25.features import FeatureError, horizon_view
from delhi_pm25.guards import InputsOutOfDate, check_up_to_date
from delhi_pm25.model import FittedModel, FixedTrees, Recipe, band_objectives, fit
from delhi_pm25.model_settings import load_model_settings, load_serving_settings
from delhi_pm25.model_spec import (
    ModelSpec,
    SpecMismatch,
    SpecParts,
    assert_same_except_window,
    build_spec,
    spec_from_json,
    spec_to_json,
    window_of,
)
from delhi_pm25.paths import MODELS_DIR, PIPELINE_TOML, PROCESSED_DIR, REPORTS_DIR
from delhi_pm25.split import EmbargoError, Fold, split

FEATURES_PARQUET: Final = PROCESSED_DIR / "features.parquet"
EVALUATION_SPEC: Final = REPORTS_DIR / "stage7" / "model_spec_evaluation.json"
LIVE_MODELS: Final = MODELS_DIR / "live"
OUT: Final = REPORTS_DIR / "live"
EVALUATION_COMMAND: Final = ".venv/bin/python scripts/10_horizon_models.py"


def train_live() -> tuple[dict[str, FittedModel], ModelSpec]:
    config = load_config(PIPELINE_TOML)
    model, serving = load_model_settings(PIPELINE_TOML), load_serving_settings(PIPELINE_TOML)
    check_up_to_date(EVALUATION_SPEC, [FEATURES_PARQUET, PIPELINE_TOML], EVALUATION_COMMAND)
    evaluation = spec_from_json(EVALUATION_SPEC.read_text())
    parts = SpecParts(config, model, serving, evaluation.columns)
    assert_same_except_window(evaluation, build_spec(evaluation.window, evaluation.trees, parts))
    features = pd.read_parquet(FEATURES_PARQUET)
    live = Fold("live", features["hour_end_utc"].max(), None)
    trained: dict[str, FittedModel] = {}
    learned: list[pd.Series] = []
    for hours in serving.horizons_hours:
        train, _ = split(horizon_view(features, hours, config), live, config.features.horizon_hours)
        learned.append(train.loc[train["target"].notna(), "target_hour_end_utc"])
        for name, objective in band_objectives(model, serving).items():
            key = f"h{hours:02d}_{name}"
            trained[key] = fit(train, Recipe(evaluation.columns, objective), FixedTrees(evaluation.trees[key]))
        print(f"horizon {hours:2d} h: trained on {learned[-1].size:,} rows", flush=True)
    spec = build_spec(window_of(pd.concat(learned)), {key: m.trees for key, m in trained.items()}, parts)
    assert_same_except_window(evaluation, spec)
    return trained, spec


def main() -> int:
    try:
        trained, spec = train_live()
    except (ConfigError, InputsOutOfDate, EmbargoError, FeatureError, SpecMismatch) as err:
        print(f"STOPPED: {err}", file=sys.stderr)
        return 1
    LIVE_MODELS.mkdir(parents=True, exist_ok=True)
    for key, fitted in trained.items():
        fitted.booster.save_model(LIVE_MODELS / f"{key}.txt", num_iteration=fitted.trees)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "model_spec_live.json").write_text(spec_to_json(spec))
    print(f"\nLive models: {len(trained)}, learning from targets {spec.window.first_target_utc} -> "
          f"{spec.window.last_target_utc}. Same recipe and trees as the evaluation models.")
    print("They have no accuracy number of their own: the site quotes the held-out 2025 numbers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
