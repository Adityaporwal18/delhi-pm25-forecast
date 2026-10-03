"""Stage 3: build the feature table the model learns from.

One row per station per hour t, where t is the END of the latest complete hour. Each row
holds what is known at t (the station's own readings, the rest of the city, the weather)
plus the calendar of the hour being forecast. The target is the station's value of the
target pollutant (PM2.5) for the hour ending t + 48 h. It stays blank when that hour was
not measured, and it is never filled.

All settings live in [features] of config/pipeline.toml. tests/test_leakage.py checks
every feature column automatically: changing any input after t must not change a feature
at t.

The evidence tables use TRAINING rows only (target hour on or before the test start), so
2025 is never looked at while choosing features.

OUTPUTS
  data/processed/features.parquet            the feature table
  reports/stage3/feature_list.csv            every feature, its group and a one-line reason
  reports/stage3/feature_correlations.csv    Spearman rho of each feature with the target
  reports/stage3/city_median_stations.csv    stations behind the city median, all vs smoggiest hours

USAGE
  .venv/bin/python scripts/06_features.py
"""

import sys
from typing import Final

import pandas as pd

from delhi_pm25.clean import GridError, check_complete_grid
from delhi_pm25.clean_rules import TAIL_SHARES
from delhi_pm25.config import ConfigError, PipelineConfig, load_config
from delhi_pm25.feature_notes import UndescribedFeatureError, feature_notes
from delhi_pm25.features import NON_FEATURE_COLUMNS, FeatureError, build_features
from delhi_pm25.guards import InputsOutOfDate, check_up_to_date
from delhi_pm25.paths import INTERIM_DIR, PIPELINE_TOML, PROCESSED_DIR, PROJECT_ROOT, REPORTS_DIR
from delhi_pm25.weather import load_station_weather

CLEAN_PARQUET: Final = INTERIM_DIR / "hourly_clean.parquet"
RAW_PARQUET: Final = INTERIM_DIR / "cpcb_15min_raw.parquet"
OUT_PARQUET: Final = PROCESSED_DIR / "features.parquet"
OUT: Final = REPORTS_DIR / "stage3"
CLEAN_COMMAND: Final = ".venv/bin/python scripts/05_clean.py"
SUMMARY_GROUPS: Final = ("A own history", "B rolling means", "C city-wide")


def load_inputs() -> tuple[PipelineConfig, pd.DataFrame, pd.DataFrame]:
    """Settings, the cleaned hourly table (checked complete) and the weather for its stations."""
    config = load_config(PIPELINE_TOML)
    check_up_to_date(CLEAN_PARQUET, [RAW_PARQUET, PIPELINE_TOML], CLEAN_COMMAND)
    hourly = pd.read_parquet(CLEAN_PARQUET)
    check_complete_grid(hourly)
    weather = load_station_weather(hourly["slug"].cat.categories.tolist())
    return config, hourly, weather


def training_rows(features: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """Rows whose target hour lies in the training period: the only rows evidence may use."""
    return features[features["target_hour_end_utc"] <= config.test_start]


def correlations(features: pd.DataFrame, columns: list[str], config: PipelineConfig) -> pd.DataFrame:
    """Spearman rho of each numeric feature with the target, on training rows.

    Spearman = the correlation of the RANKS: 1 when a higher feature value always goes with
    a higher target, 0 when the order says nothing. Computed as the plain correlation of
    ranks over rows where both values exist (pandas would need scipy for this).
    """
    train = training_rows(features, config)
    target = train["target"]
    numeric = [c for c in columns if not isinstance(train[c].dtype, pd.CategoricalDtype)]
    rows = []
    for column in numeric:
        both = train[column].notna() & target.notna()
        rho = train.loc[both, column].rank().corr(target[both].rank())
        rows.append({"feature": column, "rho": round(rho, 3), "n": int(both.sum())})
    return pd.DataFrame(rows)


def city_median_support(features: pd.DataFrame, config: PipelineConfig) -> pd.DataFrame:
    """How many stations stand behind the city median: all training hours vs the smoggiest.

    The city median is taken over the stations that reported. When the worst readings go
    missing in heavy smog, the median there rests on fewer stations and may come out too
    low; the city_<target>_n_stations feature lets the model see that.
    """
    hours = training_rows(features, config).drop_duplicates("hour_end_utc")
    city = hours[f"city_{config.target}_median"]
    stations = hours[f"city_{config.target}_n_stations"]
    tails = {"all hours": pd.Series(True, index=hours.index)}
    for share in TAIL_SHARES:
        tails[f"smoggiest {share:.1%}"] = city >= city.quantile(1 - share)
    rows = []
    for name, in_tail in tails.items():
        rows.append({
            "hours": name, "n_hours": int(in_tail.sum()),
            "city_median_from_ug_m3": round(float(city[in_tail].min()), 1),
            "stations_mean": round(float(stations[in_tail].mean()), 1),
            "stations_min": int(stations[in_tail].min()),
        })
    return pd.DataFrame(rows)


def print_summary(features: pd.DataFrame, tables: dict[str, pd.DataFrame], config: PipelineConfig) -> None:
    n_stations = features["slug"].nunique()
    print(f"Feature table: {len(features):,} rows ({n_stations} stations x "
          f"{len(features) // n_stations:,} hours), {len(tables['feature_list'])} features")
    print("Features per group:", tables["feature_list"]["group"].value_counts(sort=False).to_dict())
    rho = tables["feature_correlations"]
    print(f"\nSpearman rho with the {config.target} value {config.features.horizon_hours} h later "
          "(training rows only):")
    print(rho.loc[rho["group"].isin(SUMMARY_GROUPS), ["feature", "rho", "n"]].to_string(index=False))
    print("\nStations behind the city median (training hours):")
    print(tables["city_median_stations"].to_string(index=False))


def main() -> int:
    try:
        config, hourly, weather = load_inputs()
        features = build_features(hourly, weather, config)
        columns = [c for c in features.columns if c not in NON_FEATURE_COLUMNS]
        notes = feature_notes(columns, config.target)
    except (ConfigError, InputsOutOfDate, GridError, FeatureError, UndescribedFeatureError) as err:
        print(f"STOPPED: {err}", file=sys.stderr)
        return 1
    rho = notes[["feature", "group"]].merge(correlations(features, columns, config), on="feature")
    tables = {
        "feature_list": notes,
        "feature_correlations": rho,
        "city_median_stations": city_median_support(features, config),
    }
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    features.to_parquet(OUT_PARQUET, index=False)
    for name, table in tables.items():
        table.to_csv(OUT / f"{name}.csv", index=False)
    print_summary(features, tables, config)
    print(f"\nWrote {OUT_PARQUET.relative_to(PROJECT_ROOT)} and {len(tables)} tables in "
          f"{OUT.relative_to(PROJECT_ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
