"""Live forecasts, stage C: which OpenAQ sensor carries each pollutant at each of our stations.

OpenAQ locations keep old, dead sensors next to the current ones, so for every station in
config/openaq_locations.csv and every pollutant the live forecasts use (PM2.5, PM10, NO2, CO),
this picks the sensor that reported most recently. Needs the free key in OPENAQ_API_KEY.

Output:  config/openaq_sensors.csv (slug, parameter, sensor_id). Re-run it if a sensor goes silent.
Usage:   .venv/bin/python scripts/01d_openaq_sensors.py
"""

import os
import sys
import time
from typing import Final

import pandas as pd

from delhi_pm25.live_inputs import LIVE_PARAMETERS, SPACING_S, Deadline, LiveInputError, OpenAQ, RateLimiter, newest_sensors
from delhi_pm25.paths import PROJECT_ROOT

LOCATIONS_CSV: Final = PROJECT_ROOT / "config" / "openaq_locations.csv"
OUT: Final = PROJECT_ROOT / "config" / "openaq_sensors.csv"


def main() -> int:
    key = os.environ.get("OPENAQ_API_KEY", "")
    if not key:
        print("STOPPED: set OPENAQ_API_KEY (free key from explore.openaq.org/register)", file=sys.stderr)
        return 1
    client = OpenAQ(key, RateLimiter(SPACING_S), Deadline(60 * 60))
    rows, gaps = [], []
    started = time.monotonic()
    for station in pd.read_csv(LOCATIONS_CSV).itertuples():
        try:
            chosen = newest_sensors(client.sensors(station.openaq_location_id), LIVE_PARAMETERS)
        except LiveInputError as err:
            print(f"STOPPED at {station.slug}: {err}", file=sys.stderr)
            return 1
        rows += [{"slug": station.slug, "parameter": name, "sensor_id": sensor_id} for name, sensor_id in sorted(chosen.items())]
        print(f"{station.slug}: {sorted(chosen)} ({time.monotonic() - started:.0f} s so far)", flush=True)
        gaps += [f"{station.slug}:{name}" for name in LIVE_PARAMETERS if name not in chosen]
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"Wrote {len(rows)} sensors for {len({r['slug'] for r in rows})} stations to {OUT.relative_to(PROJECT_ROOT)}")
    print(f"pollutants with no reporting sensor: {gaps or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
