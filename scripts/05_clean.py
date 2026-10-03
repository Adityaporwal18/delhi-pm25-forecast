"""Stage 2, step 3: clean the raw readings into ONE hourly table, applying the decisions
recorded in config/pipeline.toml, in this order:

  D1   timestamp labels are Delhi time marked '+0000' -> converted to true UTC
  D2   an hour's value = mean of the 15-min readings present (at least `min_readings`)
  D6   one row per station per hour, checked: no hour missing, repeated or out of order
  D3   keep only stations that reported the target in >= 75% of their TRAINING slots
  D4.1 blank a one-hour spike, but only while the rest of the city is calm
  D4.2 blank values frozen unchanged for 6 hours or more

The rules only BLANK values. No rows are deleted and no gaps are filled (D3 a): a model
must never learn from, or be scored on, numbers we invented.

Each row is stamped with the END of its hour (`hour_end_utc`): the moment the hourly value
is complete. Stage 3 features may only use hours that have ended -- that is what keeps
them free of leakage. `n_<pollutant>` counts the raw 15-min readings behind each hour (kept
even when a rule blanks the value); `<pollutant>_at_ceiling` marks hours with a reading at
the analysers' 1000 ug/m3 limit.

Outputs:
  data/interim/hourly_clean.parquet          cleaned hourly table (kept stations only)
  reports/stage2/cleaning_summary.csv        rows and values left after each step, per pollutant
  reports/stage2/station_selection.csv       coverage per station; which were kept
  reports/stage2/removed_spikes.csv          every spike found, removed or kept
  reports/stage2/removed_flat_runs.csv       every frozen run that was blanked
  reports/stage2/missing_in_worst_hours.csv  blank target share: all hours vs smoggiest 10%, 1%, 0.1%

Usage:
  .venv/bin/python scripts/05_clean.py
"""

import sys
from typing import Final

import pandas as pd

from delhi_pm25.clean import GridError, check_complete_grid, to_hourly
from delhi_pm25.clean_rules import blank_flat_runs, missing_in_worst_hours, remove_spikes, station_selection
from delhi_pm25.config import ConfigError, PipelineConfig, load_config
from delhi_pm25.guards import InputsOutOfDate, check_up_to_date, check_weather_covers
from delhi_pm25.paths import INTERIM_DIR, PIPELINE_TOML, RAW_WEATHER_DIR, REPORTS_DIR, STATIONS_CSV
from delhi_pm25.raw_cpcb import POLLUTANTS, station_files

RAW_PARQUET: Final = INTERIM_DIR / "cpcb_15min_raw.parquet"
WEATHER_MANIFEST: Final = RAW_WEATHER_DIR / "manifest.csv"
OUT_PARQUET: Final = INTERIM_DIR / "hourly_clean.parquet"
OUT: Final = REPORTS_DIR / "stage2"
STACK_COMMAND: Final = ".venv/bin/python scripts/03_stack_raw.py"
WEATHER_COMMAND: Final = ".venv/bin/python scripts/02_fetch_weather.py"


def load_inputs() -> tuple[PipelineConfig, pd.DataFrame]:
    """Settings and raw readings, after checking that nothing upstream is out of date."""
    config = load_config(PIPELINE_TOML)
    check_up_to_date(RAW_PARQUET, [*station_files(), STATIONS_CSV], STACK_COMMAND)
    check_up_to_date(WEATHER_MANIFEST, [], WEATHER_COMMAND)
    readings = pd.read_parquet(RAW_PARQUET)
    labels = readings["ts_label"]
    check_weather_covers(pd.read_csv(WEATHER_MANIFEST), labels.min().date(), labels.max().date())
    return config, readings


def print_summary(config: PipelineConfig, hourly: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> None:
    ends = hourly["hour_end_utc"]
    print(f"D1/D2/D6 hourly grid: {hourly['slug'].nunique()} stations x {ends.nunique():,} hours "
          f"= {len(hourly):,} rows, hours ending {ends.min()} -> {ends.max()}")
    selection = tables["station_selection"]
    dropped = selection.loc[~selection["kept"], "train_readings_pct"].to_dict()
    print(f"D3   stations kept: {int(selection['kept'].sum())} of {len(selection)}; dropped (training "
          f"{config.target} coverage < {config.min_train_coverage_pct:g}%): {dropped}")
    print("D4.1 spikes found:", tables["removed_spikes"].groupby(["pollutant", "action"]).size().to_dict())
    runs = tables["removed_flat_runs"].groupby("pollutant")["hours"].agg(["size", "sum"])
    print("D4.2 frozen runs blanked:", {p: f"{n} runs, {h:,} hours" for p, (n, h) in runs.iterrows()})
    print(f"\nRows and {config.target} values left after each step:")
    print(tables["cleaning_summary"].loc[["rows", config.target]].T.to_string())
    print(f"\nBlank {config.target} values, all hours vs the smoggiest hours (city median >= cutoff):")
    print(tables["missing_in_worst_hours"].to_string(index=False))


def main() -> int:
    try:
        config, readings = load_inputs()
        hourly = to_hourly(readings, config.hourly, config.ceiling)
        check_complete_grid(hourly)
    except (ConfigError, InputsOutOfDate, GridError) as err:
        print(f"STOPPED: {err}", file=sys.stderr)
        return 1

    selection = station_selection(hourly, config)
    kept = hourly[hourly["slug"].isin(selection.index[selection["kept"].to_numpy()])].reset_index(drop=True)
    kept["slug"] = kept["slug"].cat.remove_unused_categories()
    despiked, spikes = remove_spikes(kept, config.spikes)
    cleaned, runs = blank_flat_runs(despiked, config.flat_runs)

    steps = {"raw_15min_readings": readings, "hourly_values": hourly, "hourly_values_kept_stations": kept,
             "after_spike_rule": despiked, "after_frozen_rule": cleaned}
    summary = pd.DataFrame({step: frame[POLLUTANTS].notna().sum() for step, frame in steps.items()})
    summary.loc["rows"] = [len(frame) for frame in steps.values()]
    tables = {
        "cleaning_summary": summary.rename_axis("pollutant"),
        "station_selection": selection,
        "removed_spikes": spikes,
        "removed_flat_runs": runs,
        "missing_in_worst_hours": missing_in_worst_hours(cleaned, config),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    cleaned.to_parquet(OUT_PARQUET, index=False)
    for name, table in tables.items():
        table.to_csv(OUT / f"{name}.csv", index=not isinstance(table.index, pd.RangeIndex))
    print_summary(config, hourly, tables)
    print(f"\nWrote {OUT_PARQUET.relative_to(OUT_PARQUET.parents[2])} and {len(tables)} tables "
          f"in {OUT.relative_to(OUT.parents[1])}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
