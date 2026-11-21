"""Live forecasts, stage C: features for the latest hour, built by the SAME steps as training.

Training runs to_hourly -> check_complete_grid -> apply_rules -> build_features over all years
(scripts/05_clean.py and 06_features.py). Live forecasts run exactly those functions over the
last LIVE_DAYS of readings: no second feature path. tests/test_live.py checks that both give
identical features for the same hour. Ten days cover the longest look-back (the 168-hour lag and
mean) with three days to spare.

Known difference: the spike rule needs the following hour, so the newest hour cannot be
checked for a spike yet (training data always had a following hour).
"""

from typing import Final

import pandas as pd

from delhi_pm25.clean import check_complete_grid, to_hourly
from delhi_pm25.clean_rules import apply_rules
from delhi_pm25.config import PipelineConfig
from delhi_pm25.features import build_features

LIVE_DAYS: Final = 10
MIN_REPORTING_SHARE: Final = 0.5


def latest_hour(hourly: pd.DataFrame, target: str) -> pd.Timestamp:
    """The latest hour in which at least half the stations reported the target: forecasts start
    there, so a station that reports early does not leave most stations without a value now."""
    share = hourly[target].notna().groupby(hourly["hour_end_utc"]).mean()
    return share[share >= MIN_REPORTING_SHARE].index.max()


def live_features(readings: pd.DataFrame, weather: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """Feature rows (one per station) for the latest hour most stations have reported."""
    hourly = to_hourly(readings, config.hourly, config.ceiling)
    check_complete_grid(hourly)
    cleaned = apply_rules(hourly, config).cleaned
    features = build_features(cleaned, weather, config)
    return features[features["hour_end_utc"] == latest_hour(cleaned, config.target)].reset_index(drop=True)
