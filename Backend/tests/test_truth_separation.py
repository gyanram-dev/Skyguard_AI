"""Phase 21B truth-separation tests: operational alerts use no labels.

The serving path (alerts + investigation) must never read injection IDs,
fault-type labels, event tables, latencies, or hidden test truth. Those
remain offline-evaluation-only inputs.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api import schemas as S


@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan (startup loads frozen artifacts once)."""
    from src.api.app import app

    with TestClient(app) as handle:
        yield handle


def _label_free_frame():
    """Ensemble rows with every label column removed/renamed away."""
    frame = pd.read_csv("data/ensemble/delhi_ensemble_predictions.csv")
    drop = [c for c in frame.columns
            if any(k in c.lower() for k in ("ground_truth", "injection", "fault_type",
                                            "target_variable", "label", "split"))]
    return frame.drop(columns=drop)


# Operational builder never touches label columns (would KeyError first).
def test_labels_absent_from_builder_inputs():
    import inspect

    from src.api.services import anomaly_service as AS
    from src.api.services import investigation_service as IV

    for module in (AS, IV):
        source = inspect.getsource(module)
        lowered = source.lower()
        for token in ("injection_id", "fault_type", "ground_truth",
                      "event_results", "end_to_end_diagnosis", "latency"):
            assert token not in lowered, f"{module.__name__}: {token}"


# Unlabeled anomalous rows still produce an operational alert.
def test_unlabeled_anomaly_alerts():
    from src.api.dependencies import DataStore
    from src.api.services import anomaly_service as AS

    store = DataStore.load(".")
    frame = _label_free_frame()
    flagged = frame[frame["ens_median_flag"].astype(int) == 1]
    assert len(flagged) > 0
    by_ts = {str(t) for t in flagged["timestamp"].astype(str)}
    alerts = AS.build_alerts(store)
    assert alerts
    assert any(a["timestamp"] in by_ts for a in alerts)
    for alert in alerts:
        assert "injection" not in alert["alert_id"]
        assert set(alert) >= {"alert_id", "station_id", "timestamp", "status",
                              "event", "anomaly_score", "summary"}


# Alert/detail round-trip carries no label leakage.
def test_alert_detail_no_labels(client):
    first = S.AlertListResponse.model_validate(
        client.get("/api/v1/alerts", params={"limit": 5}).json()).alerts[0]
    detail = S.AlertDetailResponse.model_validate(
        client.get(f"/api/v1/alerts/{first.alert_id}").json())
    assert detail.alert.alert_id == first.alert_id
    text = (detail.alert.summary or "") + (detail.explanation.text or "")
    for token in ("injection", "ground_truth", "fault_type"):
        assert token not in text.lower()
    assert detail.ensemble_method == "ens_median"
