"""The running service: `uvicorn delhi_pm25.server:app`.

Paths default to the project folders; the environment variables REPLAY_PARQUET, STATIONS_CSV,
FRONTEND_DIST and LIVE_FORECAST_FILE override them (the Docker image uses these). The live
forecast is read from LIVE_FORECAST_URL (by default the file the GitHub Action commits).
"""

import os
from pathlib import Path

from delhi_pm25.api import create_app
from delhi_pm25.live_source import LiveSource, github_fetch
from delhi_pm25.paths import PROJECT_ROOT, SERVING_DIR, STATIONS_CSV
from delhi_pm25.serving import Replay


def _path(variable: str, default: Path) -> Path:
    return Path(os.environ.get(variable, str(default)))


LIVE_FORECAST_URL = os.environ.get(
    "LIVE_FORECAST_URL",
    "https://raw.githubusercontent.com/Adityaporwal18/delhi-pm25-forecast/main/serving/live_forecast.json",
)

app = create_app(
    Replay.load(_path("REPLAY_PARQUET", SERVING_DIR / "replay_2025.parquet"), _path("STATIONS_CSV", STATIONS_CSV)),
    frontend=_path("FRONTEND_DIST", PROJECT_ROOT / "frontend" / "dist"),
    live=LiveSource(github_fetch(LIVE_FORECAST_URL), _path("LIVE_FORECAST_FILE", SERVING_DIR / "live_forecast.json")),
)
