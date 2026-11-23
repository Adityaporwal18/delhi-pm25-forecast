"""Live forecasts, stage D: from the latest live features to the file the site reads.

Publishing is all or nothing. problems_with lists every reason to distrust a refresh: a forecast hour that is old
or in the future, or a short history (too few stations reporting stops earlier, in
live.latest_hour). With any problem, publish_if_sound leaves the published
file untouched, because a slightly stale forecast is better than a broken page. The file records
when it was made ("generated_at_utc", the site's "last updated") and the hour the forecast
starts from ("issued_utc").
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pandas as pd

from delhi_pm25.model import order_band

__all__ = ["STALE_AFTER", "Freshness", "already_published", "forecast_document", "order_band", "previous_issue", "problems_with", "publish_if_sound", "published_age"]

MIN_HISTORY_SHARE: Final = 2 / 3
MAX_AGE: Final = pd.Timedelta(hours=12)
FUTURE_SLACK: Final = pd.Timedelta(hours=1)
# The website warns when the forecast is older than this (STALE_AFTER_HOURS in frontend/src/live.ts;
# tests/test_live_forecast.py keeps the two equal).
STALE_AFTER: Final = pd.Timedelta(hours=12)


@dataclass(frozen=True, slots=True)
class Freshness:
    """When the refresh runs, and the forecast hour of the file already published (None if none)."""

    now: pd.Timestamp
    previous_issue: pd.Timestamp | None


def already_published(features: pd.DataFrame, freshness: Freshness) -> bool:
    """True when the published file already starts at this forecast hour or later: there is
    nothing to do (two triggers can start refreshes close together), and that is not a failure."""
    previous = freshness.previous_issue
    return previous is not None and features["hour_end_utc"].max() <= previous


def problems_with(features: pd.DataFrame, target: str, freshness: Freshness) -> list[str]:
    """Every reason not to publish these live features; an empty list means publish."""
    issued = features["hour_end_utc"].max()
    history = features[f"{target}_mean_168h"].notna().mean()
    checks = [
        (history < MIN_HISTORY_SHARE,
         f"only {history:.0%} of stations have a 7-day history (need {MIN_HISTORY_SHARE:.0%}): the fetch looks short"),
        (freshness.now - issued > MAX_AGE, f"the forecast hour {issued} is more than {MAX_AGE} old"),
        (issued > freshness.now + FUTURE_SLACK, f"the forecast hour {issued} is in the future: the clock or time zone is wrong"),
    ]
    return [message for failed, message in checks if failed]


def _number(value: float) -> float | None:
    return None if pd.isna(value) else round(float(value), 1)


def forecast_document(table: pd.DataFrame, issued: pd.Timestamp, generated: pd.Timestamp) -> dict[str, object]:
    """Rows (slug, horizon_h, valid_utc, p10, p50, p90, measured) -> the JSON the site reads.
    Horizon 0 carries the value measured now; blank values become null."""
    rows = [{"slug": row.slug, "horizon_h": int(row.horizon_h), "valid_utc": row.valid_utc.isoformat(),
             "p10": _number(row.p10), "p50": _number(row.p50), "p90": _number(row.p90), "measured": _number(row.measured)}
            for row in table.itertuples()]
    return {"generated_at_utc": generated.isoformat(timespec="seconds"), "issued_utc": issued.isoformat(), "rows": rows}


def publish_if_sound(document: dict[str, object], problems: list[str], path: Path) -> bool:
    """Write the document only if there were no problems; otherwise leave the old file as it is."""
    if problems:
        return False
    part = path.with_suffix(".part")
    part.write_text(json.dumps(document, indent=1) + "\n")
    part.replace(path)
    return True


def previous_issue(path: Path) -> pd.Timestamp | None:
    """The forecast hour of the published file; None if there is none (or it cannot be read)."""
    try:
        issued = json.loads(path.read_text()).get("issued_utc")
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return None if issued is None else pd.Timestamp(issued)


def published_age(path: Path, now: pd.Timestamp) -> pd.Timedelta | None:
    """How long ago the published file was made; None if there is none (or it cannot be read)."""
    try:
        made = json.loads(path.read_text()).get("generated_at_utc")
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return None if made is None else now - pd.Timestamp(made)
