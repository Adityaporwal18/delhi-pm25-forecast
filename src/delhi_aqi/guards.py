"""Checks that stop the pipeline early, naming the exact command that fixes the problem.

Without them a stale file is used silently: after adding a year of PM2.5 data, weather
files that stop short would simply leave that year's weather features blank.
"""

import datetime as dt
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import pandas as pd

WEATHER_HISTORY: Final = dt.timedelta(days=7)


class InputsOutOfDate(Exception):
    """An input file is missing, older than the files it was built from, or covers too few dates."""


def check_up_to_date(output: Path, inputs: Sequence[Path], command: str) -> None:
    """Raise unless `output` exists and is newer than every file in `inputs`."""
    if not output.exists():
        raise InputsOutOfDate(f"{output.name} does not exist yet. Build it with: {command}")
    newest_input = max((path.stat().st_mtime for path in inputs), default=0.0)
    if newest_input > output.stat().st_mtime:
        raise InputsOutOfDate(f"{output.name} is older than its inputs. Rebuild it with: {command}")


def check_weather_covers(manifest: pd.DataFrame, first_day: dt.date, last_day: dt.date) -> None:
    """Raise unless every weather file runs from a week before `first_day` to `last_day`
    (the Delhi dates of the first and last PM2.5 reading). The week is history for lag features."""
    needed_start = first_day - WEATHER_HISTORY
    covered_start = pd.to_datetime(manifest["start_date"]).dt.date.max()
    covered_end = pd.to_datetime(manifest["end_date"]).dt.date.min()
    if covered_start > needed_start or covered_end < last_day:
        raise InputsOutOfDate(
            f"Weather files cover {covered_start}..{covered_end}, but the PM2.5 data needs "
            f"{needed_start}..{last_day} (a week of history before the first reading). Re-download with: "
            f".venv/bin/python scripts/02_fetch_weather.py --start {needed_start} --end {last_day} --force")
