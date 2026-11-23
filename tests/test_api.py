"""Tests for the replay API (src/delhi_pm25/serving.py and src/delhi_pm25/api.py)."""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from delhi_pm25.accuracy import AccuracySummary, HorizonAccuracy, SmogAccuracy
from delhi_pm25.api import create_app
from delhi_pm25.live_source import LiveSource
from delhi_pm25.serving import Replay, category

ISSUED = pd.Timestamp("2025-11-01 02:30", tz="UTC")


@pytest.fixture
def replay(tmp_path: Path) -> Replay:
    """A replay with two stations, two issue times, and horizons 0 (now) and 6 hours."""
    rows = []
    for issued in (ISSUED, ISSUED + pd.Timedelta(hours=12)):
        for slug, now in (("a", 80.0), ("b", 200.0)):
            rows.append({"slug": slug, "issued_utc": issued, "horizon_h": 0,
                         "p10": np.nan, "p50": np.nan, "p90": np.nan, "measured": now})
            rows.append({"slug": slug, "issued_utc": issued, "horizon_h": 6,
                         "p10": now - 20, "p50": now + 15, "p90": now + 60, "measured": np.nan})
    pd.DataFrame(rows).to_parquet(tmp_path / "replay.parquet", index=False)
    pd.DataFrame({"slug": ["a", "b", "c"], "station_name": ["A, Delhi - DPCC", "B, Delhi - IMD", "C (dropped)"],
                  "latitude": [28.6, 28.7, 28.8], "longitude": [77.2, 77.1, 77.0]}).to_csv(tmp_path / "stations.csv", index=False)
    accuracy = AccuracySummary(
        source="test", horizons=[HorizonAccuracy(horizon_h=48, model_mae=34.7, persistence_mae=43.4, climatology_mae=38.0,
                                                 inside_band_pct=79.0, inside_band_smoggiest_10pct=59.3)],
        smoggiest_10pct_48h=SmogAccuracy(model_mae=106.0, climatology_mae=89.3, persistence_mae=108.3, model_bias=-95.6),
    )
    (tmp_path / "accuracy.json").write_text(accuracy.model_dump_json())
    return Replay.load(tmp_path / "replay.parquet", tmp_path / "stations.csv", tmp_path / "accuracy.json")


@pytest.fixture
def client(replay: Replay) -> TestClient:
    return TestClient(create_app(replay))


@pytest.mark.parametrize(("ug_m3", "label"), [(30.0, "Good"), (30.5, "Satisfactory"), (120.0, "Poor"), (250.1, "Severe")])
def test_category_uses_the_cpcb_pm25_bands(ug_m3: float, label: str) -> None:
    band = category(ug_m3)
    assert band is not None and band.label == label


def test_a_blank_value_has_no_category() -> None:
    assert category(math.nan) is None


def test_meta_lists_the_issue_times_and_only_the_stations_in_the_replay(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert (len(meta["issue_times_utc"]), [s["slug"] for s in meta["stations"]], meta["horizons_h"]) == (2, ["a", "b"], [0, 6])


def test_map_colours_each_station_by_its_median_forecast(client: TestClient) -> None:
    points = client.get("/api/map", params={"issued": ISSUED.isoformat(), "horizon": 6}).json()
    assert [(p["slug"], p["p50"], p["category"]) for p in points] == [("a", 95.0, "Poor"), ("b", 215.0, "Very Poor")]


def test_station_forecast_runs_from_now_to_the_last_horizon(client: TestClient) -> None:
    points = client.get("/api/stations/b/forecast", params={"issued": ISSUED.isoformat()}).json()
    assert [(p["horizon_h"], p["measured"], p["p50"]) for p in points] == [(0, 200.0, None), (6, None, 215.0)]


@pytest.mark.parametrize(
    ("path", "issued"),
    [("/api/stations/zzz/forecast", ISSUED.isoformat()), ("/api/map", "2030-01-01T00:00:00+00:00")],
    ids=["unknown station", "unknown issue time"],
)
def test_requests_outside_the_replay_get_a_404(client: TestClient, path: str, issued: str) -> None:
    assert client.get(path, params={"issued": issued}).status_code == 404


LIVE = {
    "generated_at_utc": "2026-11-22T04:27:31+00:00", "issued_utc": "2026-11-22T03:30:00+00:00",
    "stations_reporting": 1, "stations": 1,
    "training_window": {"first_target_utc": "2023-01-01T01:30:00+00:00", "last_target_utc": "2026-11-16T18:30:00+00:00"},
    "rows": [{"slug": "a", "horizon_h": 48, "valid_utc": "2026-11-24T03:30:00+00:00", "p10": 79.2, "p50": 145.1, "p90": 240.0, "measured": None}],
}


def test_live_endpoint_serves_the_latest_forecast(replay: Replay, tmp_path: Path) -> None:
    app = create_app(replay, live=LiveSource(lambda: LIVE, tmp_path / "missing.json"))
    body = TestClient(app).get("/api/live").json()
    assert (body["issued_utc"], body["rows"][0]["p50"], body["stations_reporting"]) == ("2026-11-22T03:30:00Z", 145.1, 1)


def test_no_live_forecast_yet_is_reported_as_unavailable(replay: Replay, tmp_path: Path) -> None:
    def unreachable() -> dict[str, object]:
        raise OSError("GitHub unreachable")

    app = create_app(replay, live=LiveSource(unreachable, tmp_path / "missing.json"))
    assert TestClient(app).get("/api/live").status_code == 503


def test_live_points_carry_the_pm25_based_category_of_their_median(replay: Replay, tmp_path: Path) -> None:
    app = create_app(replay, live=LiveSource(lambda: LIVE, tmp_path / "missing.json"))
    row = TestClient(app).get("/api/live").json()["rows"][0]
    assert (row["category"], row["colour"]) == ("Very Poor", "#ff0000")


def test_accuracy_endpoint_serves_the_held_out_2025_numbers(client: TestClient) -> None:
    body = client.get("/api/accuracy").json()
    assert (body["horizons"][0]["model_mae"], body["horizons"][0]["inside_band_smoggiest_10pct"],
            body["smoggiest_10pct_48h"]["model_mae"]) == (34.7, 59.3, 106.0)


def test_live_files_written_before_station_status_still_load(replay: Replay, tmp_path: Path) -> None:
    body = TestClient(create_app(replay, live=LiveSource(lambda: LIVE, tmp_path / "missing.json"))).get("/api/live").json()
    assert (body["station_status"], body["heavy_smog_now"], body["city_median_now"]) == ([], False, None)


def test_station_status_reaches_the_site(replay: Replay, tmp_path: Path) -> None:
    status = {"slug": "a", "status": "analyser_dark", "last_value": 300.0,
              "last_value_utc": "2026-11-22T12:30:00+00:00", "last_reading_utc": "2026-11-22T15:45:00+00:00"}
    document = LIVE | {"station_status": [status], "city_median_now": 310.0, "heavy_smog_now": True}
    body = TestClient(create_app(replay, live=LiveSource(lambda: document, tmp_path / "missing.json"))).get("/api/live").json()
    assert (body["station_status"][0]["status"], body["heavy_smog_now"]) == ("analyser_dark", True)
