"""Phase 20 upload tests: CSV ingest, mapping, units, DQ, analysis."""

from __future__ import annotations

import numpy as np
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


def make_csv(header, rows):
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join("" if v is None else str(v) for v in row))
    return ("\n".join(lines) + "\n").encode("utf-8")


def timestamps(n, start="2024-03-01 00:00:00", freq="5min"):
    return pd.date_range(start, periods=n, freq=freq).strftime("%Y-%m-%d %H:%M:%S").tolist()


def upload(client, payload, filename="station.csv"):
    return client.post("/api/v1/analyze/upload",
                       files={"file": (filename, payload, "text/csv")})


def confirm(client, sid, mapping, units, label="TEST-01"):
    return client.post(f"/api/v1/analyze/{sid}/confirm",
                       json={"mapping": mapping, "units": units,
                             "station_label": label})


def full_flow(client, payload, mapping, units, filename="station.csv", label="TEST-01"):
    sid = upload(client, payload, filename).json()["session_id"]
    assert confirm(client, sid, mapping, units, label).status_code == 200
    run = client.post(f"/api/v1/analyze/{sid}/run")
    assert run.status_code == 200
    return S.AnalysisResult.model_validate(run.json())


# 1+3. Valid full datasets validate against schemas end to end.
def test_1_3_valid_full(client):
    ts = timestamps(200)
    rows = [(t, 20.0 + (i % 7) * 0.1, 55.0, 1012.0) for i, t in enumerate(ts)]
    body = S.UploadResponse.model_validate(
        upload(client, make_csv(["timestamp", "temperature_c",
                                 "relative_humidity_pct", "pressure_hpa"], rows)).json())
    assert body.rows == 200 and body.columns and not body.warnings
    result = full_flow(client, make_csv(["timestamp", "temperature_c",
                                         "relative_humidity_pct", "pressure_hpa"], rows),
                       {"timestamp": "timestamp", "temperature": "temperature_c",
                        "humidity": "relative_humidity_pct", "pressure": "pressure_hpa"},
                       {"temperature": "C", "pressure": "hPa"})
    assert result.observations == 200
    assert result.normal + result.anomalies == 200
    assert "NaN" not in client.post(
        f"/api/v1/analyze/{body.session_id}/run").text


# 2. Temperature-only dataset: optionals unavailable, never fabricated.
def test_2_temperature_only(client):
    ts = timestamps(120)
    rows = [(t, 21.0) for t in ts]
    body = upload(client, make_csv(["timestamp", "temp"], rows)).json()
    assert body["mapping"]["humidity"]["confidence"] == "absent"
    assert body["mapping"]["pressure"]["confidence"] == "absent"
    sid = body["session_id"]
    preview = S.DQPreview.model_validate(confirm(
        client, sid, {"timestamp": "timestamp", "temperature": "temp"},
        {"temperature": "C"}).json())
    assert preview.rh_available is False
    assert preview.pressure_available is False
    result = S.AnalysisResult.model_validate(
        client.post(f"/api/v1/analyze/{sid}/run").json())
    assert result.observations == 120
    assert result.evidence_availability["isolation_forest"] is False


# 4. Alternate column names map with high confidence.
def test_4_alternate_names(client):
    ts = timestamps(100)
    rows = [(t, 22.0, 60.0, 1011.0) for t in ts]
    body = upload(client, make_csv(["datetime", "air_temp", "RH", "pressure_hpa"],
                                   rows)).json()
    assert body["mapping"]["timestamp"] == {"column": "datetime",
                                            "confidence": "high", "alternates": []}
    assert body["mapping"]["temperature"]["column"] == "air_temp"
    assert body["mapping"]["humidity"]["column"] == "RH"
    assert body["mapping"]["pressure"]["column"] == "pressure_hpa"


