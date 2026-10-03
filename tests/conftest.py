"""Shared test fixtures."""

from datetime import date

import pandas as pd
import pytest

from delhi_pm25.config import (
    CeilingRule,
    DiwaliWindow,
    FeatureSettings,
    FlatRule,
    HourlyRules,
    PipelineConfig,
    SpikeRule,
)


@pytest.fixture
def config() -> PipelineConfig:
    """Cleaning rules written out in full, so tests never depend on config/pipeline.toml."""
    return PipelineConfig(
        target="pm25",
        test_start=pd.Timestamp("2024-12-31 18:30", tz="UTC"),
        min_train_coverage_pct=75.0,
        hourly=HourlyRules(min_readings=1, clock="ist"),
        ceiling=CeilingRule(ug_m3=1000.0, pollutants=("pm25",)),
        spikes={"pm25": SpikeRule(
            jump_ug_m3=200.0,
            calm_city_median_ug_m3=200.0,
            polluted_city_median_ug_m3=300.0,
            min_ratio_in_between=2.0,
        )},
        flat_runs=FlatRule(min_hours=6, pollutants=("pm25",), exempt_hours_at_ceiling=True),
        features=FeatureSettings(
            horizon_hours=48,
            lags_hours=(0, 3, 6, 12, 24, 48, 168),
            rolling_hours=(6, 24, 72, 168),
            rolling_min_share=0.5,
            other_pollutants=("pm10", "no2", "co"),
            diwali=DiwaliWindow(
                dates=(date(2023, 11, 12), date(2024, 10, 31), date(2025, 10, 20), date(2026, 11, 8)),
                start_hour_ist=18,
                hours=18,
            ),
            stubble_season=(1015, 1115),
        ),
    )
