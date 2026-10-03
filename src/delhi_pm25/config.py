"""Pipeline settings: config/pipeline.toml, parsed once into typed, read-only values.

Every Stage 2 decision (D0-D6) lives in that file, not in code: changing a decision
is an edit plus a re-run, and git history shows when and why it changed. A missing
or malformed setting stops the run here, with a message naming the setting.
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal

import pandas as pd

from delhi_pm25.raw_cpcb import POLLUTANTS

Target = Literal["pm25", "pm10"]
Clock = Literal["ist", "utc"]


class ConfigError(Exception):
    """config/pipeline.toml lacks a setting or holds a value the pipeline cannot use."""


@dataclass(frozen=True, slots=True)
class HourlyRules:
    min_readings: int
    clock: Clock


@dataclass(frozen=True, slots=True)
class CeilingRule:
    ug_m3: float
    pollutants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SpikeRule:
    jump_ug_m3: float
    calm_city_median_ug_m3: float


@dataclass(frozen=True, slots=True)
class FlatRule:
    min_hours: int
    pollutants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    target: Target
    test_start: pd.Timestamp
    min_train_coverage_pct: float
    hourly: HourlyRules
    ceiling: CeilingRule
    spikes: Mapping[str, SpikeRule]
    flat_runs: FlatRule


@dataclass(frozen=True, slots=True)
class _Table:
    name: str
    values: Mapping[str, object]

    def get(self, key: str) -> object:
        if key not in self.values:
            raise ConfigError(f"[{self.name}] {key} is missing")
        return self.values[key]

    def table(self, key: str) -> "_Table":
        value = self.get(key)
        if not isinstance(value, dict):
            raise ConfigError(f"[{self.name}] {key} must be a table of settings")
        return _Table(key if self.name == "top level" else f"{self.name}.{key}", value)

    def number(self, key: str, at_most: float = float("inf")) -> float:
        value = self.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float) or not 0 < value <= at_most:
            raise ConfigError(f"[{self.name}] {key} must be a number above 0 and at most {at_most}, got {value!r}")
        return float(value)

    def whole_number(self, key: str, allowed: range) -> int:
        value = self.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value not in allowed:
            raise ConfigError(
                f"[{self.name}] {key} must be a whole number from {allowed.start} to {allowed.stop - 1}, got {value!r}"
            )
        return value

    def pollutants(self, key: str) -> tuple[str, ...]:
        value = self.get(key)
        if not isinstance(value, list) or not value:
            raise ConfigError(f"[{self.name}] {key} must be a non-empty list of pollutants")
        unknown = [p for p in value if p not in POLLUTANTS]
        if unknown:
            raise ConfigError(f"[{self.name}] {key}: unknown pollutant(s) {unknown}; choose from {POLLUTANTS}")
        return tuple(value)


def _target(value: object) -> Target:
    match value:
        case "pm25":
            return "pm25"
        case "pm10":
            return "pm10"
        case _:
            raise ConfigError(f'target must be "pm25" or "pm10", got {value!r}')


def _clock(value: object) -> Clock:
    match value:
        case "ist":
            return "ist"
        case "utc":
            return "utc"
        case _:
            raise ConfigError(f'[hourly] clock must be "ist" or "utc", got {value!r}')


def _test_start(value: object) -> pd.Timestamp:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ConfigError(
            f"[split] test_start must be a date-time with a time zone, e.g. 2025-01-01T00:00:00+05:30; got {value!r}"
        )
    return pd.Timestamp(value).tz_convert("UTC")


def _spike_rules(spikes: _Table) -> Mapping[str, SpikeRule]:
    unknown = [p for p in spikes.values if p not in POLLUTANTS]
    if unknown:
        raise ConfigError(f"[spikes] unknown pollutant(s) {unknown}; choose from {POLLUTANTS}")
    rules = {}
    for pollutant in spikes.values:
        rule = spikes.table(pollutant)
        rules[pollutant] = SpikeRule(rule.number("jump_ug_m3"), rule.number("calm_city_median_ug_m3"))
    return MappingProxyType(rules)


def load_config(path: Path) -> PipelineConfig:
    """Read config/pipeline.toml; raise ConfigError naming the first bad setting."""
    try:
        with path.open("rb") as file:
            root = _Table("top level", tomllib.load(file))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    hourly, ceiling, flat = root.table("hourly"), root.table("ceiling"), root.table("flat_runs")
    return PipelineConfig(
        target=_target(root.get("target")),
        test_start=_test_start(root.table("split").get("test_start")),
        min_train_coverage_pct=root.table("stations").number("min_train_coverage_pct", at_most=100.0),
        hourly=HourlyRules(hourly.whole_number("min_readings", range(1, 5)), _clock(hourly.get("clock"))),
        ceiling=CeilingRule(ceiling.number("ug_m3"), ceiling.pollutants("pollutants")),
        spikes=_spike_rules(root.table("spikes")),
        flat_runs=FlatRule(flat.whole_number("min_hours", range(2, 10_000)), flat.pollutants("pollutants")),
    )
