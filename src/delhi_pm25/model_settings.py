"""Stage 5 settings: the [model] table of config/pipeline.toml.

Kept apart from config.py (data, cleaning and feature settings) so each file stays small.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from delhi_pm25.config import ConfigError, Table, read_table

Objective = Literal["l1", "l2"]


@dataclass(frozen=True, slots=True)
class ModelSettings:
    objective: Objective
    max_trees: int
    early_stopping_rounds: int
    ablations: Mapping[str, tuple[str, ...]]
    min_gain_pct: float


def _objective(value: object) -> Objective:
    match value:
        case "l1" | "l2":
            return value
        case _:
            raise ConfigError(f'[model] objective must be "l1" (absolute error) or "l2" (squared error), got {value!r}')


def _ablations(groups: Table) -> Mapping[str, tuple[str, ...]]:
    """Each entry names a comparison and the feature columns it removes."""
    parsed: dict[str, tuple[str, ...]] = {}
    for name, value in groups.values.items():
        if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
            raise ConfigError(f"[{groups.name}] {name} must be a non-empty list of feature names, got {value!r}")
        parsed[name] = tuple(value)
    return MappingProxyType(parsed)


def load_model_settings(path: Path) -> ModelSettings:
    """Read [model] from config/pipeline.toml; raise ConfigError naming the first bad setting."""
    model = read_table(path).table("model")
    return ModelSettings(
        objective=_objective(model.get("objective")),
        max_trees=model.whole_number("max_trees", range(1, 100_001)),
        early_stopping_rounds=model.whole_number("early_stopping_rounds", range(1, 10_001)),
        ablations=_ablations(model.table("ablations")),
        min_gain_pct=model.table("keep_rule").number("min_gain_pct", at_most=100.0),
    )
