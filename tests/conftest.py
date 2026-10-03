"""Shared test fixtures."""

import pandas as pd
import pytest

from delhi_pm25.config import CeilingRule, FlatRule, HourlyRules, PipelineConfig, SpikeRule


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
    )