# 5. Fahrenheit input is converted (131F spike reads as 55C).
def test_5_fahrenheit(client):
    ts = timestamps(150)
    rows = [(t, 68.0, 55.0, 1012.0) for t in ts]
    rows[100] = (ts[100], 131.0, 55.0, 1012.0)
    body = upload(client, make_csv(["timestamp", "temp_f", "humidity", "pressure"],
                                   rows)).json()
    assert body["units"]["temperature"] == {"unit": "F", "source": "inferred"}
    result = full_flow(client, make_csv(["timestamp", "temp_f", "humidity", "pressure"],
                                        rows),
                       {"timestamp": "timestamp", "temperature": "temp_f",
                        "humidity": "humidity", "pressure": "pressure"},
                       {"temperature": "F", "pressure": "hPa"})
    hits = [a for a in result.anomalies_detail if a.timestamp == ts[100]]
    assert hits and abs((hits[0].observation["temperature_c"] or 0.0) - 55.0) < 0.01


# 6. Pascal pressure is converted (Pa/1000 = hPa).
def test_6_pascal(client):
    ts = timestamps(120)
    rows = [(t, 20.0, 50.0, 101300.0) for t in ts]
    body = upload(client, make_csv(["timestamp", "temperature", "humidity", "pres_pa"],
                                   rows)).json()
    assert body["units"]["pressure"] == {"unit": "Pa", "source": "inferred"}
    result = full_flow(client, make_csv(["timestamp", "temperature", "humidity", "pres_pa"],
                                        rows),
                       {"timestamp": "timestamp", "temperature": "temperature",
                        "humidity": "humidity", "pressure": "pres_pa"},
                       {"temperature": "C", "pressure": "Pa"})
    assert result.observations == 120


# 7. Missing values surface as DQ counts, never anomalies-by-fiat.
def test_7_missing_values(client):
    ts = timestamps(100)
    rows = [(t, None if i % 10 == 0 else 20.0, 55.0, 1012.0) for i, t in enumerate(ts)]
    sid = upload(client, make_csv(["timestamp", "temperature", "humidity", "pressure"],
                                  rows)).json()["session_id"]
    preview = S.DQPreview.model_validate(confirm(
        client, sid, {"timestamp": "timestamp", "temperature": "temperature",
                      "humidity": "humidity", "pressure": "pressure"},
        {"temperature": "C", "pressure": "hPa"}).json())
    assert preview.missing["temperature"] == 10


# 8. Duplicate timestamps are reported.
def test_8_duplicates(client):
    ts = timestamps(100)
    ts[50] = ts[49]
    rows = [(t, 20.0, 55.0, 1012.0) for t in ts]
    sid = upload(client, make_csv(["timestamp", "temperature", "humidity", "pressure"],
                                  rows)).json()["session_id"]
    preview = S.DQPreview.model_validate(confirm(
        client, sid, {"timestamp": "timestamp", "temperature": "temperature",
                      "humidity": "humidity", "pressure": "pressure"},
        {"temperature": "C", "pressure": "hPa"}).json())
    assert preview.duplicates >= 1


# 9. Gaps remain communication events.
def test_9_gaps(client):
    ts = timestamps(60) + timestamps(60, start="2024-03-02 00:00:00")
    rows = [(t, 20.0, 55.0, 1012.0) for t in ts]
    sid = upload(client, make_csv(["timestamp", "temperature", "humidity", "pressure"],
                                  rows)).json()["session_id"]
    preview = S.DQPreview.model_validate(confirm(
        client, sid, {"timestamp": "timestamp", "temperature": "temperature",
                      "humidity": "humidity", "pressure": "pressure"},
        {"temperature": "C", "pressure": "hPa"}).json())
    assert preview.large_gaps >= 1


# 10. Unparseable timestamps are rejected with structure.
def test_10_invalid_timestamp(client):
    rows = [("not-a-time", 20.0, 55.0, 1012.0)] * 10
    sid = upload(client, make_csv(["timestamp", "temperature", "humidity", "pressure"],
                                  rows)).json()["session_id"]
    response = confirm(client, sid, {"timestamp": "timestamp", "temperature": "temperature",
                                     "humidity": "humidity", "pressure": "pressure"},
                       {"temperature": "C", "pressure": "hPa"})
    assert response.status_code == 422
    assert response.json()["code"] in ("invalid_timestamp", "insufficient_data")
    assert "Traceback" not in response.text


