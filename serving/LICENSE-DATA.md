# Data licence for this folder

`replay_2025.parquet` holds this project's PM2.5 forecasts for 2025 next to the PM2.5 values
that were measured. The measured values are derived from data published by the Central
Pollution Control Board (CPCB), obtained from Vonter/india-cpcb-aqi (ODbL-1.0) and OpenCity.
This file is therefore a derived database, released under the
[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).

Attribution: Central Pollution Control Board (CPCB);
[Vonter/india-cpcb-aqi](https://github.com/Vonter/india-cpcb-aqi);
[OpenCity](https://data.opencity.in). The forecasts also use weather from
[Open-Meteo](https://open-meteo.com) (CC BY 4.0).

Rebuild it with `.venv/bin/python scripts/10_horizon_models.py` (see the README).

`live_forecast.json` holds the latest live forecast and the PM2.5 values measured in the hour it
starts from. Those readings are CPCB's, fetched through [OpenAQ](https://openaq.org), and are
released under the same ODbL 1.0 terms with the same credits (plus OpenAQ). `models/` holds the
24 live models that produce it (`scripts/11_live_models.py`).
