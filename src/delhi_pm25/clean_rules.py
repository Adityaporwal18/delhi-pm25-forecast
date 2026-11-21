"""Stage 2 cleaning, part 2: station selection (D3), spikes (D4.1) and frozen runs (D4.2).

The rules blank values (set them to NaN); they never delete rows, so the hourly grid
stays complete. Each rule also returns a log of exactly what it touched.
"""

from collections.abc import Mapping
from typing import Final

import numpy as np
import pandas as pd

from delhi_pm25.clean import HOUR
from delhi_pm25.config import FlatRule, PipelineConfig, SpikeRule
from delhi_pm25.series_checks import flat_mask, isolated_spikes

SLOTS_PER_HOUR: Final = 4
DELHI: Final = "Asia/Kolkata"
TAIL_SHARES: Final = (0.10, 0.01, 0.001)
SPIKE_LOG_COLUMNS: Final = [
    "slug", "hour_end_utc", "pollutant", "before", "value", "after", "ratio", "city_median", "action",
]
RUN_LOG_COLUMNS: Final = ["slug", "pollutant", "first_hour_end_utc", "last_hour_end_utc", "hours", "value"]


def _period(hourly: pd.DataFrame, config: PipelineConfig) -> np.ndarray:
    """"train" up to test_start, "test" up to test_end, "after test" beyond (newer data for the
    live model only, never part of a published number)."""
    end = hourly["hour_end_utc"]
    return np.select([end <= config.test_start, end <= config.test_end], ["train", "test"], default="after test")


