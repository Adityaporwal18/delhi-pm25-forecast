"""Tests for the held-out 2025 accuracy numbers the site shows (src/delhi_pm25/accuracy.py)."""

import pandas as pd

from delhi_pm25.accuracy import AccuracySummary, accuracy_summary
from delhi_pm25.paths import REPORTS_DIR, SERVING_DIR


def test_summary_rounds_to_one_decimal_and_keeps_the_heavy_smog_row() -> None:
    # Given: one horizon of reports/stage7/horizons.csv and two rows of reports/stage6/tails.csv
    horizons = pd.DataFrame({"horizon_h": [48], "persistence_mae": [43.37], "climatology_mae": [37.97],
                             "model_mae": [34.71], "inside_band_pct": [79.0], "inside_band_smoggiest_10pct": [59.3]})
    tails = pd.DataFrame({"persistence_mae": [43.4, 108.3], "climatology_mae": [38.0, 89.3], "model_mae": [34.7, 106.0],
                          "model_bias": [-9.8, -95.6]}, index=pd.Index(["all hours", "smoggiest 10%, by outcome"], name="hours"))
    # When
    summary = accuracy_summary(horizons, tails)
    # Then
    assert (summary.horizons[0].model_mae, summary.horizons[0].climatology_mae, summary.smoggiest_10pct_48h.model_bias) == (
        34.7, 38.0, -95.6,
    )


def test_the_numbers_the_site_shows_match_the_evaluation_reports() -> None:
    # Given: the file the site serves, and the evaluation reports it must come from
    published = AccuracySummary.model_validate_json((SERVING_DIR / "accuracy_2025.json").read_text())
    horizons = pd.read_csv(REPORTS_DIR / "stage7" / "horizons.csv")
    tails = pd.read_csv(REPORTS_DIR / "stage6" / "tails.csv", index_col=0)
    # When / Then: a re-run that changes the reports must also refresh the site's numbers
    assert published == accuracy_summary(horizons, tails)
