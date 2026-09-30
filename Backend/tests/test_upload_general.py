"""Phase 21B general input contract: unfamiliar CSVs work without code changes.

Three genuinely different fixtures prove the canonical schema
(station_id/timestamp/temperature_c/pressure_hpa/relative_humidity_pct)
is reached via aliases, unit conversion, and explicit mapping — with ML
honestly unavailable for unseen stations.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api import schemas as S


@pytest.fixture(scope="module")
def client():
    from src.api.app import app

    with TestClient(app) as handle:
        yield handle


def _csv(header, rows):
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join("" if v is None else str(v) for v in row))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _upload(client, payload, filename="station.csv"):
    return client.post("/api/v1/analyze/upload",
                       files={"file": (filename, payload, "text/csv")})


def _confirm(client, sid, mapping, units, label="NEW-01"):
    return client.post(f"/api/v1/analyze/{sid}/confirm",
                       json={"mapping": mapping, "units": units,
                             "station_label": label})


def _run(client, sid):
    return S.AnalysisResult.model_validate(
        client.post(f"/api/v1/analyze/{sid}/run").json())


# Fixture 1: unfamiliar column names + shuffled rows + duplicates.
def test_1_unfamiliar_names_shuffled(client):
    base = pd.date_range("2024-05-01 00:00:00", periods=150, freq="10min")
    rows = [[t.strftime("%Y-%m-%d %H:%M:%S"), 21.0 + (i % 5) * 0.2,
             55.0, 1011.0 + (i % 3) * 0.1] for i, t in enumerate(base)]
    rows = rows[::-1]  # shuffled: newest first
    rows.insert(10, rows[20])  # duplicate row
    header = ["observed_at", "TempCelsius", "hum", "press"]
    sid = _upload(client, _csv(header, rows)).json()["session_id"]
    assert _confirm(client, sid,
                    {"timestamp": "observed_at", "temperature": "TempCelsius",
                     "humidity": "hum", "pressure": "press"},
                    {"temperature": "C", "pressure": "hPa"},
                    label="UNFAMILIAR-01").status_code == 200
    result = _run(client, sid)
    assert result.observations == 151
    assert result.normal + result.anomalies == 151
    assert result.evidence_availability["isolation_forest"] is False
    assert result.evidence_availability["lstm"] is False
    assert result.evidence_availability["spatial"] is False
    assert any("not" in n.lower() and "trained" in n.lower()
               for n in result.notes)


# Fixture 2: different units (Fahrenheit, Pascals) + ISO-Z timestamps
# + multi-station file with unfamiliar station IDs.
def test_2_different_units_multi_station(client):
    def f(c):
        return c * 9.0 / 5.0 + 32.0

    stamps = pd.date_range("2024-06-01T00:00:00Z", periods=80, freq="15min",
                           tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
    rows = []
    for i, t in enumerate(stamps):
        rows.append(["KASAULI-HILLS-99", t, f(18.0 + (i % 4) * 0.3),
                     60.0, 101200.0])
        rows.append(["SHIMLA-RIDGE-07", t, f(15.0 + (i % 6) * 0.2),
                     65.0, 100900.0])
    header = ["site", "recorded_on", "temp_f", "rh_pct", "pressure_pa"]
    sid = _upload(client, _csv(header, rows)).json()["session_id"]
    assert _confirm(client, sid,
                    {"timestamp": "recorded_on", "temperature": "temp_f",
                     "humidity": "rh_pct", "pressure": "pressure_pa",
                     "station": "site"},
                    {"temperature": "F", "pressure": "Pa"},
                    label="HILLS").status_code == 200
    result = _run(client, sid)
    assert result.observations == 160
    assert len(result.stations) == 2
    assert result.evidence_availability["root_cause_model"] is False
    # No trained-model confidence is ever reported for unseen stations.
    for detail in result.anomalies_detail:
        assert detail["confidence"] is None
        assert "Heuristic" in detail["explanation"]


# Fixture 3: unfamiliar station ID + gaps + missing values (cold start honest).
def test_3_new_station_gaps_missing(client):
    stamps = pd.date_range("2024-07-01 00:00:00", periods=120, freq="10min")
    rows = []
    for i, t in enumerate(stamps):
        if 40 <= i < 50:  # communication gap: 100 missing minutes
            continue
        temp = None if i % 25 == 0 else 22.0 + (i % 7) * 0.15
        rows.append([t.strftime("%Y-%m-%d %H:%M:%S"), temp, 58.0, 1010.0])
    header = ["timestamp", "temperature_c", "relative_humidity_pct", "pressure_hpa"]
    sid = _upload(client, _csv(header, rows)).json()["session_id"]
    preview = S.DQPreview.model_validate(_confirm(
        client, sid,
        {"timestamp": "timestamp", "temperature": "temperature_c",
         "humidity": "relative_humidity_pct", "pressure": "pressure_hpa"},
        {"temperature": "C", "pressure": "hPa"},
        label="NEWHO-42").json())
    assert preview.large_gaps >= 1
    assert preview.missing["temperature"] >= 1
    result = _run(client, sid)
    assert result.observations == 110
    assert result.station_label == "NEWHO-42"
    assert result.evidence_availability["ensemble"] is False


# Fixture 4: space-separated UTC-offset timestamps (pandas/GHCNh default
# output, e.g. "2022-01-01 00:00:00+00:00") must confirm and analyze;
# per-station rows/anomalies must stay isolated.
def test_4_utc_offset_multi_station(client):
    base = pd.date_range("2024-08-01 00:00:00", periods=100, freq="30min",
                         tz="UTC")
    rows = []
    for i, t in enumerate(base):
        stamp = t.strftime("%Y-%m-%d %H:%M:%S%z")
        rows.append([stamp, 29.0 + (i % 4) * 0.2, 60.0, 1008.0, "Bhopal"])
        rows.append([stamp, 31.0 + (i % 5) * 0.2, 55.0, 1006.0, "Jaipur"])
    header = ["timestamp", "temperature", "humidity", "pressure", "station"]
    sid = _upload(client, _csv(header, rows)).json()["session_id"]
    assert _confirm(client, sid,
                    {"timestamp": "timestamp", "temperature": "temperature",
                     "humidity": "humidity", "pressure": "pressure"},
                    {"temperature": "C", "pressure": "hPa"},
                    label="OFFSET-01").status_code == 200
    result = _run(client, sid)
    assert result.observations == 200
    by_station = {p["station"]: p for p in result.stations}
    assert by_station["Bhopal"]["rows"] == 100
    assert by_station["Jaipur"]["rows"] == 100
    for detail in result.anomalies_detail:
        assert detail["station"] in ("Bhopal", "Jaipur")
