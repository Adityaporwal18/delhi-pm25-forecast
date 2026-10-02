"""Stage 2 cleaning, part 2: station selection (D3), spikes (D4.1) and frozen runs (D4.2).

The rules blank values (set them to NaN); they never delete rows, so the hourly grid
stays complete. Each rule also returns a log of exactly what it touched.
"""

from collections.abc import Mapping
from typing import Final

import numpy as np
import pandas as pd

from delhi_aqi.clean import HOUR
from delhi_aqi.config import FlatRule, PipelineConfig, SpikeRule
from delhi_aqi.series_checks import flat_mask, isolated_spikes

SLOTS_PER_HOUR: Final = 4
DELHI: Final = "Asia/Kolkata"
TAIL_SHARES: Final = (0.10, 0.01, 0.001)
SPIKE_LOG_COLUMNS: Final = ["slug", "hour_end_utc", "pollutant", "before", "value", "after", "city_median", "action"]
RUN_LOG_COLUMNS: Final = ["slug", "pollutant", "first_hour_end_utc", "last_hour_end_utc", "hours", "value"]


def station_selection(hourly: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """D3 (b): keep a station only if it reported the target in at least
    `min_train_coverage_pct` % of its 15-min slots during TRAINING.

    Coverage counts raw readings (n_<target> of 4 per hour), so it does not depend on any
    cleaning threshold. Test-period and per-year coverage are shown for information only.
    """
    pct = hourly[f"n_{config.target}"] / SLOTS_PER_HOUR * 100
    period = pd.Series(np.where(hourly["hour_end_utc"] <= config.test_start, "train", "test"),
                       index=hourly.index, name="period")
    delhi_year = (hourly["hour_end_utc"] - HOUR).dt.tz_convert(DELHI).dt.year.rename("year")
    by_period = pct.groupby([hourly["slug"], period], observed=True).mean().unstack()
    by_year = pct.groupby([hourly["slug"], delhi_year], observed=True).mean().unstack()
    table = pd.concat([by_period.reindex(columns=["train", "test"]).add_suffix("_readings_pct"),
                       by_year.add_prefix("readings_pct_")], axis=1)
    kept = table["train_readings_pct"] >= config.min_train_coverage_pct
    return table.round(1).assign(kept=kept)


def remove_spikes(hourly: pd.DataFrame, rules: Mapping[str, SpikeRule]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """D4.1 (c): blank a one-hour spike only when the rest of the city is calm that hour.

    Spike = more than `jump_ug_m3` above BOTH neighbouring hours. Instrument glitches look
    like that, but so does a real Diwali-night peak; the city median tells them apart.
    Returns the cleaned table and a log of every spike found, removed or kept.
    """
    cleaned = hourly.copy()
    logs = []
    for pollutant, rule in rules.items():
        values = hourly[pollutant]
        by_station = values.groupby(hourly["slug"], observed=True)
        spike = by_station.transform(isolated_spikes, jump=rule.jump_ug_m3)
        city = values.groupby(hourly["hour_end_utc"]).transform("median")
        remove = spike & (city < rule.calm_city_median_ug_m3)
        log = pd.DataFrame({
            "slug": hourly["slug"], "hour_end_utc": hourly["hour_end_utc"], "pollutant": pollutant,
            "before": by_station.shift(1), "value": values, "after": by_station.shift(-1),
            "city_median": city, "action": np.where(remove, "removed", "kept: city polluted"),
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
    """
    cleaned = hourly.copy()
    slug = hourly["slug"]
    logs = []
    for pollutant in rule.pollutants:
        values = hourly[pollutant]
        frozen = values.groupby(slug, observed=True).transform(flat_mask, min_hours=rule.min_hours)
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
    in_train = hourly["hour_end_utc"] <= config.test_start
    rows = []
    for period, part in (("train", hourly[in_train]), ("test", hourly[~in_train])):
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
