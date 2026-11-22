"""Live forecasts, stage F: copy the held-out 2025 accuracy numbers into the file the site serves.

The site shows only the EVALUATION model's numbers (trained on 2023-2024, scored on held-out
2025), from reports/stage7/horizons.csv and reports/stage6/tails.csv. tests/test_accuracy.py
fails if serving/accuracy_2025.json ever disagrees with those reports; re-run this script after
re-running the evaluation.

Usage:  .venv/bin/python scripts/15_accuracy_file.py
"""

import sys
from typing import Final

import pandas as pd

from delhi_pm25.accuracy import accuracy_summary
from delhi_pm25.paths import PROJECT_ROOT, REPORTS_DIR, SERVING_DIR

OUT: Final = SERVING_DIR / "accuracy_2025.json"


def main() -> int:
    summary = accuracy_summary(pd.read_csv(REPORTS_DIR / "stage7" / "horizons.csv"),
                               pd.read_csv(REPORTS_DIR / "stage6" / "tails.csv", index_col=0))
    OUT.write_text(summary.model_dump_json(indent=1) + "\n")
    at48 = next(h for h in summary.horizons if h.horizon_h == 48)
    print(f"Wrote {OUT.relative_to(PROJECT_ROOT)}: MAE {at48.model_mae} at 48 h; band coverage "
          f"{at48.inside_band_pct}% overall, {at48.inside_band_smoggiest_10pct}% in the smoggiest 10%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
