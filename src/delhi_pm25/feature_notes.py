"""A plain-language note for every feature column. scripts/06_features.py writes them to
reports/stage3/feature_list.csv; a feature without a note stops the run."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from delhi_pm25.raw_cpcb import POLLUTANTS


class UndescribedFeatureError(Exception):
    """A feature column has no plain-language note."""


@dataclass(frozen=True, slots=True)
class _Note:
    pattern: str
    group: str
    why: str


_NOTES: tuple[_Note, ...] = (
    _Note("slug", "station", "Which station: local sources make some stations run higher than others."),
    _Note("{t}_lag_0h", "A own history", "The value now; on its own this is the persistence forecast."),
    _Note(r"{t}_lag_\d+h", "A own history", "The value k hours ago; 24 h and 48 h share the target's clock time."),
    _Note(r"{t}_mean_\d+h", "B rolling means", "Average of the last N hours: the level of the current episode."),
    _Note("city_{t}_median", "C city-wide",
          "Median over the stations reporting now: smog is regional, and this works when this analyser is down."),
    _Note("city_{t}_median_mean_24h", "C city-wide", "The city median averaged over the last 24 hours."),
    _Note("city_{t}_n_stations", "C city-wide",
          "How many stations the city median rests on; fewer in heavy smog, when the worst readings go missing."),
    _Note("{t}_minus_city", "C city-wide", "This station's excess over the city now; local excess tends to persist."),
    _Note("target_hour_(sin|cos)", "D calendar", "Clock time of the target hour on a circle, so 23:00 and 00:00 are neighbours."),
    _Note("target_doy_(sin|cos)", "D calendar", "Day of the year of the target hour on a circle: the season."),
    _Note("target_in_diwali_window", "E events",
          "Target hour between 18:00 on Diwali and 12:00 the next day (Delhi time); dates in config/pipeline.toml."),
    _Note("target_in_stubble_season", "E events",
          "Target day inside the crop-burning season set in config/pipeline.toml; kept only if it helps."),
    _Note("({p})_now", "G other pollutants", "Another pollutant now: a hint at the source (dust, traffic, burning)."),
    _Note("n_{t}_now", "G data quality", "How many of the 4 fifteen-minute readings made the current hour."),
    _Note("hours_since_{t}", "G data quality", "Hours since this station last had a value."),
    _Note("{t}_hit_limit_24h", "G data quality", "1 if the analyser hit its 1000 µg/m³ limit in the last 24 hours."),
    _Note("wx_temperature", "F weather now", "Air temperature: cold nights go with trapped smog."),
    _Note("wx_rh", "F weather now", "Relative humidity."),
    _Note("wx_dew_point", "F weather now", "Dew point: moisture in the air, linked to fog and particle growth."),
    _Note("wx_pressure", "F weather now", "Surface pressure: high pressure goes with still air."),
    _Note("wx_cloud", "F weather now", "Cloud cover."),
    _Note("wx_shortwave", "F weather now", "Sunshine in the last hour: it heats the ground and stirs the air."),
    _Note("wx_wind_speed", "F weather now", "Wind speed: wind carries pollution away."),
    _Note("wx_wind_(u|v)", "F weather now", "Wind towards the east (u) and the north (v): also where the air comes from."),
    _Note("wx_wind_speed_mean_24h", "F weather now", "Average wind speed over the last 24 hours."),
    _Note("wx_rain_sum_24h", "F weather now", "Rain in the last 24 hours: rain washes particles out."),
    _Note("wx_blh", "F weather now",
          "Boundary-layer height (ERA5): the depth of air pollution mixes into; blank January-June 2024."),
    _Note("wx_blh_min_24h", "F weather now", "Lowest boundary-layer height in the last 24 hours."),
    _Note("wx_ventilation", "F weather now", "Boundary-layer height x wind speed: how fast the air over the city is replaced."),
)


def feature_notes(columns: Sequence[str], target: str) -> pd.DataFrame:
    """One row per feature column: feature, group, why. Raises if a column has no note."""
    names = {"t": re.escape(target), "p": "|".join(POLLUTANTS)}
    rows, undescribed = [], []
    for column in columns:
        note = next((n for n in _NOTES if re.fullmatch(n.pattern.format(**names), column)), None)
        if note is None:
            undescribed.append(column)
        else:
            rows.append({"feature": column, "group": note.group, "why": note.why})
    if undescribed:
        raise UndescribedFeatureError(
            f"No plain-language note for {undescribed}: add one in src/delhi_pm25/feature_notes.py"
        )
    return pd.DataFrame(rows)
