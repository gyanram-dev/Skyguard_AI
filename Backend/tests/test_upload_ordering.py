"""Phase 20.1 ordering tests: chronological normalization + multi-station.

A seeded 3-station, 15-minute controlled dataset (duplicates, missing
block, spike, frozen segment, drift, cross-variable inconsistency) is
analyzed sorted and shuffled: analytical results must be identical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api import schemas as S

STATIONS = ["PATNA-TEST-01", "JAIPUR-TEST-01", "BHOPAL-TEST-01"]


@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan (startup loads frozen artifacts once)."""
    from src.api.app import app

    with TestClient(app) as handle:
        yield handle


def controlled_rows():
    """Deterministic multi-station fixture (seeded, no randomness on rerun)."""
    rng = np.random.default_rng(20240501)
    rows = []
    for station in STATIONS:
        stamps = pd.date_range("2024-05-01 00:00:00", periods=200, freq="15min")
        temp = 25.0 + 3.0 * np.sin(np.arange(200) / 15.0) + rng.normal(0, 0.15, 200)
        hum = 60.0 + rng.normal(0, 0.8, 200)
        pres = 1008.0 + rng.normal(0, 0.2, 200)
        if station == "PATNA-TEST-01":
            temp[50:60] = np.nan
            temp[100] = 60.0
            temp[120:150] = temp[119]
            hum[150] = 95.0
        if station == "JAIPUR-TEST-01":
            temp[100:] = temp[100:] + np.arange(100) * 0.05
        for i in range(200):
            rows.append({
                "station_id": station,
                "timestamp": stamps[i].strftime("%Y-%m-%d %H:%M:%S"),
                "temperature": None if np.isnan(temp[i]) else round(float(temp[i]), 2),
                "humidity": round(float(hum[i]), 1),
                "pressure": round(float(pres[i]), 1),
            })
    for dup in (rows[10], rows[250], rows[500]):
        rows.append(dict(dup))
    return rows


def to_csv(rows):
    lines = ["station_id,timestamp,temperature,humidity,pressure"]
    for row in rows:
        lines.append(",".join("" if row[k] is None else str(row[k])
                              for k in ("station_id", "timestamp", "temperature",
                                        "humidity", "pressure")))
    return ("\n".join(lines) + "\n").encode("utf-8")


def analyze(client, payload, label="CONTROLLED"):
    sid = client.post("/api/v1/analyze/upload",
                      files={"file": ("controlled.csv", payload, "text/csv")}).json()["session_id"]
    confirm = client.post(
        f"/api/v1/analyze/{sid}/confirm",
        json={"mapping": {"timestamp": "timestamp", "temperature": "temperature",
                          "humidity": "humidity", "pressure": "pressure"},
              "units": {"temperature": "C", "pressure": "hPa"},
              "station_label": label})
    assert confirm.status_code == 200, confirm.text
    preview = S.DQPreview.model_validate(confirm.json())
    run = client.post(f"/api/v1/analyze/{sid}/run")
    assert run.status_code == 200, run.text
    return preview, S.AnalysisResult.model_validate(run.json())


@pytest.fixture(scope="module")
def controlled_pair(client):
    rows = controlled_rows()
    ordered = sorted(rows, key=lambda r: (r["station_id"], r["timestamp"]))
    shuffled = list(rows)
    rng = np.random.default_rng(99)
    rng.shuffle(shuffled)
    preview_s, result_s = analyze(client, to_csv(ordered), label="SORTED")
    preview_x, result_x = analyze(client, to_csv(shuffled), label="SHUFFLED")
    return (preview_s, result_s), (preview_x, result_x)


def key_anomalies(result):
    return sorted((a.timestamp, a.station, a.root_cause_estimate,
                   round(a.score or 0.0, 4)) for a in result.anomalies_detail)


