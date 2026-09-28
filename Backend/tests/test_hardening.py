"""Phase 18 hardening tests: health/readiness, model cache, replay restart."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from src.api import schemas as S


@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan (startup loads frozen artifacts once)."""
    from src.api.app import app

    with TestClient(app) as handle:
        yield handle


def collect_until(ws, want_type, count=1, timeout_s=300.0):
    out = []
    deadline = time.perf_counter() + timeout_s
    while len(out) < count:
        if time.perf_counter() > deadline:
            raise TimeoutError(f"timed out waiting for {want_type}")
        message = ws.receive_json()
        if message["type"] == want_type:
            out.append(message)
    return out


class Collector(threading.Thread):
    def __init__(self, ws):
        super().__init__(daemon=True)
        self._ws = ws
        self.messages: list = []

    def run(self):
        try:
            while True:
                self.messages.append(self._ws.receive_json())
        except Exception:  # noqa: BLE001 - socket closed
            pass

    def of_type(self, kind):
        return [m for m in self.messages if m["type"] == kind]


def wait_for(predicate, timeout_s=180.0, interval_s=0.2):
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


# D/F. Health keeps compatibility and distinguishes data from models.
def test_health_compat_and_data_status(client):
    for path in ("/health", "/api/v1/health"):
        payload = S.HealthResponse.model_validate(client.get(path).json())
        assert payload.service == "skyguard-api"
        assert payload.data_mode == "historical_replay"
        assert payload.data_status == "available"
        assert set(payload.model_status.model_dump()) == {
            "statistical", "isolation_forest", "lstm_autoencoder",
            "ensemble", "root_cause"}


# G. Readiness reports every demo capability without inference.
def test_readiness(client):
    response = client.get("/api/v1/demo/readiness")
    assert response.status_code == 200
    payload = S.ReadinessResponse.model_validate(response.json())
    assert payload.ready is True
    assert payload.data_mode == "historical_replay"
    assert payload.default_station == "DEL-01"
    assert payload.default_split == "OOD"
    assert payload.replay_available is True
    assert payload.probe_available is True
    assert payload.evaluation_available is True
    assert payload.missing == []


# E. Model groups load once and are shared across entries/threads.
def test_model_cache_shared(client):
    from src.api import app as app_module
    from src.api.services import scoring as SC

    store = app_module.STORE
    assert store is not None
    first = SC.get_models(store, "delhi")
    assert SC.get_models(store, "delhi") is first
    results = []

    def load():
        results.append(SC.get_models(store, "delhi"))

    threads = [threading.Thread(target=load) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results and all(bundle is first for bundle in results)
    assert set(first) >= {"if", "cal", "scaler", "lstm", "rc", "explainer"}


# N. Stop then start again runs cleanly with reset counters.
def test_restart_after_stop(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 3600, "limit": 8})
        collect_until(ws, "reading")
        ws.send_json({"action": "stop"})
        stopped = collect_until(ws, "replay_state")[0]
        assert stopped["status"] == "stopped"
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 3600, "limit": 3})
        done = collect_until(ws, "complete", timeout_s=300.0)[0]
        assert done["processed"] == 3
        assert done["anomalies"] >= 0


# N. Completion then start again runs cleanly.
def test_restart_after_complete(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        for _ in range(2):
            ws.send_json({"action": "start", "station_id": "DEL-01",
                          "split": "OOD", "speed": 3600, "limit": 2})
            done = collect_until(ws, "complete", timeout_s=300.0)[0]
            assert done["processed"] == 2


# N/O. Disconnect mid-run, reconnect, start again; stop leaves silence.
def test_restart_after_disconnect_and_quiescence(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 1, "limit": 30})
        collect_until(ws, "reading")
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        collector = Collector(ws)
        collector.start()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 1, "limit": 30})
        assert wait_for(lambda: len(collector.of_type("reading")) >= 1,
                        timeout_s=180.0)
        ws.send_json({"action": "stop"})
        assert wait_for(lambda: any(
            m.get("status") == "stopped" for m in collector.of_type("replay_state")))
        frozen = len(collector.messages)
        time.sleep(4)
        assert len(collector.messages) == frozen


# P. Longer session completes bounded and the server stays responsive.
def test_long_session_bounded(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 3600, "limit": 500})
        done = collect_until(ws, "complete", timeout_s=900.0)[0]
        assert done["processed"] == 500
    assert client.get("/health").status_code == 200
