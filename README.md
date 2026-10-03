# Delhi PM2.5 forecast — 48 hours ahead, per monitoring station

Forecasts **hourly PM2.5** (fine particulate matter, in µg/m³) up to 48 hours ahead for
37 of Delhi's 39 continuous air-quality monitoring stations, using three years of CPCB
station data (2023–2025) and Open-Meteo weather.

> **Status (2 Oct 2026): stages 1–2 of 7 done — data collected and cleaned.**
> No model has been trained yet, so the results table below is empty on purpose.
> The two things a reader should know before any result appears — the missing-data
> problem and which stations were dropped — are written down now, before modelling.

## What this project forecasts (and what it does not)

- **It forecasts PM2.5 concentration, not AQI.** India's AQI is a 0–500 index built from
  24-hour averages of up to seven pollutants, reporting the worst one. This project
  predicts one pollutant, hour by hour, in µg/m³.
- The map will colour stations with CPCB's PM2.5 bands (Good 0–30, Satisfactory 31–60,
  Moderate 61–90, Poor 91–120, Very Poor 121–250, Severe above 250 µg/m³). CPCB defines
  these bands for 24-hour averages, so the map labels them **"PM2.5-based category"** and
  never calls them AQI.
- Why PM2.5: particulate matter (PM2.5 or PM10) decides Delhi's AQI in 92.6% of the hours
  where an AQI can be computed, and the AQI stops at 500 (Anand Vihar sits at the cap in
  10.2% of those hours), so it cannot tell "very bad" from "catastrophic".
- The whole pipeline can be re-run with PM10 as the target by changing one line in
  `config/pipeline.toml`.

## The most important limitation: the worst readings are often missing

Monitors drop out more often exactly when pollution is extreme, so the hardest hours are
the ones we can least measure. Statisticians call this data *missing not at random*.

How often the **next** 15-minute reading is blank, by the level of the current reading
(all 39 stations, 2023–2025; `reports/stage2/missing_after_high_readings.csv`):

| Current reading (µg/m³)   | below 300 | 300–600 | 600–800 | 800–900 | 900–950 | 950 or more |
|---------------------------|-----------|---------|---------|---------|---------|-------------|
| PM2.5: next reading blank | 1.8%      | 2.2%    | 2.9%    | 6.3%    | 10.3%   | **19.3%**   |
| PM10: next reading blank  | 1.2%      | 1.1%    | 1.8%    | 3.9%    | 6.0%    | **8.3%**    |

The analysers stop at 1000 µg/m³, and readings near that limit are often deleted instead
of published.

Blank hourly PM2.5 values in the test period (calendar 2025), in all hours and in the
smoggiest hours. An hour's smog level is the median across the stations that did report,
so an hour still counts as smoggy when its worst readings are missing
(37 kept stations, after cleaning; `reports/stage2/missing_in_worst_hours.csv`):

| Test hours (2025) | Hours | City median at least | PM2.5 blank (cannot be scored) | Built from only 1–3 of 4 readings |
|-------------------|-------|----------------------|--------------------------------|-----------------------------------|
| All hours         | 8,760 | —                    | 4.6%                           | 6.3%                              |
| Smoggiest 10%     | 879   | 223 µg/m³            | **3.1%**                       | 6.1%                              |
| Smoggiest 1%      | 88    | 379 µg/m³            | **8.7%**                       | 7.1%                              |
| Smoggiest 0.1%    | 9     | 488 µg/m³            | **27.3%**                      | 10.5%                             |

How to read this:

- The smoggiest 10% of hours are ordinary winter smog, and the monitors work about as well
  then as at any other time (3.1% blank, against 4.6% overall, which long outages in clean
  months push up). A single "top 10%" number would make the problem look solved.
- The problem sits in the extreme tail: 8.7% of values are missing in the worst 1% of hours,
  and more than a quarter in the worst 0.1% (only 9 hours, so that figure is rough).
- An hourly value built from fewer than four readings comes out too low when the missing
  readings were the highest ones.

What this means for the results:

- Every error number in this project is computed on hours that *were* measured. It
  understates the error in the most dangerous hours, and the model sees few extreme values
  to learn from.
- No missing PM2.5 value is ever filled in: we do not invent the numbers we score against.
- Hours where an analyser hit its 1000 µg/m³ limit carry a flag (`pm25_at_ceiling`).
- The error on the smoggiest 10% and 1% of test hours is a **headline result**, reported
  next to the overall error together with the share of those hours that cannot be scored.

## Results

Mean absolute error (MAE, average size of the miss in µg/m³; lower is better) of the
48-hour-ahead PM2.5 forecast on the test period, calendar 2025 (Delhi time). The baseline
is persistence: "PM2.5 in 48 hours = PM2.5 now".

