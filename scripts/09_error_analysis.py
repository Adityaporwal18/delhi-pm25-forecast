"""Stage 6: where the model is weakest, on the test year (2025).

Diagnosis only: nothing here changes the model (model choices are made on the 2024 validation
year). Every table compares persistence, climatology and the model on the same rows and gives
MAE (lower is better) and bias (average of forecast minus truth; negative = too low).

Slices:
  tails     the smoggiest 10% and 1% of hours, chosen two ways: by how smoggy the target hour
            turned out (favours forecasts that never pull back towards typical values), and by
            the city median known when the forecast is made (fair to every forecast)
  season    winter (Dec-Feb), summer (Mar-May), monsoon (Jun-Sep), post-monsoon (Oct-Nov)
  change    how far PM2.5 actually moved in the 48 hours: steady vs sharp rises and falls
  station   each of the 37 stations
  Diwali    the Diwali 2025 window: one night, so an anecdote (n = 1), not evidence

Outputs: reports/stage6/{tails,by_season,by_change,by_station,diwali_2025}.csv and six charts
Usage:   .venv/bin/python scripts/09_error_analysis.py
"""

import sys
import textwrap
from typing import Final

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 (the backend must be chosen before this import)
import numpy as np
import pandas as pd

from delhi_pm25.baselines import climatology, climatology_table
from delhi_pm25.clean import HOUR
from delhi_pm25.config import ConfigError, PipelineConfig, load_config
from delhi_pm25.error_analysis import change_class, errors_by, issue_time_tail, outcome_tail, target_season
from delhi_pm25.features import DELHI
from delhi_pm25.guards import InputsOutOfDate, check_up_to_date
from delhi_pm25.model import load_model, predict
from delhi_pm25.model_settings import load_model_settings
from delhi_pm25.paths import MODELS_DIR, PIPELINE_TOML, PROCESSED_DIR, REPORTS_DIR
from delhi_pm25.split import EmbargoError, folds, split

FEATURES_PARQUET: Final = PROCESSED_DIR / "features.parquet"
MODEL_FILE: Final = MODELS_DIR / "pm25_48h.txt"
OUT: Final = REPORTS_DIR / "stage6"
MODEL_COMMAND: Final = ".venv/bin/python scripts/08_model.py"
METHODS: Final = ("persistence", "climatology", "model")
COLORS: Final = ["#9e9e9e", "#4c72b0", "#dd8452"]
TAIL_SHARES: Final = (0.10, 0.01)
MAE_LABEL: Final = "MAE, µg/m³ (lower is better)"


def forecasts_for_test_year(config: PipelineConfig) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """The test fold's rows and the three forecasts for them (the saved final model). Rows whose
    target hour falls after the end of the data (the last 48 forecast hours) are left out: their
    target can never be measured, so they would only inflate the share of blank targets."""
    check_up_to_date(MODEL_FILE, [FEATURES_PARQUET, PIPELINE_TOML], MODEL_COMMAND)
    features = pd.read_parquet(FEATURES_PARQUET)
    train, scored = split(features, folds(config)[1], config.features.horizon_hours)
    inside_data = scored["target_hour_end_utc"] <= features["hour_end_utc"].max()
    rows = scored[inside_data].reset_index(drop=True)
    model = load_model(MODEL_FILE, load_model_settings(PIPELINE_TOML).objective)
    return rows, {
        "persistence": rows[f"{config.target}_lag_0h"],
        "climatology": climatology(rows, climatology_table(train, config.baselines)),
        "model": predict(model, rows),
    }


def tails(rows: pd.DataFrame, forecasts: dict[str, pd.Series], city_now: str) -> pd.DataFrame:
    masks = {"all hours": pd.Series(True, index=rows.index)}
    for share in TAIL_SHARES:
        masks[f"smoggiest {share:.0%}, by outcome"] = outcome_tail(rows, share)
        masks[f"smoggiest {share:.0%}, known at forecast time"] = issue_time_tail(rows, share, city_now)
    parts = []
    for label, mask in masks.items():
        table = errors_by(rows, forecasts, pd.Series(label, index=rows.index, name="hours").where(mask))
        parts.append(table.assign(target_blank_pct=round(rows.loc[mask, "target"].isna().mean() * 100, 1)))
    return pd.concat(parts)


def diwali(rows: pd.DataFrame, forecasts: dict[str, pd.Series], season: pd.Series) -> pd.DataFrame:
    inside = rows["target_in_diwali_window"] == 1
    other = np.where(season == "post-monsoon", "rest of Oct-Nov 2025", None)
    label = np.where(inside, "Diwali 2025 window (one night: n = 1)", other)
    return errors_by(rows, forecasts, pd.Series(label, index=rows.index, name="hours"))


def stations(rows: pd.DataFrame, forecasts: dict[str, pd.Series]) -> pd.DataFrame:
    table = errors_by(rows, forecasts, rows["slug"].astype(str).rename("station"))
    table["model_gain_vs_climatology_pct"] = ((1 - table["model_mae"] / table["climatology_mae"]) * 100).round(1)
    return table.sort_values("model_mae", ascending=False)


