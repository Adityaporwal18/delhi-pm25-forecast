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
MIN_REPORTING_SHARE: Final = 2 / 3


class NoForecastHour(Exception):
    """No hour in the live window was reported by enough stations to forecast from."""


def latest_hour(hourly: pd.DataFrame, target: str) -> pd.Timestamp:
    """The latest hour that at least two thirds of the stations reported: forecasts start there.
    OpenAQ delivers stations in batches, so the newest hour is often only partly in; starting from
    it would leave many stations without a value now (and the refresh would refuse to publish)."""
    share = hourly[target].notna().groupby(hourly["hour_end_utc"]).mean()
    complete = share[share >= MIN_REPORTING_SHARE]
    if complete.empty:
        raise NoForecastHour(f"no hour in the last {LIVE_DAYS} days has {target} from at least two thirds of the stations")
    return complete.index.max()


def live_features(readings: pd.DataFrame, weather: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """Feature rows (one per station) for the latest hour most stations have reported."""
    hourly = to_hourly(readings, config.hourly, config.ceiling)
    check_complete_grid(hourly)
    cleaned = apply_rules(hourly, config).cleaned
    features = build_features(cleaned, weather, config)
    return features[features["hour_end_utc"] == latest_hour(cleaned, config.target)].reset_index(drop=True)