| Test hours    | Cannot be scored (blank) | Persistence baseline MAE | Model MAE             |
|---------------|--------------------------|--------------------------|-----------------------|
| All hours     | 4.6%                     | not run yet (stage 4)    | not run yet (stage 5) |
| Smoggiest 10% | 3.1%                     | —                        | —                     |
| Smoggiest 1%  | 8.7%                     | —                        | —                     |

Where the model is weak (winter vs summer, spikes vs steady periods, station by station)
will be reported in stage 6.

## Stations: the selection rule was fixed before any model

Rule, set on 2 Oct 2026 in `config/pipeline.toml` before any model was trained: keep a
station only if it reported PM2.5 in at least **75% of its 15-minute slots during the
training period** (2023–2024, Delhi time). Test-period coverage is shown below but is not
used by the rule.

| Station                       | Training coverage | Test coverage (not used) | Result      |
|-------------------------------|-------------------|--------------------------|-------------|
| Chandni Chowk (IITM)          | 29.3%             | 73.1%                    | **dropped** |
| Lodhi Road (IITM)             | 35.0%             | 76.3%                    | **dropped** |
| Sirifort (CPCB), lowest kept  | 79.1%             | 95.7%                    | kept        |

- 37 of 39 stations are kept. Judged on test data instead, Lodhi Road (IITM) would have
  passed and Chandni Chowk nearly so; the rule deliberately looks only at training data.
- The result does not hinge on the split date: with the test period starting 1 Jul 2025
  the same two stations are dropped; starting it 1 Jul 2024 would also drop Sirifort
  (73.5%). To check, change `test_start` and re-run `scripts/05_clean.py`.
- Full table, with coverage per year: `reports/stage2/station_selection.csv`.

## Rules that keep the evaluation honest

- **Time-based split, never shuffled:** train on 2023–2024, test on calendar 2025 (Delhi
  time), set once in `config/pipeline.toml`.
- Every decision that looks at the data (station selection, thresholds) uses training
  data only.
- A forecast made at hour *t* may only use what is known at *t*: each hourly value counts
  from the end of its hour, and the actual weather at *t* + 48 h is never used.
- Two cleaning rules (spikes, frozen readings) look at the following hours, so in live use
  they cannot be applied in exactly the same way to the newest hours. This is a small,
  known difference between the test setup and live forecasts.

## Cleaning decisions (stage 2)

Every choice lives in `config/pipeline.toml`; the evidence is in `reports/stage2/`.

| #    | Question | Decision | Why |
|------|----------|----------|-----|
| D0   | What to forecast | Hourly PM2.5 (µg/m³) | See "What this project forecasts". |
| D1   | Timestamps | Labels are Delhi time (IST) wrongly marked `+0000`; converted once to true UTC (label − 5 h 30 min). Each hourly value is stamped with the **end** of its hour, the moment it is known. | Solar radiation peaks at label 11:15–13:15 at all 30 stations with a sun sensor (solar noon is 12:20 IST = 06:50 UTC); station temperature matches Open-Meteo best after a 5–5.5 h shift at all 26 stations with a thermometer; stations without sensors line up with sun-checked neighbours within ±1 h; an independent OpenAQ copy with explicit `+05:30` matches 83 of 83 readings at zero shift. |
| D2   | 15-minute → hourly | Mean of the readings present (at least 1 of 4); the count is stored (`n_pm25`) | Demanding all four would blank another 6.9% of station-hours, and about half the hours at Jahangirpuri and Rohini, where one slot is routinely missing. |
| D3   | Missing values | Left blank; the target is never filled | Interpolation uses the next real reading (future information) and would draw a straight line under deleted peaks. |
| D3   | Stations | Keep if ≥ 75% coverage in training | See "Stations" above. |
| D4.1 | One-hour spikes (up more than 200 µg/m³ and straight back down) | Removed only when the city median that hour is below 300 µg/m³: 126 removed, 27 kept | On calm days they are glitches (DTU, 4 Mar 2024: 24 → 1000 → 15). On polluted nights they can be real (Sonia Vihar, Diwali night 2025: 514 → 923 → 713, city median 853). |
| D4.2 | Frozen readings | Values unchanged for 6 hours or more are blanked: PM2.5 54 stretches (1,233 h), PM10 41 (775 h) | A stuck analyser (longest: Narela, 153 hours at exactly 53.0 µg/m³ in June 2023). |
| D4.3 | PM2.5 above PM10 (physically odd) | Kept | Rare: a median of 0% of hours per station. |
| D4.4 | Station weather sensors | Not used; weather comes from Open-Meteo | 13 of the 39 stations have no thermometer; the "BP (mmHg)" column holds hPa at 24 stations, mmHg at 4 and nothing at 11. |
| D5   | Station identity | CPCB station ID (e.g. `site_124`), not the name | Names drift (trailing spaces, different titles), and Lodhi Road IITM and Lodhi Road IMD are different stations 0.67 km apart (PM2.5 correlation 0.57). |
| D6   | Time grid | One row per station per hour, blank if no data; a check stops the run otherwise | Without it, "the value 24 rows earlier" silently stops meaning "24 hours earlier". |
| —    | Textbook outlier rule (IQR) | Rejected | It would delete 5.5% of hours, 93.8% of them in October–January: exactly the season we must forecast. |