def save(fig: plt.Figure, name: str) -> None:
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=120)
    plt.close(fig)


def grouped_bars(table: pd.DataFrame, title: str, name: str) -> None:
    data = table[[f"{method}_mae" for method in METHODS]].set_axis(list(METHODS), axis=1)
    data.index = [textwrap.fill(str(label), 16) for label in data.index]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    data.plot.bar(ax=ax, rot=0, color=COLORS, width=0.8)
    for bars in ax.containers:
        ax.bar_label(bars, fmt="%.0f", fontsize=7)
    ax.set(title=title, ylabel=MAE_LABEL, xlabel="")
    save(fig, name)


def station_bars(table: pd.DataFrame) -> None:
    order = table.sort_values("model_mae")
    y = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(8, 10))
    ax.barh(y - 0.2, order["climatology_mae"], height=0.4, color=COLORS[1], label="climatology")
    ax.barh(y + 0.2, order["model_mae"], height=0.4, color=COLORS[2], label="model")
    ax.set_yticks(y, order.index, fontsize=7)
    ax.set(title="Test 2025: MAE by station", xlabel=MAE_LABEL)
    ax.legend(loc="lower right")
    save(fig, "by_station.png")


def diwali_lines(rows: pd.DataFrame, forecasts: dict[str, pd.Series], config: PipelineConfig) -> None:
    window = config.features.diwali
    day = next(date for date in window.dates if date.year == 2025)
    opens = pd.Timestamp(day.isoformat()) + window.start_hour_ist * HOUR
    closes = opens + window.hours * HOUR
    start = (rows["target_hour_end_utc"] - HOUR).dt.tz_convert(DELHI).dt.tz_localize(None)
    near = (start >= opens - 72 * HOUR) & (start < closes + 72 * HOUR)
    city = pd.concat({"measured": rows["target"], **forecasts}, axis=1)[near].groupby(start[near]).median()
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.axvspan(opens, closes, color="#f2d0a4", alpha=0.6, label="Diwali window")
    ax.plot(city.index, city["measured"], color="black", linewidth=1.8, label="measured (city median)")
    for method, color in zip(METHODS, COLORS, strict=True):
        ax.plot(city.index, city[method], color=color, linewidth=1.2, label=f"{method} (made 48 h earlier)")
    ax.set(title="Diwali 2025, one night (n = 1): city median PM2.5", ylabel="PM2.5, µg/m³",
           xlabel="Delhi time (start of hour)")
    ax.legend(fontsize=8)
    fig.autofmt_xdate()
    save(fig, "diwali_2025.png")


def forecast_vs_measured(rows: pd.DataFrame, forecasts: dict[str, pd.Series]) -> None:
    measured = rows["target"].notna()
    fig, ax = plt.subplots(figsize=(6, 5.2))
    cells = ax.hexbin(rows.loc[measured, "target"], forecasts["model"][measured], gridsize=60, bins="log",
                      extent=(0, 800, 0, 800), mincnt=1, cmap="viridis")
    ax.plot([0, 800], [0, 800], color="red", linewidth=1, label="perfect forecast")
    ax.set(title="Test 2025: model forecast vs measured PM2.5",
           xlabel="measured PM2.5 48 h later (µg/m³)", ylabel="model forecast (µg/m³)")
    ax.legend(loc="upper left")
    fig.colorbar(cells, label="station-hours (log scale)")
    save(fig, "forecast_vs_measured.png")


def main() -> int:
    try:
        config = load_config(PIPELINE_TOML)
        rows, forecasts = forecasts_for_test_year(config)
    except (ConfigError, InputsOutOfDate, EmbargoError) as err:
        print(f"STOPPED: {err}", file=sys.stderr)
        return 1
    season = target_season(rows)
    tables = {
        "tails": tails(rows, forecasts, f"city_{config.target}_median"),
        "by_season": errors_by(rows, forecasts, season),
        "by_change": errors_by(rows, forecasts, change_class(rows, f"{config.target}_lag_0h")),
        "by_station": stations(rows, forecasts),
        "diwali_2025": diwali(rows, forecasts, season),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(OUT / f"{name}.csv")
    grouped_bars(tables["tails"], "Test 2025: smoggiest hours, picked by outcome and by what is known in advance", "tails.png")
    grouped_bars(tables["by_season"], "Test 2025: MAE by season of the target hour", "by_season.png")
    grouped_bars(tables["by_change"], "Test 2025: MAE by how far PM2.5 actually moved in 48 hours", "by_change.png")
    station_bars(tables["by_station"])
    diwali_lines(rows, forecasts, config)
    forecast_vs_measured(rows, forecasts)
    pd.set_option("display.width", 220)
    for name, table in tables.items():
        shown = pd.concat([table.head(4), table.tail(4)]) if name == "by_station" else table
        print(f"\n{name}:\n{shown.to_string()}")
    print(f"\nWrote {len(tables)} tables and 6 charts to reports/stage6/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
