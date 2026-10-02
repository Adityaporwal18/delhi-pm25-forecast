"""Stage 2 inspection, part 2: suspicious values, look-alike stations and the AQI target.

Like part 1, every function only MEASURES and returns a table of evidence;
nothing is changed. `hourly` always means the provisional label-hour table from
inspect_coverage.hourly_by_label (index: slug, hour).
"""

from itertools import combinations
from typing import Final

import numpy as np
import pandas as pd

from delhi_aqi.aqi import aqi_from_hourly
from delhi_aqi.inspect_coverage import POLLUTANTS
from delhi_aqi.series_checks import flat_runs, isolated_spikes

EARTH_RADIUS_KM: Final = 6371.0
# India Meteorological Department seasons, by calendar month.
SEASONS: Final = {
    12: "winter", 1: "winter", 2: "winter",
    3: "summer", 4: "summer", 5: "summer",
    6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon",
    10: "post-monsoon", 11: "post-monsoon",
}
SEASON_ORDER: Final = ["winter", "summer", "monsoon", "post-monsoon"]
# Air pressure at Delhi's altitude (~215 m) is about 990 hPa, which is about 740 mmHg.
HPA_RANGE: Final = (850.0, 1100.0)
MMHG_RANGE: Final = (600.0, 850.0)
MAX_LAG_H: Final = 8


def value_extremes(readings: pd.DataFrame) -> pd.DataFrame:
    """Per station and pollutant: count, min, max, readings <= 0 and readings exactly AT the max.

    Many readings sitting exactly on the maximum suggest an instrument ceiling:
    the true value was higher, but the analyser could not report it.
    """
    rows = []
    for slug, station in readings.groupby("slug", observed=True):
        for pollutant in POLLUTANTS:
            values = station[pollutant].dropna()
            if values.empty:  # this station has no analyser for this pollutant
                continue
            top = values.max()
            rows.append({
                "slug": slug, "pollutant": pollutant, "n": len(values),
                "min": values.min(), "max": top,
                "n_nonpositive": int((values <= 0).sum()),
                "n_at_max": int((values == top).sum()),
            })
    return pd.DataFrame(rows)


def repeats_within_hour(readings: pd.DataFrame) -> pd.DataFrame:
    """Per station: % of complete hours (4 PM2.5 readings) in which all four are identical.

    A high share means the '15-minute' data is really one hourly value written four times.
    """
    hour = readings["ts_label"].dt.floor("h")
    grouped = readings.groupby([readings["slug"], hour], observed=True)["pm25"]
    stats = pd.DataFrame({"n": grouped.count(), "distinct": grouped.nunique()})
    full_hours = stats[stats["n"] == 4]
    identical = (full_hours["distinct"] == 1).groupby(level="slug", observed=True).mean()
    return identical.mul(100).round(1).to_frame("all_four_identical_pct")


def hourly_checks(hourly: pd.DataFrame, flat_hours: int) -> pd.DataFrame:
    """Per station: % of hours with PM2.5 > PM10, and flat stretches of hourly PM2.5.

    PM2.5 > PM10 is physically impossible (PM10 includes all PM2.5), so it measures
    instrument error. A value repeated for `flat_hours`+ hours suggests a stuck analyser.
    """
    rows = []
    for slug, station in hourly.groupby(level="slug", observed=True):
        both = station[["pm25", "pm10"]].dropna()
        runs = flat_runs(station["pm25"], flat_hours)
        rows.append({
            "slug": slug,
            "pm25_above_pm10_pct": round(100 * float((both["pm25"] > both["pm10"]).mean()), 1),
            "flat_runs": len(runs),
            "flat_hours": int(runs.sum()),
            "longest_flat_h": int(runs.max()) if len(runs) else 0,
        })
    return pd.DataFrame(rows).set_index("slug")


def spike_table(hourly: pd.DataFrame, jump: float) -> pd.DataFrame:
    """Every one-hour PM2.5 spike that rises AND falls back by more than `jump` µg/m³."""
    parts = []
    for slug, pm25 in hourly["pm25"].groupby(level="slug", observed=True):
        flags = isolated_spikes(pm25, jump).to_numpy()
        parts.append(pd.DataFrame({
            "slug": slug,
            "hour": pm25.index.get_level_values("hour")[flags],
            "before": pm25.shift(1).to_numpy()[flags],
            "value": pm25.to_numpy()[flags],
            "after": pm25.shift(-1).to_numpy()[flags],
        }))
    return pd.concat(parts, ignore_index=True)


