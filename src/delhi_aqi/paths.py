"""Where every input and output lives, relative to the project folder."""

from pathlib import Path
from typing import Final

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
STATIONS_CSV: Final = PROJECT_ROOT / "config" / "stations.csv"
RAW_CPCB_DIR: Final = PROJECT_ROOT / "data" / "raw" / "cpcb"
RAW_WEATHER_DIR: Final = PROJECT_ROOT / "data" / "raw" / "weather"
INTERIM_DIR: Final = PROJECT_ROOT / "data" / "interim"
REPORTS_DIR: Final = PROJECT_ROOT / "reports"
