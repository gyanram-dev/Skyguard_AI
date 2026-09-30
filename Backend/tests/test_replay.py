"""Phase 16 replay tests: WS /api/v1/live protocol and honesty."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

RC_TAXONOMY = {"SPIKE", "FROZEN", "DRIFT", "CROSS", "MIXED", "UNKNOWN"}


@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan (startup loads frozen artifacts once)."""
    from src.api.app import app

    with TestClient(app) as handle:
        yield handle


def split_frame() -> pd.DataFrame:
    root = Path("data/benchmark/delhi/test_generalization.csv")
    return pd.read_csv(root, usecols=["timestamp", "temperature_c",
                                      "pressure_hpa", "relative_humidity_pct"])


def collect_until(ws, want_type, count=1, timeout_s=300.0):
    """Blocking collect of count messages of one type (skips others)."""
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
    """Background drain of every server message into a shared list."""

    def __init__(self, ws):
        super().__init__(daemon=True)
        self._ws = ws
        self.messages: list = []
        self.done = False

    def run(self):
        try:
            while True:
                self.messages.append(self._ws.receive_json())
        except Exception:  # noqa: BLE001 - socket closed, stop draining
            self.done = True

    def of_type(self, kind):
        return [m for m in self.messages if m["type"] == kind]


def wait_for(predicate, timeout_s=180.0, interval_s=0.2):
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


# 1+2+17. Connection succeeds with an honest handshake.
def test_1_2_17_connection(client):
    with client.websocket_connect("/api/v1/live") as ws:
        first = ws.receive_json()
        assert first["type"] == "connection"
        assert first["status"] == "connected"
        assert first["data_mode"] == "historical_replay"


# 3. Start is accepted and the replay reaches running.
def test_3_start_accepted(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 3600, "limit": 3})
        preparing = collect_until(ws, "replay_state", timeout_s=120.0)[0]
        assert preparing["status"] == "preparing"
        assert preparing["station_id"] == "DEL-01"
        running = collect_until(ws, "replay_state", timeout_s=120.0)[0]
        assert running["status"] == "running"


# 4+5. Invalid station and speed are structured errors, socket stays open.
def test_4_5_invalid_start(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "NOPE-99",
                      "split": "OOD", "speed": 10})
        error = collect_until(ws, "error")[0]
        assert error["code"] == "unknown_station"
        ws.send_json({"action": "start", "station_id": "JENA-01",
                  "split": "OOD", "speed": 10})
        error = collect_until(ws, "error")[0]
        assert error["code"] == "unknown_station"
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 99999})
        error = collect_until(ws, "error")[0]
        assert error["code"] == "invalid_speed"


# 14. Completion arrives at the end with exact counts.
def test_14_completion(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 3600, "limit": 3})
        done = collect_until(ws, "complete", timeout_s=300.0)[0]
        assert done["station_id"] == "DEL-01"
        assert done["split"] == "OOD"
        assert done["processed"] == 3
        assert done["data_mode"] == "historical_replay"


