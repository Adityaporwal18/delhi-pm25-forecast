"""The full description of a set of forecast models, apart from the data they learn from.

Two sets exist. The EVALUATION models (trained on 2023-2024, scored on 2025) produced every
published accuracy number. The LIVE models learn from everything up to the latest reading, so
they have no held-out year and no accuracy number of their own; the site quotes the evaluation
numbers for them. That is honest only if the two sets are identical in every respect except
their training window. assert_same_except_window checks that: scripts/11_live_models.py runs it before
saving, and tests/test_model_spec.py runs it on the committed specs.
"""

import json
from dataclasses import asdict, dataclass, fields

import pandas as pd

from delhi_pm25.config import PipelineConfig
from delhi_pm25.model import BASE_PARAMS
from delhi_pm25.model_settings import ModelSettings, ServingSettings


class SpecMismatch(Exception):
    """The live models would differ from the evaluation models in more than the training window."""


@dataclass(frozen=True, slots=True)
class TrainingWindow:
    """First and last target hour (UTC, end of hour) among the rows the models learn from."""

    first_target_utc: str
    last_target_utc: str


@dataclass(frozen=True, slots=True)
class ModelSpec:
    window: TrainingWindow
    target: str
    columns: tuple[str, ...]
    objective: str
    band_quantiles: tuple[float, float]
    horizons_hours: tuple[int, ...]
    trees: dict[str, int]
    lightgbm: dict[str, object]


@dataclass(frozen=True, slots=True)
class SpecParts:
    """What both model sets are built from: the settings and the feature columns."""

    config: PipelineConfig
    model: ModelSettings
    serving: ServingSettings
    columns: tuple[str, ...]


def build_spec(window: TrainingWindow, trees: dict[str, int], parts: SpecParts) -> ModelSpec:
    return ModelSpec(
        window=window, target=parts.config.target, columns=parts.columns, objective=parts.model.objective,
        band_quantiles=parts.serving.band_quantiles, horizons_hours=parts.serving.horizons_hours,
        trees=trees, lightgbm=dict(BASE_PARAMS),
    )


def window_of(targets: pd.Series) -> TrainingWindow:
    """The training window of rows whose (measured) target hours are `targets`."""
    return TrainingWindow(first_target_utc=targets.min().isoformat(), last_target_utc=targets.max().isoformat())


def assert_same_except_window(evaluation: ModelSpec, live: ModelSpec) -> None:
    different = [field.name for field in fields(ModelSpec)
                 if field.name != "window" and getattr(evaluation, field.name) != getattr(live, field.name)]
    if different:
        raise SpecMismatch(
            f"the live models differ from the evaluation models in {different}, "
            "so the published 2025 accuracy would not describe them"
        )


def spec_to_json(spec: ModelSpec) -> str:
    return json.dumps(asdict(spec), indent=2, sort_keys=True) + "\n"


def spec_from_json(text: str) -> ModelSpec:
    data = json.loads(text)
    low, high = data["band_quantiles"]
    return ModelSpec(
        window=TrainingWindow(**data["window"]), target=data["target"], columns=tuple(data["columns"]),
        objective=data["objective"], band_quantiles=(low, high), horizons_hours=tuple(data["horizons_hours"]),
        trees=dict(data["trees"]), lightgbm=dict(data["lightgbm"]),
    )
