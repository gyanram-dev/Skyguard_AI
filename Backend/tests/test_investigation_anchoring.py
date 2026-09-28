"""Phase 21B anchoring tests: investigation history follows the alert.

History windows end at the selected alert/event timestamp, never at the
dataset latest. Timezones stay in their native basis (naive-local Delhi/
Jena frames, UTC NOAA) with no fabricated offsets.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api import schemas as S
from src.api.services import station_service as SS


@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan (startup loads frozen artifacts once)."""
    from src.api.app import app

    with TestClient(app) as handle:
        yield handle


@pytest.fixture(scope="module")
def store():
    from src.api.dependencies import DataStore

    return DataStore.load(".")


def _delhi_mapping(store):
    return next(m for m in store.mapping if m["frontend_station_id"] == "DEL-01")


# history_range ends at the given event time (not dataset latest).
def test_range_anchored_at_event(store):
    mapping = _delhi_mapping(store)
    latest = str(store.pipeline["delhi"]["obs"]["timestamp"].iloc[-1])
    early = "2024-06-14 10:20:00"
    points = SS.history_range(store, mapping, "temperature", early, 24)
    assert points
    assert max(p["timestamp"] for p in points) <= early
    assert any(p["timestamp"] == early for p in points)
    assert all(p["timestamp"] <= latest for p in points)


# 1+2. Old and recent alerts both anchor their own detail history.
@pytest.mark.parametrize("limit", [200])
def test_old_and_recent_alerts_anchor(client, limit):
    alerts = S.AlertListResponse.model_validate(
        client.get("/api/v1/alerts", params={"limit": limit}).json()).alerts
    assert len(alerts) >= 2
    oldest, newest = alerts[-1], alerts[0]
    assert oldest.timestamp < newest.timestamp
    for alert in (oldest, newest):
        detail = S.AlertDetailResponse.model_validate(
            client.get(f"/api/v1/alerts/{alert.alert_id}").json())
        series = detail.history.series
        assert series
        assert max(p["timestamp"] for p in series) <= alert.timestamp
        assert any(p["timestamp"] == alert.timestamp for p in series)


# 3. Alert at the dataset boundary anchors without leaking past it.
def test_boundary_alert(store, client):
    mapping = _delhi_mapping(store)
    latest = str(store.pipeline["delhi"]["obs"]["timestamp"].iloc[-1])
    points = SS.history_range(store, mapping, "temperature", latest, 24)
    assert points
    assert max(p["timestamp"] for p in points) == latest


# 4. No timezone arithmetic: naive-local frames compare in native basis.
def test_no_timezone_shift(store):
    mapping = _delhi_mapping(store)
    stamp = "2024-06-14 10:20:00"
    points = SS.history_range(store, mapping, "temperature", stamp, 1)
    assert any(p["timestamp"] == stamp for p in points)
    frame = store.pipeline["delhi"]["obs"]
    assert "+05:30" not in str(frame["timestamp"].iloc[0])
    assert pd.Timestamp(stamp).strftime("%Y-%m-%d %H:%M:%S") == stamp


# 7. Station history endpoint still serves latest-anchored windows.
def test_station_history_latest_anchored(client):
    body = S.HistoryResponse.model_validate(client.get(
        "/api/v1/stations/DEL-01/history",
        params={"variable": "temperature", "hours": 24}).json())
    assert body.points
