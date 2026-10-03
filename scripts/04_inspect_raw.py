"""Stage 2, step 2: inspect the stacked raw data and write the evidence for each cleaning decision.

Nothing is cleaned here. Every table in reports/stage2/ backs one decision (D0-D6)
that YOU make; the cleaning script then applies exactly those choices, so each
choice can be defended (and changed) later.

INPUT    data/interim/cpcb_15min_raw.parquet   (from scripts/03_stack_raw.py)
         data/raw/weather/actual_ecmwf_ifs/     (Open-Meteo, true UTC: the time-zone check)
OUTPUT   reports/stage2/*.csv and two .png charts (small, committed to git as evidence)

"Hourly" below is PROVISIONAL: the 15-min readings averaged by their *label* hour,
before the time-zone and averaging decisions are made.

USAGE    .venv/bin/python scripts/04_inspect_raw.py
"""

import sys
from typing import Final

import matplotlib

matplotlib.use("Agg")  # draw straight to PNG files, no window
import matplotlib.pyplot as plt
import pandas as pd

from delhi_pm25 import inspect_coverage as cov
from delhi_pm25 import inspect_values as val
from delhi_pm25.paths import INTERIM_DIR, RAW_WEATHER_DIR, REPORTS_DIR, STATIONS_CSV

OUT: Final = REPORTS_DIR / "stage2"
RAW_PARQUET: Final = INTERIM_DIR / "cpcb_15min_raw.parquet"
WEATHER_SOURCE: Final = "actual_ecmwf_ifs"
FLAT_HOURS: Final = 6  # same hourly PM2.5 value this many hours in a row = suspicious
SPIKE_JUMP: Final = 200.0  # µg/m³ up AND back down within one hour
NEARBY_KM: Final = 3.0
WORST_DAYS: Final = 10
MIN_COVERAGE_PCT: Final = 75.0  # only used to list low-coverage stations in the summary


def open_meteo_actuals() -> tuple[pd.DataFrame, pd.Series]:
    """Open-Meteo temperature per station (naive-UTC hour x slug) and the city-mean sunshine."""
    cells = pd.read_csv(RAW_WEATHER_DIR / "station_cells.csv")
    cells = cells[cells["source"] == WEATHER_SOURCE]
    by_cell = {}
    for cell_id in cells["cell_id"].unique():
        frame = pd.read_csv(RAW_WEATHER_DIR / WEATHER_SOURCE / f"{cell_id}.csv")
        utc = pd.to_datetime(frame["time_utc"]).dt.tz_convert(None)  # explicit UTC -> naive UTC
        by_cell[cell_id] = frame.set_index(utc.rename("time_utc"))
    temperature = pd.DataFrame({row.slug: by_cell[row.cell_id]["temperature_2m"] for row in cells.itertuples()})
    shortwave = pd.concat([f["shortwave_radiation"] for f in by_cell.values()], axis=1).mean(axis=1)
    return temperature, shortwave


def naming_table(stations: pd.DataFrame, files: pd.DataFrame) -> pd.DataFrame:
    """Config name vs the name(s) inside the data files vs the OpenCity title, per CPCB ID."""
    in_files = files.groupby("station_id")["names_in_file"].agg(lambda s: " | ".join(sorted(set(s))))
    columns = ["slug", "station_id", "agency", "station_name", "opencity_15min_resource"]
    table = stations[columns].merge(in_files, left_on="station_id", right_index=True, how="left")
    table["name_in_file_differs"] = table["names_in_file"] != table["station_name"].map(repr)
    return table.set_index("slug")