def station_selection(hourly: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """D3 (b): keep a station only if it reported the target in at least
    `min_train_coverage_pct` % of its 15-min slots during TRAINING.

    Coverage counts raw readings (n_<target> of 4 per hour), so it does not depend on any
    cleaning threshold. Test-period and per-year coverage are shown for information only.
    """
    pct = hourly[f"n_{config.target}"] / SLOTS_PER_HOUR * 100
    period = pd.Series(_period(hourly, config), index=hourly.index, name="period")
    delhi_year = (hourly["hour_end_utc"] - HOUR).dt.tz_convert(DELHI).dt.year.rename("year")
    by_period = pct.groupby([hourly["slug"], period], observed=True).mean().unstack()
    by_year = pct.groupby([hourly["slug"], delhi_year], observed=True).mean().unstack()
    table = pd.concat([by_period.reindex(columns=["train", "test"]).add_suffix("_readings_pct"),
                       by_year.add_prefix("readings_pct_")], axis=1)
    kept = table["train_readings_pct"] >= config.min_train_coverage_pct
    return table.round(1).assign(kept=kept)


def remove_spikes(hourly: pd.DataFrame, rules: Mapping[str, SpikeRule]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """D4.1 (d): blank a one-hour spike unless it sits inside real city-wide smog.

    Spike = more than `jump_ug_m3` above BOTH neighbouring hours. Instrument glitches look
    like that, but so does a real Diwali-night peak; the city median tells them apart.
    City median below `calm_city_median_ug_m3`: removed. At or above
    `polluted_city_median_ug_m3`: kept. In between: removed only if the spike is at least
    `min_ratio_in_between` times its higher neighbouring hour (a glitch-sized jump).
    Returns the cleaned table and a log of every spike found, removed or kept.
    """
    cleaned = hourly.copy()
    logs = []
    for pollutant, rule in rules.items():
        values = hourly[pollutant]
        by_station = values.groupby(hourly["slug"], observed=True)
        spike = by_station.transform(isolated_spikes, jump=rule.jump_ug_m3)
        before, after = by_station.shift(1), by_station.shift(-1)
        higher = np.fmax(before, after)
        city = values.groupby(hourly["hour_end_utc"]).transform("median")
        calm = city < rule.calm_city_median_ug_m3
        polluted = city >= rule.polluted_city_median_ug_m3
        glitch_sized = values >= rule.min_ratio_in_between * higher
        remove = spike & (calm | (~polluted & glitch_sized))
        neighbour_test = f"{rule.min_ratio_in_between:g}x higher neighbour"
        action = np.select(
            [calm, polluted, glitch_sized],
            ["removed: city calm", "kept: city polluted", f"removed: >= {neighbour_test}"],
            default=f"kept: < {neighbour_test}",
        )
        log = pd.DataFrame({
            "slug": hourly["slug"], "hour_end_utc": hourly["hour_end_utc"], "pollutant": pollutant,
            "before": before, "value": values, "after": after, "ratio": (values / higher).round(2),
            "city_median": city, "action": action,
        })
        logs.append(log[spike])
        cleaned[pollutant] = values.mask(remove)
    if not logs:
        return cleaned, pd.DataFrame(columns=SPIKE_LOG_COLUMNS)
    return cleaned, pd.concat(logs, ignore_index=True)


def blank_flat_runs(hourly: pd.DataFrame, rule: FlatRule) -> tuple[pd.DataFrame, pd.DataFrame]:
    """D4.2 (b): blank values repeated unchanged for `min_hours` or more hours (a stuck
    analyser, or a logger copying its last value). Returns the cleaned table and one log
    row per blanked run. Runs never continue from one station into the next.

    With `exempt_hours_at_ceiling`, hours where the analyser hit its limit are never
    blanked: a value pinned at the limit may be real smog above it, and the
    `<pollutant>_at_ceiling` flag keeps that information.
    """
    cleaned = hourly.copy()
    slug = hourly["slug"]
    logs = []
    for pollutant in rule.pollutants:
        values = hourly[pollutant]
        frozen = values.groupby(slug, observed=True).transform(flat_mask, min_hours=rule.min_hours)
        if rule.exempt_hours_at_ceiling:
            frozen = frozen & ~hourly[f"{pollutant}_at_ceiling"]
        run_id = (values.ne(values.shift()) | slug.ne(slug.shift())).cumsum()
        runs = hourly[frozen].groupby(run_id[frozen]).agg(
            slug=("slug", "first"), first_hour_end_utc=("hour_end_utc", "first"),
            last_hour_end_utc=("hour_end_utc", "last"), hours=("hour_end_utc", "size"),
            value=(pollutant, "first"))
        logs.append(runs.assign(pollutant=pollutant)[RUN_LOG_COLUMNS])
        cleaned[pollutant] = values.mask(frozen)
    return cleaned, pd.concat(logs, ignore_index=True)


def missing_in_worst_hours(hourly: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """How much of the target is blank in the smoggiest hours, compared with all hours.

    An hour's smog level is the median target over the stations that DID report, so an
    hour still counts as smoggy when its worst readings are missing. For each period:
    all hours, then the smoggiest 10%, 1% and 0.1% of hours.
    blank_pct   = station-hours with no target value.
    partial_pct = values built from only 1-3 of the 4 readings; when the missing readings
                  were the highest ones, such an hour's average comes out too low.
    A blank share that climbs in the tail means the hardest hours cannot be scored
    ('missing not at random').
    """
    target = config.target
    periods = _period(hourly, config)
    rows = []
    for period in ("train", "test"):
        part = hourly[periods == period]
        city = part.groupby("hour_end_utc")[target].median()
        smog = part["hour_end_utc"].map(city)
        tails = {"all hours": pd.Series(True, index=part.index)}
        for share in TAIL_SHARES:
            tails[f"smoggiest {share:.1%}"] = smog >= city.quantile(1 - share)
        for name, in_tail in tails.items():
            tail = part[in_tail]
            partial = tail[target].notna() & tail[f"n_{target}"].between(1, SLOTS_PER_HOUR - 1)
            rows.append({
                "period": period, "hours": name, "n_hours": tail["hour_end_utc"].nunique(),
                "city_median_from_ug_m3": round(float(smog[in_tail].min()), 1),
                "blank_pct": round(tail[target].isna().mean() * 100, 1),
                "partial_pct": round(partial.mean() * 100, 1),
            })
    return pd.DataFrame(rows)
