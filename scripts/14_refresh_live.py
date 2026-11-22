"""Live forecasts, stage D: refresh the forecast the site shows. One script, meant to run every 6 hours.

  fetch      the last 10 days of OpenAQ readings and Open-Meteo weather (src/delhi_pm25/live_fetch.py)
  features   the training functions (live.live_features), for the latest hour most stations reported
  models     the 24 live models in serving/models (median and 80% band at 6, 12, ..., 48 hours),
             after checking that the settings still match the spec they were trained with
  output     serving/live_forecast.json; "generated_at_utc" is the site's "last updated"

It fails safely. If the fetch fails, or problems_with finds the data suspicious (too few stations,
an old or future forecast hour, nothing newer than the published file, a short history), the
published file is left untouched and the reason is printed; the exit code is then 1, so a
scheduled run shows as failed while the site keeps its last good forecast.

Usage:  .venv/bin/python scripts/14_refresh_live.py   (needs OPENAQ_API_KEY; about 8 minutes)
"""

import os
import sys
from dataclasses import asdict
from typing import Final

import numpy as np
import pandas as pd

from delhi_pm25.clean import HOUR, IST_OFFSET, GridError
from delhi_pm25.config import ConfigError, load_config
from delhi_pm25.features import FeatureError, horizon_view
from delhi_pm25.guards import InputsOutOfDate
from delhi_pm25.live import live_features
from delhi_pm25.live_fetch import fetch_live
from delhi_pm25.live_forecast import Freshness, forecast_document, previous_issue, problems_with, publish_if_sound
from delhi_pm25.live_inputs import LiveInputError
from delhi_pm25.model import band_objectives, load_model, order_band, predict
from delhi_pm25.model_settings import load_model_settings, load_serving_settings
from delhi_pm25.model_spec import ModelSpec, SpecMismatch, SpecParts, assert_same_except_window, build_spec, spec_from_json
from delhi_pm25.openaq import OpenAQFormatError
from delhi_pm25.paths import PIPELINE_TOML, REPORTS_DIR, SERVING_DIR
from delhi_pm25.raw_cpcb import RawFormatError

OUT: Final = SERVING_DIR / "live_forecast.json"
MODELS: Final = SERVING_DIR / "models"
LIVE_SPEC: Final = REPORTS_DIR / "live" / "model_spec_live.json"
FAILURES: Final = (ConfigError, SpecMismatch, LiveInputError, OpenAQFormatError, RawFormatError, GridError,
                   InputsOutOfDate, FeatureError, FileNotFoundError)


def checked_setup() -> tuple[SpecParts, ModelSpec]:
    """The settings, after confirming they still match the spec the live models were trained with."""
    live = spec_from_json(LIVE_SPEC.read_text())
    parts = SpecParts(load_config(PIPELINE_TOML), load_model_settings(PIPELINE_TOML), load_serving_settings(PIPELINE_TOML), live.columns)
    assert_same_except_window(live, build_spec(live.window, live.trees, parts))
    return parts, live


def forecasts(features: pd.DataFrame, parts: SpecParts) -> pd.DataFrame:
    """Horizon 0 (the value measured now), then the median and band for every horizon."""
    slugs, issued = features["slug"].astype(str), features["hour_end_utc"]
    now = features[f"{parts.config.target}_lag_0h"]
    tables = [pd.DataFrame({"slug": slugs, "horizon_h": 0, "valid_utc": issued, "p10": np.nan, "p50": np.nan, "p90": np.nan, "measured": now})]
    for hours in parts.serving.horizons_hours:
        view = horizon_view(features, hours, parts.config)
        band = {name: predict(load_model(MODELS / f"h{hours:02d}_{name}.txt", objective), view)
                for name, objective in band_objectives(parts.model, parts.serving).items()}
        low, high = order_band(band["p10"], band["p50"], band["p90"])
        tables.append(pd.DataFrame({"slug": slugs, "horizon_h": hours, "valid_utc": issued + hours * HOUR,
                                    "p10": low, "p50": band["p50"], "p90": high, "measured": np.nan}))
    return pd.concat(tables, ignore_index=True).sort_values(["slug", "horizon_h"], ignore_index=True)


def kept(reason: str) -> int:
    print(f"KEPT the published forecast: {reason}", file=sys.stderr)
    return 1


def main() -> int:
    key = os.environ.get("OPENAQ_API_KEY", "")
    if not key:
        return kept("OPENAQ_API_KEY is not set")
    now = pd.Timestamp.now(tz="UTC")
    try:
        parts, live = checked_setup()
        readings, weather = fetch_live(key, now)
        features = live_features(readings, weather, parts.config)
    except FAILURES as err:
        return kept(f"{type(err).__name__}: {err}")
    problems = problems_with(features, parts.config.target, Freshness(now, previous_issue(OUT)))
    if problems:
        return kept("; ".join(problems))
    issued = features["hour_end_utc"].iloc[0]
    reporting = int(features[f"{parts.config.target}_lag_0h"].notna().sum())
    table = forecasts(features, parts)
    document = forecast_document(table, issued, now) | {
        "stations_reporting": reporting, "stations": len(features), "training_window": asdict(live.window)}
    publish_if_sound(document, [], OUT)
    print(f"Published {OUT.relative_to(SERVING_DIR.parent)}: forecast from {(issued + IST_OFFSET).tz_localize(None):%d %b %H:%M} "
          f"Delhi time, {reporting} of {len(features)} stations reporting, {len(table)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
