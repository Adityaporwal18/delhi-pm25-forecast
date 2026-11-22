"""The held-out 2025 accuracy numbers the site shows, taken from the evaluation reports.

Every accuracy number on the site describes the EVALUATION model (trained on 2023-2024, scored
on the held-out 2025 test year). The live view quotes them as the expected accuracy, labelled as
based on held-out 2025 testing, never as a measurement of the live models. accuracy_summary builds
them from reports/stage7/horizons.csv (every horizon) and reports/stage6/tails.csv (the smoggiest
hours at 48 h); scripts/15_accuracy_file.py writes serving/accuracy_2025.json, and
tests/test_accuracy.py fails if that file ever disagrees with the reports.
"""

from typing import Final

import pandas as pd
from pydantic import BaseModel

SMOGGY_ROW: Final = "smoggiest 10%, by outcome"
SOURCE: Final = "Evaluation model: trained on 2023-2024, scored on the held-out 2025 test year"


class HorizonAccuracy(BaseModel):
    horizon_h: int
    model_mae: float
    persistence_mae: float
    climatology_mae: float
    inside_band_pct: float
    inside_band_smoggiest_10pct: float


class SmogAccuracy(BaseModel):
    """The 48-hour forecasts in the smoggiest 10% of 2025 hours (picked by how smoggy they turned out)."""

    model_mae: float
    climatology_mae: float
    persistence_mae: float
    model_bias: float


class AccuracySummary(BaseModel):
    source: str
    horizons: list[HorizonAccuracy]
    smoggiest_10pct_48h: SmogAccuracy


def _rounded(table: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return table.astype({column: "float64" for column in columns}).round({column: 1 for column in columns})


def accuracy_summary(horizons: pd.DataFrame, tails: pd.DataFrame) -> AccuracySummary:
    """horizons: reports/stage7/horizons.csv; tails: reports/stage6/tails.csv, indexed by its hours column."""
    columns = list(HorizonAccuracy.model_fields)
    per_horizon = _rounded(horizons, columns[1:])[columns]
    smog = _rounded(tails.loc[[SMOGGY_ROW]], list(SmogAccuracy.model_fields)).iloc[0]
    return AccuracySummary(
        source=SOURCE,
        horizons=[HorizonAccuracy.model_validate(row) for row in per_horizon.to_dict("records")],
        smoggiest_10pct_48h=SmogAccuracy.model_validate(smog[list(SmogAccuracy.model_fields)].to_dict()),
    )