# 11/14. Sorted vs shuffled: identical DQ and identical anomalies.
def test_sorted_shuffled_invariance(controlled_pair):
    (preview_s, result_s), (preview_x, result_x) = controlled_pair
    assert preview_s.rows == preview_x.rows == 603
    assert preview_s.cadence_min == preview_x.cadence_min == 15.0
    assert preview_s.duplicates == preview_x.duplicates == 3
    assert preview_s.missing == preview_x.missing
    assert preview_s.large_gaps == preview_x.large_gaps
    assert preview_s.invalid_timestamps == preview_x.invalid_timestamps == 0
    assert preview_s.ml_eligible == preview_x.ml_eligible
    assert preview_s.quality_counts == preview_x.quality_counts
    assert result_s.observations == result_x.observations == 603
    assert result_s.anomalies == result_x.anomalies
    assert result_s.normal == result_x.normal
    assert result_s.breakdown == result_x.breakdown
    assert key_anomalies(result_s) == key_anomalies(result_x)


# 4/5/13. Chronological cadence ~15 min, exact duplicate count, high eligibility.
def test_controlled_characteristics(controlled_pair):
    (preview_s, result_s), _ = controlled_pair
    assert preview_s.cadence_min == 15.0
    assert preview_s.duplicates == 3
    assert preview_s.ml_eligible > 500
    assert preview_s.missing["temperature"] == 10
    by_station = {s["station"]: s for s in preview_s.stations}
    assert set(by_station) == set(STATIONS)
    assert all(s["cadence_min"] == 15.0 for s in by_station.values())


# 9/10/11. Station IDs correct; spike found on the right station/time.
def test_station_attribution(controlled_pair):
    (_, result_s), _ = controlled_pair
    assert {a.station for a in result_s.anomalies_detail} <= set(STATIONS)
    spikes = [a for a in result_s.anomalies_detail
              if a.root_cause_estimate == "SPIKE" and a.timestamp == "2024-05-02 01:00:00"]
    assert len(spikes) == 1
    assert spikes[0].station == "PATNA-TEST-01"
    assert spikes[0].correction is not None


# 7. ISO-8601 T/Z/offset timestamps parse deterministically.
def test_iso_timestamps(client):
    ts = ["2024-03-01T00:00:00", "2024-03-01T00:05:00Z", "2024-03-01T00:10:00+00:00",
          "2024-03-01T00:15:00", "2024-03-01T00:20:00Z"]
    rows = [(t, 20.0 + i * 0.1, 55.0, 1012.0) for i, t in enumerate(ts)]
    lines = ["timestamp,temperature,humidity,pressure"]
    lines += [",".join(str(v) for v in row) for row in rows]
    sid = client.post("/api/v1/analyze/upload",
                      files={"file": ("iso.csv", ("\n".join(lines) + "\n").encode(),
                                            "text/csv")}).json()["session_id"]
    confirm = client.post(
        f"/api/v1/analyze/{sid}/confirm",
        json={"mapping": {"timestamp": "timestamp", "temperature": "temperature",
                          "humidity": "humidity", "pressure": "pressure"},
              "units": {"temperature": "C", "pressure": "hPa"}})
    assert confirm.status_code == 200
    assert confirm.json()["rows"] == 5


# 6. A genuinely missing block stays a detectable gap after sorting.
def test_gap_after_sorting(client):
    head = pd.date_range("2024-04-01 00:00:00", periods=40, freq="15min")
    tail = pd.date_range("2024-04-01 12:00:00", periods=40, freq="15min")
    stamps = [s.strftime("%Y-%m-%d %H:%M:%S") for s in list(head) + list(tail)]
    rng = np.random.default_rng(3)
    rng.shuffle(stamps)
    rows = [(t, 22.0, 58.0, 1010.0) for t in stamps]
    lines = ["timestamp,temperature,humidity,pressure"]
    lines += [",".join(str(v) for v in row) for row in rows]
    sid = client.post("/api/v1/analyze/upload",
                      files={"file": ("gap.csv", ("\n".join(lines) + "\n").encode(),
                                        "text/csv")}).json()["session_id"]
    preview = S.DQPreview.model_validate(client.post(
        f"/api/v1/analyze/{sid}/confirm",
        json={"mapping": {"timestamp": "timestamp", "temperature": "temperature",
                          "humidity": "humidity", "pressure": "pressure"},
              "units": {"temperature": "C", "pressure": "hPa"}}).json())
    assert preview.cadence_min == 15.0
    assert preview.large_gaps >= 1