def plot_monthly_coverage(monthly: pd.DataFrame, overall_pct: pd.Series) -> None:
    """Heatmap: % of hours with a PM2.5 reading, station x month, worst stations at the top."""
    order = overall_pct.sort_values().index
    data = monthly.loc[order]
    fig, ax = plt.subplots(figsize=(13, 11))
    image = ax.imshow(data.to_numpy(), cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
    ax.set_yticks(range(len(order)), [f"{s}  ({overall_pct[s]:.0f}%)" for s in order], fontsize=8)
    ax.set_xticks(range(data.shape[1]), data.columns, rotation=90, fontsize=8)
    ax.set_title("Hours with at least one PM2.5 reading (% per station and month; label time)")
    fig.colorbar(image, ax=ax, label="% of hours")
    fig.tight_layout()
    fig.savefig(OUT / "pm25_coverage_by_month.png", dpi=110)
    plt.close(fig)


def plot_timezone_check(readings: pd.DataFrame, shortwave: pd.Series) -> None:
    """Station sunshine by label clock vs Open-Meteo sunshine placed on a UTC and an IST clock."""
    labels = readings["ts_label"]
    station = readings["sr"].groupby(labels.dt.hour + labels.dt.minute / 60).mean()
    om = shortwave.groupby(shortwave.index.hour).mean()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(station.index, station / station.max(), color="black", lw=2.5,
            label="Stations' solar-radiation sensors, by the time written in the file")
    # Open-Meteo radiation at hour h is the mean over the PRECEDING hour, centred at h - 0.5 UTC.
    for offset, style, text in [(-0.5, "--", "Open-Meteo sun IF the labels were UTC"),
                                (5.0, "-", "Open-Meteo sun IF the labels are IST (UTC + 5:30)")]:
        curve = pd.Series(om.to_numpy(), index=(om.index + offset) % 24).sort_index()
        ax.plot(curve.index, curve / curve.max(), style, lw=1.8, label=text)
    ax.set_xticks(range(0, 25, 2))
    ax.set_xlabel("Clock time written in the CPCB file (hours)")
    ax.set_ylabel("Mean radiation (1 = daily peak)")
    ax.set_title("Which clock do the CPCB timestamps follow? (all stations pooled, 2024-2025)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "timezone_check.png", dpi=110)
    plt.close(fig)


def print_summary(t: dict[str, pd.DataFrame]) -> None:
    """A few headline numbers per decision; the CSVs hold the full detail."""
    tz, coverage, extremes = t["timezone_evidence"], t["coverage"], t["value_extremes"]
    pm25 = extremes[extremes["pollutant"] == "pm25"]
    low = coverage.loc[coverage["pm25_pct"] < MIN_COVERAGE_PCT, "pm25_pct"].sort_values()
    checks, prominent = t["hourly_checks"], t["prominent_pollutant"]
    print("\nD1 time zone  sun peak says:", tz["sun_says"].value_counts().to_dict(),
          "| best temperature offset (h):", tz["temp_best_offset_h"].value_counts().to_dict())
    clock = t["neighbour_clock_check"]
    print("              PM2.5 vs nearest sun-checked station, best lag (h):",
          clock["best_lag_h"].value_counts().to_dict(),
          f"| stations fitting a UTC clock better: {int((clock['r_if_utc'] > clock['r_lag0']).sum())}")
    print(f"D6 grid       missing 15-min rows: {coverage['missing_rows'].sum():,}; "
          f"off-grid labels: {coverage['off_grid_labels'].sum():,}")
    print("D2 averaging  mean % of hours with N PM2.5 readings:", t["slots_per_hour"].mean().round(1).to_dict())
    print(f"              median % of full hours whose 4 readings are identical: "
          f"{t['repeats_within_hour']['all_four_identical_pct'].median():.0f}%")
    print(f"D3 missing    stations with PM2.5 in < {MIN_COVERAGE_PCT:.0f}% of slots:", low.to_dict())
    print(f"              longest PM2.5 gap: {t['gaps']['longest_gap_h'].max()} h "
          f"({t['gaps']['longest_gap_h'].idxmax()})")
    blank = t["missing_after_high_readings"]["next_missing_pct"]
    print("              next 15-min reading blank after a reading < 300 vs >= 950 µg/m³: "
          + "; ".join(f"{p} {blank[p].iloc[0]}% vs {blank[p].iloc[-1]}%" for p in ["pm25", "pm10"]))
    print(f"D4 values     PM2.5 readings exactly 1000: {int(pm25.loc[pm25['max'] == 1000, 'n_at_max'].sum())}; "
          f"readings <= 0 (any pollutant): {int(extremes['n_nonpositive'].sum()):,}")
    print(f"              hours PM2.5 > PM10: median {checks['pm25_above_pm10_pct'].median()}% per station, "
          f"max {checks['pm25_above_pm10_pct'].max()}% ({checks['pm25_above_pm10_pct'].idxmax()})")
    print(f"              flat runs >= {FLAT_HOURS} h: {checks['flat_runs'].sum()}; "
          f"one-hour spikes > {SPIKE_JUMP:.0f}: {len(t['spikes'])}")
    print("              'BP (mmHg)' looks like:", t["bp_units"]["looks_like"].value_counts().to_dict())
    demo = t["outlier_rule_demo"]["value"]
    print(f"              textbook IQR rule would delete {demo['hours_flagged_pct']}% of hours, "
          f"{demo['flagged_in_oct_to_jan_pct']}% of them in Oct-Jan")
    print(f"D0 target     PM decides the AQI in {prominent.loc['all year', ['pm25', 'pm10']].sum():.1f}% "
          f"of valid hours; median station has a valid AQI in {t['aqi_by_station']['aqi_valid_pct'].median()}% of hours")
    print(f"D5 naming     names differ inside files: {int(t['naming']['name_in_file_differs'].sum())}; "
          f"station pairs within {NEARBY_KM:.0f} km: {len(t['nearby_pairs'])}")


def main() -> int:
    if not RAW_PARQUET.exists():
        print(f"Missing {RAW_PARQUET}. Run scripts/03_stack_raw.py first.", file=sys.stderr)
        return 1
    stations = pd.read_csv(STATIONS_CSV)
    files = pd.read_csv(OUT / "files.csv")
    print("Loading raw readings and Open-Meteo actuals ...")
    readings = pd.read_parquet(RAW_PARQUET)
    hourly = cov.hourly_by_label(readings)
    temperature, shortwave = open_meteo_actuals()
    print("Computing a CPCB-style AQI for every station hour ...")
    aqi = val.station_aqi(hourly)
    timezone = cov.timezone_evidence(readings, temperature)
    sun_checked = timezone.index[timezone["sun_says"] == "IST"].tolist()
    tables = {
        "coverage": cov.coverage_table(readings),
        "slots_per_hour": cov.slots_per_hour(hourly),
        "repeats_within_hour": val.repeats_within_hour(readings),
        "gaps": cov.gap_table(hourly),
        "missing_after_high_readings": pd.concat(
            {p: cov.missing_after_level(readings, p) for p in ["pm25", "pm10"]}, names=["pollutant"]),
        "monthly_pm25_coverage": cov.monthly_coverage(hourly),
        "timezone_evidence": timezone,
        "neighbour_clock_check": val.neighbour_lags(stations, hourly, sun_checked),
        "value_extremes": val.value_extremes(readings),
        "hourly_checks": val.hourly_checks(hourly, FLAT_HOURS),
        "spikes": val.spike_table(hourly, SPIKE_JUMP),
        "bp_units": val.bp_units(readings),
        "naming": naming_table(stations, files),
        "nearby_pairs": val.nearby_pairs(stations, hourly, NEARBY_KM),
        "aqi_by_station": val.aqi_by_station(aqi),
        "prominent_pollutant": val.prominent_shares(aqi),
        "outlier_rule_demo": val.outlier_rule_demo(hourly).to_frame("value"),
        "worst_days": val.worst_days(hourly, WORST_DAYS),
    }
    for name, table in tables.items():
        table.to_csv(OUT / f"{name}.csv", index=not isinstance(table.index, pd.RangeIndex))
    overall_pct = hourly["pm25"].notna().groupby(level="slug", observed=True).mean() * 100
    plot_monthly_coverage(tables["monthly_pm25_coverage"], overall_pct)
    plot_timezone_check(readings, shortwave)
    print_summary(tables)
    print(f"\nWrote {len(tables)} tables and 2 charts to {OUT.relative_to(OUT.parents[1])}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