def bp_units(readings: pd.DataFrame) -> pd.DataFrame:
    """Per station: how often 'BP (mmHg)' is reported, its median, and which unit it looks like."""
    by_station = readings.groupby("slug", observed=True)["bp"]
    table = pd.DataFrame({
        "bp_present_pct": by_station.count() / by_station.size() * 100,
        "bp_median": by_station.median(),
    }).round(1)
    median = table["bp_median"]
    table["looks_like"] = np.select(
        [median.isna(), median.between(*HPA_RANGE), median.between(*MMHG_RANGE)],
        ["no sensor", "hPa", "mmHg"],
        default="neither (suspect)",
    )
    return table


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle ('haversine') distance between two (latitude, longitude) points."""
    lat1, lon1, lat2, lon2 = np.radians([*a, *b])
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return float(2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(h)))


def nearby_pairs(stations: pd.DataFrame, hourly: pd.DataFrame, max_km: float) -> pd.DataFrame:
    """Station pairs closer than `max_km`: near-duplicates, or genuinely different places?"""
    coords = stations.set_index("slug")[["latitude", "longitude"]]
    pm25 = hourly["pm25"].unstack("slug")
    rows = []
    for a, b in combinations(coords.index, 2):
        km = distance_km(tuple(coords.loc[a]), tuple(coords.loc[b]))
        if km > max_km:
            continue
        both = pm25[[a, b]].dropna()
        rows.append({
            "station_a": a, "station_b": b, "km": round(km, 2), "common_hours": len(both),
            "pm25_r": round(both[a].corr(both[b]), 3),
            "mean_abs_diff_pm25": round(float((both[a] - both[b]).abs().mean()), 1),
        })
    return pd.DataFrame(rows).sort_values("km", ignore_index=True)


def lag_scan(x: pd.Series, y: pd.Series, max_lag: int) -> pd.Series:
    """Correlation of x with y shifted by -max_lag..+max_lag steps.

    A peak at k means x(t) looks like y(t - k): for the same air, x's timestamps
    run k hours LATER than y's. Two stations on the same clock peak at 0.
    """
    lags = range(-max_lag, max_lag + 1)
    return pd.Series([x.corr(y.shift(lag)) for lag in lags], index=lags, name="r")


def neighbour_lags(stations: pd.DataFrame, hourly: pd.DataFrame, reference: list[str]) -> pd.DataFrame:
    """Each station's hourly PM2.5 against its nearest `reference` station, shifted -8..+8 h.

    Delhi's pollution rises and falls city-wide, so stations on the same clock line up
    best at lag 0. A station labelled in UTC, compared with an IST neighbour, would line
    up best near -5/-6 h. `reference` = stations whose clock the sun check confirmed.
    """
    coords = stations.set_index("slug")[["latitude", "longitude"]]
    pm25 = hourly["pm25"].unstack("slug")
    rows = []
    for slug in coords.index:
        km = {ref: distance_km(tuple(coords.loc[slug]), tuple(coords.loc[ref])) for ref in reference if ref != slug}
        neighbour = min(km, key=km.__getitem__)
        scan = lag_scan(pm25[slug], pm25[neighbour], MAX_LAG_H)
        rows.append({
            "slug": slug, "neighbour": neighbour, "km": round(km[neighbour], 2),
            "best_lag_h": int(scan.idxmax()), "r_lag0": round(scan.loc[0], 3),
            "r_best": round(scan.max(), 3), "r_if_utc": round(scan.loc[[-6, -5]].max(), 3),
        })
    return pd.DataFrame(rows).set_index("slug")


def station_aqi(hourly: pd.DataFrame) -> pd.DataFrame:
    """CPCB-style AQI (see delhi_aqi.aqi) for every station hour, indexed (slug, hour)."""
    parts = {
        slug: aqi_from_hourly(station.droplevel("slug"))
        for slug, station in hourly[POLLUTANTS].groupby(level="slug", observed=True)
    }
    return pd.concat(parts, names=["slug", "hour"])


def aqi_by_station(aqi: pd.DataFrame) -> pd.DataFrame:
    """Per station: % of hours with a valid AQI, % capped at 500, % decided by PM, median."""
    slug = aqi.index.get_level_values("slug")
    valid = aqi["aqi"].notna()
    n_valid = valid.groupby(slug).sum()
    table = pd.DataFrame({
        "aqi_valid_pct": valid.groupby(slug).mean() * 100,
        "pm25_subindex_valid_pct": aqi["si_pm25"].notna().groupby(slug).mean() * 100,
        "capped_at_500_pct": aqi["aqi"].ge(500).groupby(slug).sum() / n_valid * 100,
        "pm_prominent_pct": aqi["prominent"].isin(["pm25", "pm10"]).groupby(slug).sum() / n_valid * 100,
        "aqi_median": aqi["aqi"].groupby(slug).median(),
    })
    return table.round(1)


def prominent_shares(aqi: pd.DataFrame) -> pd.DataFrame:
    """% of valid AQI hours in which each pollutant decides the AQI: all year and by season."""
    valid = aqi[aqi["aqi"].notna()]
    season = valid.index.get_level_values("hour").month.map(SEASONS)
    by_season = pd.crosstab(np.asarray(season), valid["prominent"].to_numpy(), normalize="index")
    by_season = by_season.loc[[s for s in SEASON_ORDER if s in by_season.index]]
    overall = valid["prominent"].value_counts(normalize=True).rename("all year").to_frame().T
    return pd.concat([overall, by_season]).mul(100).round(1).fillna(0.0)


def outlier_rule_demo(hourly: pd.DataFrame) -> pd.Series:
    """What the textbook outlier rule (above Q3 + 1.5 x IQR) would delete from hourly PM2.5."""
    pm25 = hourly["pm25"].dropna()
    q1, q3 = pm25.quantile([0.25, 0.75])
    cutoff = q3 + 1.5 * (q3 - q1)
    flagged_months = pm25[pm25 > cutoff].index.get_level_values("hour").month
    return pd.Series({
        "cutoff_ug_m3": round(cutoff, 1),
        "hours_flagged_pct": round(100 * len(flagged_months) / len(pm25), 1),
        "flagged_in_oct_to_jan_pct": round(100 * float(np.isin(flagged_months, [10, 11, 12, 1]).mean()), 1),
    })


def worst_days(hourly: pd.DataFrame, n: int) -> pd.DataFrame:
    """The n days whose worst hour had the highest city-wide median PM2.5 (label time)."""
    city = hourly["pm25"].groupby(level="hour").median().dropna()
    daily = city.groupby(city.index.floor("D").rename("day"))
    table = pd.DataFrame({
        "worst_hour": daily.idxmax(),
        "worst_hour_city_median": daily.max().round(1),
        "day_mean_city_median": daily.mean().round(1),
    })
    return table.nlargest(n, "worst_hour_city_median")