# 6+7+8+9+15+18. Readings chronological and real; alerts pair with
# detections, carry taxonomy root causes, never duplicate.
def test_6_7_8_9_15_18_stream_honesty(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 3600, "limit": 200})
        readings = []
        alerts = []
        deadline = time.perf_counter() + 400.0
        while time.perf_counter() < deadline:
            message = ws.receive_json()
            if message["type"] == "reading":
                readings.append(message)
            elif message["type"] == "alert":
                alerts.append(message)
            elif message["type"] == "complete":
                break
        assert len(readings) == 200
        stamps = [pd.Timestamp(r["timestamp"]) for r in readings]
        assert stamps == sorted(stamps)
        assert [r["sequence"] for r in readings] == list(range(1, 201))
        source = split_frame()
        for reading in readings[:5]:
            row = source[source["timestamp"] == reading["timestamp"]].iloc[0]
            assert reading["observations"]["temperature_c"] == row["temperature_c"]
            assert reading["observations"]["pressure_hpa"] == row["pressure_hpa"]
            assert reading["observations"]["relative_humidity_pct"] == \
                row["relative_humidity_pct"]
        detected = {r["sequence"] for r in readings if r["anomaly"]["detected"]}
        alerted = {a["sequence"] for a in alerts}
        assert detected == alerted
        assert len({a["alert_id"] for a in alerts}) == len(alerts)
        assert len(alerts) >= 1
        for alert in alerts:
            assert alert["root_cause"] in RC_TAXONOMY
            assert alert["status"] in ("anomaly", "review")
        # Serving contract: a replayed alert is emitted for the COMBINED
        # verdict — the frozen ensemble flag OR the deterministic freeze rule
        # (documented in src/detection/freeze.py and src/ensemble/severity.py).
        # Every alert therefore names its trigger, and the ensemble-triggered
        # rows still have to agree exactly with the frozen predictions file.
        frozen = pd.read_csv(
            "data/ensemble/delhi_ensemble_predictions.csv",
            usecols=["timestamp", "ens_median_flag"])
        by_stamp = dict(zip(frozen["timestamp"].astype(str),
                            frozen["ens_median_flag"]))
        for alert in alerts:
            trigger = alert["trigger"]
            assert trigger in ("ensemble", "freeze", "ensemble+freeze"), trigger
            if trigger in ("ensemble", "ensemble+freeze"):
                assert by_stamp[str(alert["timestamp"])] == 1
            if trigger in ("freeze", "ensemble+freeze"):
                assert alert["freeze"]["confirmed"] is True
        assert any(a["trigger"] in ("ensemble", "ensemble+freeze")
                   for a in alerts)


# 10+11+12. Pause stalls, resume continues, stop terminates.
def test_10_11_12_pause_resume_stop(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        collector = Collector(ws)
        collector.start()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 1, "limit": 30})
        assert wait_for(lambda: any(
            m.get("status") == "running" for m in collector.of_type("replay_state")),
            timeout_s=180.0)
        assert wait_for(lambda: len(collector.of_type("reading")) >= 1,
                        timeout_s=180.0)
        ws.send_json({"action": "pause"})
        assert wait_for(lambda: any(
            m.get("status") == "paused" for m in collector.of_type("replay_state")))
        frozen_count = len(collector.of_type("reading"))
        time.sleep(4)
        assert len(collector.of_type("reading")) == frozen_count
        ws.send_json({"action": "resume"})
        assert wait_for(lambda: any(
            m.get("status") == "running" for m in collector.of_type("replay_state")))
        ws.send_json({"action": "stop"})
        assert wait_for(lambda: any(
            m.get("status") == "stopped" for m in collector.of_type("replay_state")))


# 13+16. Disconnect cleans up; malformed frames stay structured.
def test_13_16_disconnect_and_malformed(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_text("this is not json")
        error = collect_until(ws, "error")[0]
        assert error["code"] == "invalid_command"
        assert "Traceback" not in error["detail"]
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 3600, "limit": 10})
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 3600, "limit": 2})
        done = collect_until(ws, "complete", timeout_s=300.0)[0]
        assert done["processed"] == 2

# 19A. Reading/alert events expose threshold, method, runner-up, and spatial.
def test_19a_event_fields(client):
    with client.websocket_connect("/api/v1/live") as ws:
        ws.receive_json()
        ws.send_json({"action": "start", "station_id": "DEL-01",
                      "split": "OOD", "speed": 3600, "limit": 200})
        readings = []
        alerts = []
        deadline = time.perf_counter() + 400.0
        while time.perf_counter() < deadline:
            message = ws.receive_json()
            if message["type"] == "reading":
                readings.append(message)
            elif message["type"] == "alert":
                alerts.append(message)
            elif message["type"] == "complete":
                break
        assert len(readings) == 200
        first = readings[0]
        assert first["anomaly"]["threshold"] == pytest.approx(0.978295475557844)
        assert first["anomaly"]["method"] == "ens_median"
        assert isinstance(first["evidence"]["spatial"], dict)
        assert first["evidence"]["spatial"]["available"] is True
        assert first["evidence"]["spatial"]["neighbor_count"] >= 2
        assert len(alerts) >= 1
        for alert in alerts:
            assert alert["threshold"] == pytest.approx(0.978295475557844)
            assert alert["root_cause"] in RC_TAXONOMY
