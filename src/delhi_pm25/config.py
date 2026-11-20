"""Pipeline settings: config/pipeline.toml, parsed once into typed, read-only values.

Every Stage 2 decision (D0-D6) lives in that file, not in code: changing a decision
is an edit plus a re-run, and git history shows when and why it changed. A missing
or malformed setting stops the run here, with a message naming the setting.
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
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
    polluted_city_median_ug_m3: float
    min_ratio_in_between: float


@dataclass(frozen=True, slots=True)
class FlatRule:
    min_hours: int
    pollutants: tuple[str, ...]
    exempt_hours_at_ceiling: bool


@dataclass(frozen=True, slots=True)
class DiwaliWindow:
    dates: tuple[date, ...]
    start_hour_ist: int
    hours: int


@dataclass(frozen=True, slots=True)
class FeatureSettings:
    horizon_hours: int
    lags_hours: tuple[int, ...]
    rolling_hours: tuple[int, ...]
    rolling_min_share: float
    other_pollutants: tuple[str, ...]
    diwali: DiwaliWindow
    stubble_season: tuple[int, int]


@dataclass(frozen=True, slots=True)
class BaselineSettings:
    climatology_days_either_side: int
    climatology_min_values: int


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    target: Target
    test_start: pd.Timestamp
    validation_start: pd.Timestamp
    min_train_coverage_pct: float
    hourly: HourlyRules
    ceiling: CeilingRule
    spikes: Mapping[str, SpikeRule]
    flat_runs: FlatRule
    features: FeatureSettings
    baselines: BaselineSettings


@dataclass(frozen=True, slots=True)
class Table:
    name: str
    values: Mapping[str, object]

    def get(self, key: str) -> object:
        if key not in self.values:
            raise ConfigError(f"[{self.name}] {key} is missing")
        return self.values[key]

    def table(self, key: str) -> "Table":
        value = self.get(key)
        if not isinstance(value, dict):
            raise ConfigError(f"[{self.name}] {key} must be a table of settings")
        return Table(key if self.name == "top level" else f"{self.name}.{key}", value)

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

    def flag(self, key: str) -> bool:
        value = self.get(key)
        if not isinstance(value, bool):
            raise ConfigError(f"[{self.name}] {key} must be true or false, got {value!r}")
        return value

    def whole_numbers(self, key: str, allowed: range) -> tuple[int, ...]:
        value = self.get(key)
        if not isinstance(value, list) or not value or any(type(v) is not int or v not in allowed for v in value):
            raise ConfigError(f"[{self.name}] {key} must be a list of whole numbers from "
                              f"{allowed.start} to {allowed.stop - 1}, got {value!r}")
        return tuple(value)

    def dates(self, key: str) -> tuple[date, ...]:
        value = self.get(key)
        if not isinstance(value, list) or not value or any(type(v) is not date for v in value):
            raise ConfigError(f"[{self.name}] {key} must be a list of dates like 2024-10-31, got {value!r}")
        return tuple(value)

    def month_day(self, key: str) -> int:
        """A day of the year written "MM-DD" (e.g. "10-15"), returned as the number 1015.
        Checked against a leap year, so "02-29" is allowed."""
        value = self.get(key)
        try:
            day = date.fromisoformat(f"2024-{value}")
        except ValueError as error:
            raise ConfigError(f'[{self.name}] {key} must be a day of the year written "MM-DD", '
                              f'e.g. "10-15", got {value!r}') from error
        return day.month * 100 + day.day


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


def _moment(split: Table, key: str) -> pd.Timestamp:
    value = split.get(key)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ConfigError(
            f"[split] {key} must be a date-time with a time zone, e.g. 2025-01-01T00:00:00+05:30; got {value!r}"
        )
    return pd.Timestamp(value).tz_convert("UTC")


def _split_moments(split: Table) -> tuple[pd.Timestamp, pd.Timestamp]:
    test_start, validation_start = _moment(split, "test_start"), _moment(split, "validation_start")
    if validation_start >= test_start:
        raise ConfigError(f"[split] validation_start ({validation_start}) must be before test_start ({test_start})")
    return test_start, validation_start


def _baseline_settings(baselines: Table) -> BaselineSettings:
    return BaselineSettings(
        climatology_days_either_side=baselines.whole_number("climatology_days_either_side", range(184)),
        climatology_min_values=baselines.whole_number("climatology_min_values", range(1, 10_000)),
    )


def _spike_rules(spikes: Table) -> Mapping[str, SpikeRule]:
    unknown = [p for p in spikes.values if p not in POLLUTANTS]
    if unknown:
        raise ConfigError(f"[spikes] unknown pollutant(s) {unknown}; choose from {POLLUTANTS}")
    rules = {}
    for pollutant in spikes.values:
        rules[pollutant] = _spike_rule(spikes.table(pollutant))
    return MappingProxyType(rules)


def _spike_rule(rule: Table) -> SpikeRule:
    calm, polluted = rule.number("calm_city_median_ug_m3"), rule.number("polluted_city_median_ug_m3")
    if polluted < calm:
        raise ConfigError(f"[{rule.name}] polluted_city_median_ug_m3 ({polluted:g}) must not be "
                          f"below calm_city_median_ug_m3 ({calm:g})")
    return SpikeRule(rule.number("jump_ug_m3"), calm, polluted, rule.number("min_ratio_in_between"))


def _flat_rule(flat: Table, ceiling: CeilingRule) -> FlatRule:
    pollutants, exempt = flat.pollutants("pollutants"), flat.flag("exempt_hours_at_ceiling")
    unflagged = sorted(set(pollutants) - set(ceiling.pollutants))
    if exempt and unflagged:
        raise ConfigError(f"[{flat.name}] exempt_hours_at_ceiling needs a ceiling flag for every "
                          f"pollutant, but [ceiling] pollutants lacks {unflagged}")
    return FlatRule(flat.whole_number("min_hours", range(2, 10_000)), pollutants, exempt)


def _feature_settings(features: Table, target: Target, ceiling: CeilingRule) -> FeatureSettings:
    others = features.pollutants("other_pollutants")
    if target in others:
        raise ConfigError(f"[{features.name}] other_pollutants must not include the target "
                          f"{target!r}: its own history is already in the lags")
    if target not in ceiling.pollutants:
        raise ConfigError(f"[ceiling] pollutants must include the target {target!r}: the "
                          "'hit the limit' feature needs its flag")
    diwali, stubble = features.table("diwali"), features.table("stubble")
    first, last = stubble.month_day("first_day"), stubble.month_day("last_day")
    if first > last:
        raise ConfigError(f"[{stubble.name}] first_day must not be after last_day "
                          "(a season running past 31 December is not supported)")
    return FeatureSettings(
        horizon_hours=features.whole_number("horizon_hours", range(1, 169)),
        lags_hours=features.whole_numbers("lags_hours", range(673)),
        rolling_hours=features.whole_numbers("rolling_hours", range(2, 673)),
        rolling_min_share=features.number("rolling_min_share", at_most=1.0),
        other_pollutants=others,
        diwali=DiwaliWindow(diwali.dates("dates"), diwali.whole_number("start_hour_ist", range(24)),
                            diwali.whole_number("hours", range(1, 73))),
        stubble_season=(first, last),
    )


def read_table(path: Path) -> Table:
    """The whole TOML file as a Table; ConfigError if it cannot be read."""
    try:
        with path.open("rb") as file:
            return Table("top level", tomllib.load(file))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error


def load_config(path: Path) -> PipelineConfig:
    """Read config/pipeline.toml; raise ConfigError naming the first bad setting."""
    root = read_table(path)
    hourly, ceiling = root.table("hourly"), root.table("ceiling")
    ceiling_rule = CeilingRule(ceiling.number("ug_m3"), ceiling.pollutants("pollutants"))
    target = _target(root.get("target"))
    test_start, validation_start = _split_moments(root.table("split"))
    return PipelineConfig(
        target=target,
        test_start=test_start,
        validation_start=validation_start,
        min_train_coverage_pct=root.table("stations").number("min_train_coverage_pct", at_most=100.0),
        hourly=HourlyRules(hourly.whole_number("min_readings", range(1, 5)), _clock(hourly.get("clock"))),
        ceiling=ceiling_rule,
        spikes=_spike_rules(root.table("spikes")),
        flat_runs=_flat_rule(root.table("flat_runs"), ceiling_rule),
        features=_feature_settings(root.table("features"), target, ceiling_rule),
        baselines=_baseline_settings(root.table("baselines")),
    )