Also not carried past cleaning: NO and NOx (they overlap with NO2) and benzene, toluene and
xylene (mostly empty).

## Quirks in the source data (handled in cleaning)

- Timestamps are Delhi time but marked `+0000` (UTC): the upstream parser labels local time
  as UTC without shifting it. Joining them to weather as if they were UTC would misalign
  everything by 5.5 hours.
- The upstream compiler deletes rows in which every column is empty, so three stations
  (ITO, NSIT Dwarka, Shadipur) have fewer rows; the hourly grid turns these into explicit
  blanks.
- Most DPCC stations publish hourly values repeated in all four 15-minute slots; IMD
  stations report genuine 15-minute values.
- Analysers top out at 1000 µg/m³. Some stations publish 1000, others leave the reading
  blank (see the limitation above).

## Data and credits

| What | Source | Licence |
|------|--------|---------|
| PM2.5, PM10 and gases, 15-minute, 39 stations, 2023 | CPCB data repository, compiled by [Vonter/india-cpcb-aqi](https://github.com/Vonter/india-cpcb-aqi) (release `2023`) | ODbL-1.0 |
| The same, 2024–2025 | CPCB data repository, republished by [OpenCity](https://data.opencity.in/) as "Delhi Hourly Air Quality Reports" | treated as ODbL-1.0 (copies of the Vonter files) |
| Weather: ECMWF IFS actuals, ERA5 boundary-layer height, archived DWD ICON forecasts | [Open-Meteo](https://open-meteo.com/) Historical Weather and Previous Runs APIs (free, non-commercial) | CC BY 4.0 |
| Station coordinates | CPCB's real-time air-quality feed on data.gov.in | Government Open Data License – India |

- Air-quality data: **Central Pollution Control Board (CPCB)**, Government of India,
  continuous monitoring stations operated by CPCB, DPCC, IMD and IITM.
- The two copies agree: R K Puram 2024 is identical value for value in Vonter's release and
  OpenCity's file (631,295 values), and all 39 stations have identical row counts.
- The station data is licensed under ODbL-1.0. Raw and cleaned data are **not** committed
  here (the scripts download them), and any derived database shared publicly must carry
  the same licence. The map footer (stage 7) credits CPCB, Vonter/india-cpcb-aqi, OpenCity
  and Open-Meteo.
- Older years exist upstream (back to 2009) but are not used here.

## Reproduce

Python 3.14; versions pinned in `requirements.txt`. About 1.2 GB of downloads.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python scripts/01_fetch_cpcb.py                      # 2024–2025 station files (~460 MB)
.venv/bin/python scripts/01b_fetch_cpcb_vonter.py --year 2023  # 2023 (~690 MB download)
.venv/bin/python scripts/02_fetch_weather.py                   # weather, ~8 min (free API, rate-limited)
.venv/bin/python scripts/03_stack_raw.py                       # stack every raw file -> data/interim/
.venv/bin/python scripts/04_inspect_raw.py                     # data-quality evidence -> reports/stage2/
.venv/bin/python scripts/05_clean.py                           # cleaning -> data/interim/hourly_clean.parquet

.venv/bin/python -m pytest                                     # 75 tests
```

- The fetch scripts skip files already downloaded, and record SHA-256 fingerprints in the
  committed manifests (`data/raw/cpcb/manifest*.csv`, `data/raw/weather/manifest.csv`), so
  you can confirm you have exactly the data these results came from.
- Adding a year is a re-run, not a rewrite: `01b_fetch_cpcb_vonter.py --year YYYY`, then
  scripts 02–05. If the weather files do not cover the new dates, `05_clean.py` stops and
  prints the exact command to fix it.

## Project layout

```
config/stations.csv    the 39 stations: CPCB ID, name, agency, coordinates
config/pipeline.toml   every target, split and cleaning decision (change here, re-run)
scripts/               01-05: fetch -> stack -> inspect -> clean (run in order)
src/delhi_pm25/         the tested code the scripts use
tests/                 pytest tests
reports/stage2/        data-quality evidence and cleaning logs (committed)
data/                  downloaded and derived data (not committed; rebuilt by the scripts)
```

## Progress

1. Data — done
2. Cleaning — done
3. Features — next
4. Time-based split and persistence baseline
5. Model (LightGBM or XGBoost)
6. Error analysis, with the smoggiest hours as the headline
7. API, map frontend and deployment
