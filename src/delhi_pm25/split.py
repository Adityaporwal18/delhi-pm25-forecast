"""Stage 4: split the feature rows by TIME, with a gap before every boundary.

A row is a forecast made at hour t for the hour ending t + horizon. Rows are stamped with the
END of their hour, so 18:30 UTC on 31 Dec 2024 (midnight in Delhi) ends the last hour of 2024.
Training rows are forecasts made at least `embargo_hours` before the boundary, so no training
target lies past it; evaluation rows are the ones whose TARGET hour lies past it. Features may
look back across the boundary: the past is known when a forecast is made.
"""

from dataclasses import dataclass

import pandas as pd

from delhi_pm25.clean import HOUR
from delhi_pm25.config import PipelineConfig


class EmbargoError(Exception):
    """A training row's target hour starts on or after the boundary, so the model would learn
    from the period it is scored on."""


@dataclass(frozen=True, slots=True)
class Fold:
    """`boundary`: end of the last hour on the training side. `until`: end of the last target
    hour this fold scores (None = to the end of the data)."""

    name: str
    boundary: pd.Timestamp
    until: pd.Timestamp | None


def folds(config: PipelineConfig) -> tuple[Fold, Fold]:
    """Validation: train on 2023, score 2024 (for choosing features and settings).
    Test: train on 2023-2024, score 2025 (once, at the end; never past test_end)."""
    return (
        Fold("validation", config.validation_start, config.test_start),
        Fold("test", config.test_start, config.test_end),
    )


def check_embargo(train: pd.DataFrame, boundary: pd.Timestamp) -> None:
    """Stop if any training row's target hour starts on or after `boundary` (it ends later)."""
    late = train["target_hour_end_utc"] > boundary
    if late.any():
        first = train.loc[late, "target_hour_end_utc"].min()
        raise EmbargoError(
            f"{int(late.sum()):,} training rows have a target hour that starts on or after {boundary} "
            f"(the first ends {first}). Training forecasts must be made at least one horizon before it."
        )


def split(features: pd.DataFrame, fold: Fold, embargo_hours: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(train, evaluate) for one fold. Raises EmbargoError if the gap is shorter than the horizon."""
    made_in_time = features["hour_end_utc"] <= fold.boundary - embargo_hours * HOUR
    train = features.loc[made_in_time].reset_index(drop=True)
    check_embargo(train, fold.boundary)
    scored = features["target_hour_end_utc"] > fold.boundary
    if fold.until is not None:
        scored = scored & (features["target_hour_end_utc"] <= fold.until)
    return train, features.loc[scored].reset_index(drop=True)