# 11. Ambiguous mapping proposes nothing and lists alternates.
def test_11_ambiguous_mapping(client):
    ts = timestamps(50)
    rows = [(t, 20.0, 21.0) for t in ts]
    body = upload(client, make_csv(["timestamp", "temp", "temperature"], rows)).json()
    proposal = body["mapping"]["temperature"]
    assert proposal["column"] is None and proposal["confidence"] == "ambiguous"
    assert set(proposal["alternates"]) == {"temp", "temperature"}
    sid = body["session_id"]
    assert confirm(client, sid, {"timestamp": "timestamp", "temperature": "temp"},
                   {"temperature": "C"}).status_code == 200


# 12. Malformed files and names are rejected safely.
def test_12_malformed(client):
    bad = upload(client, b"\x00\x01\x02not csv at all\xff", filename="bad.csv")
    assert bad.status_code == 422
    assert "Traceback" not in bad.text
    wrong_ext = upload(client, b"a,b\n1,2\n", filename="data.txt")
    assert wrong_ext.status_code == 422
    assert wrong_ext.json()["code"] == "invalid_file"


# 13. Oversized input is rejected before parsing.
def test_13_oversized(client):
    big = b"x," * (11 * 1024 * 1024 // 2)
    response = upload(client, big, filename="big.csv")
    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"


# 14. Unseen station label flows through without Delhi claims.
def test_14_unseen_station(client):
    ts = timestamps(100)
    rows = [(t, 25.0, 60.0, 1009.0) for t in ts]
    result = full_flow(client, make_csv(["timestamp", "temperature", "humidity", "pressure"],
                                        rows),
                       {"timestamp": "timestamp", "temperature": "temperature",
                        "humidity": "humidity", "pressure": "pressure"},
                       {"temperature": "C", "pressure": "hPa"},
                       label="NOWHERE-99")
    assert result.station_label == "NOWHERE-99"
    text = " ".join([result.notes[0] if result.notes else ""])
    assert "Delhi" not in text or "not" in text.lower() or "unvalidated" in text.lower()


# 15. Flat clean data yields no anomalies.
def test_15_no_anomaly(client):
    ts = timestamps(300)
    rows = [(t, 20.0, 55.0, 1012.0) for t in ts]
    result = full_flow(client, make_csv(["timestamp", "temperature", "humidity", "pressure"],
                                        rows),
                       {"timestamp": "timestamp", "temperature": "temperature",
                        "humidity": "humidity", "pressure": "pressure"},
                       {"temperature": "C", "pressure": "hPa"})
    assert result.anomalies == 0
    assert result.normal == 300
    assert result.breakdown == {}


# 16. Spike is estimated with a defensible correction suggestion.
def test_16_spike(client):
    ts = timestamps(200)
    rows = [(t, 20.0, 55.0, 1012.0) for t in ts]
    rows[100] = (ts[100], 55.0, 55.0, 1012.0)
    result = full_flow(client, make_csv(["timestamp", "temperature", "humidity", "pressure"],
                                        rows),
                       {"timestamp": "timestamp", "temperature": "temperature",
                        "humidity": "humidity", "pressure": "pressure"},
                       {"temperature": "C", "pressure": "hPa"})
    hits = [a for a in result.anomalies_detail if a.timestamp == ts[100]]
    assert len(hits) == 1
    hit = hits[0]
    assert hit.root_cause_estimate == "SPIKE"
    assert hit.confidence is None
    assert hit.correction is not None
    assert hit.correction["suggested_value"] == pytest.approx(20.0)
    assert "approval" in hit.correction["reason"].lower()
    assert "Verify" in hit.recommended_action


# Sessions: unknown IDs 404 without leakage.
def test_session_not_found(client):
    response = client.get("/api/v1/analyze/0" * 8)
    assert response.status_code == 404
    assert "Traceback" not in response.text
    assert "D:" not in response.text and "/home" not in response.text
