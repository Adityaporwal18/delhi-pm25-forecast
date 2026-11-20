"""The running service: `uvicorn delhi_pm25.server:app`.

Paths default to the project folders; the environment variables REPLAY_PARQUET, STATIONS_CSV
and FRONTEND_DIST override them (the Docker image uses these).
"""

import os
from pathlib import Path

from delhi_pm25.api import create_app
from delhi_pm25.paths import PROJECT_ROOT, SERVING_DIR, STATIONS_CSV
from delhi_pm25.serving import Replay


def _path(variable: str, default: Path) -> Path:
    return Path(os.environ.get(variable, str(default)))


app = create_app(
    Replay.load(_path("REPLAY_PARQUET", SERVING_DIR / "replay_2025.parquet"), _path("STATIONS_CSV", STATIONS_CSV)),
    frontend=_path("FRONTEND_DIST", PROJECT_ROOT / "frontend" / "dist"),
)
