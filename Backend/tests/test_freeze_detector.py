"""Critical-gap tests: freeze detector, severity bands, path integration.

Covers the deterministic freeze rule (causality, gap safety, RH saturation
exclusion, documented severity/confidence), its integration into the
calibrated station detector and the live path, and the ensemble severity
presentation bands. No TensorFlow models are required.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from src.detection import freeze as FE
from src.detection.station_statistical import StationStatisticalDetector
from src.ensemble import severity as ES
from src.live import history as LH
from src.live import inference as LI
from src.live import obs as LO


def _frame(values: np.ndarray, cadence_min: float = 30.0) -> pd.DataFrame:
    """Sensor frame with ramps on pressure/humidity (never accidentally flat)."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    stamps = pd.date_range("2024-01-01 00:00:00", periods=n,
                           freq=f"{int(cadence_min)}min")
    return pd.DataFrame({
        "timestamp": stamps.strftime("%Y-%m-%d %H:%M:%S"),
        "temperature_c": values,
        "pressure_hpa": 1000.0 + np.linspace(0.0, 9.0, n),
        "relative_humidity_pct": 60.0 + np.linspace(0.0, 9.0, n),
    })


# 1. Causal confirmation: only from the sixth identical reading onward.
def test_run_confirmed_only_from_sixth_reading():
    values = np.arange(20, dtype=float)
    values[5:15] = 10.0
    run, code = FE.scan_frame(_frame(values))
    assert (run[:5] == 0).all()
    assert (run[5:10] == 0).all()          # rows 1..5 of the run
    assert run[10] == 6 and code[10] == 1  # sixth identical reading
    assert run[14] == 10
    assert run[15] == 0                     # run ended


# 2. NaN and communication-gap rows both terminate runs.
def test_nan_and_gap_reset_runs():
    frame = _frame(np.full(30, 7.0))
    frame.loc[10, "temperature_c"] = np.nan
    run, _ = FE.scan_frame(frame)
    assert run[9] == 10 and run[10] == 0
    assert run[15] == 0 and run[16] == 6   # new run restarts after the NaN

    gap = np.zeros(30, dtype=bool)
    gap[10] = True
    run2, _ = FE.scan_frame(_frame(np.full(30, 7.0)), gap_rows=gap)
    assert run2[9] == 10 and run2[10] == 0
    assert run2[16] == 6


# 3. Saturated relative humidity is never a freeze (measured background).
def test_rh_saturation_excluded():
    frame = _frame(np.arange(20, dtype=float))
    frame["relative_humidity_pct"] = 100.0
    run, _ = FE.scan_frame(frame)
    assert int(run.max()) == 0

    frame2 = _frame(np.arange(20, dtype=float))
    frame2.loc[5:14, "relative_humidity_pct"] = 42.0
    run2, code2 = FE.scan_frame(frame2)
    assert run2[10] == 6 and code2[10] == 3  # humidity variable code


# 4. Documented confidence and severity edges.
def test_confidence_and_severity_are_documented():
    assert FE.confidence_for(5) is None
    assert FE.confidence_for(6) == 0.5
    assert FE.confidence_for(12) == round(12 / 18, 4)
    assert FE.confidence_for(30) > FE.confidence_for(12)
    assert FE.severity_for(5, 30.0) is None
    assert FE.severity_for(6, 30.0) == "LOW"
    assert FE.severity_for(12, 30.0) == "HIGH"    # 6 h at 30-min cadence
    assert FE.severity_for(12, 5.0) == "MEDIUM"
    assert FE.severity_for(72, 5.0) == "HIGH"


# 5. Signal-health summary states are documented and reachable.
def test_signal_health_summary_states():
    rng = np.random.default_rng(7)
    frame = _frame(20 + np.sin(np.arange(300) / 5.0) + rng.normal(0, 0.1, 300),
                   cadence_min=5.0)
    assert FE.summarise(frame, 5.0)["state"] == "NO_FLATLINE_EVIDENCE"

    frame.loc[100:107, "temperature_c"] = 25.0
    summary = FE.summarise(frame, 5.0)
    assert summary["state"] == "ISOLATED_FLATLINE"
    assert summary["freeze_runs"] == 1
    assert summary["affected_variables"] == ["temperature"]
    assert summary["longest_run_hours"] == 0.67    # 8 rows at 5 min
    assert summary["fast_rule_applicable"] is True

    frame.loc[200:207, "pressure_hpa"] = 1001.0
    assert FE.summarise(frame, 5.0)["state"] == "REPEATED_FLATLINES"

    long_frame = _frame(20 + np.sin(np.arange(300) / 5.0)
                        + rng.normal(0, 0.1, 300), cadence_min=5.0)
    long_frame.loc[50:130, "temperature_c"] = 25.0   # 81 rows = 6.75 h
    assert FE.summarise(long_frame, 5.0)["state"] == "PROLONGED_FLATLINE"
    assert FE.summarise(frame.head(50), 5.0)["state"] == "INSUFFICIENT_HISTORY"


# 5b. Slow cadences use the DQ 6-hour gate, never the fast rule.
def test_slow_cadence_uses_dq_candidate_gate():
    rng = np.random.default_rng(13)
    frame = _frame(20 + np.sin(np.arange(300) / 5.0) + rng.normal(0, 0.1, 300),
                   cadence_min=30.0)
    frame.loc[100:107, "temperature_c"] = 25.0      # 8 rows = 4 h
    summary = FE.summarise(frame, 30.0)
    assert summary["fast_rule_applicable"] is False
    assert summary["rule"] == "dq_6h_candidate_gate"
    assert summary["state"] == "NO_FLATLINE_EVIDENCE"

    frame.loc[150:169, "temperature_c"] = 26.0      # 20 rows = 10 h
    summary = FE.summarise(frame, 30.0)
    assert summary["min_run_rows"] == 12             # 6 h at 30-min cadence
    assert summary["state"] == "PROLONGED_FLATLINE"
    assert summary["freeze_runs"] == 1

    assert FE.applicable(30.0) is False
    empty = FE.row_evidence(np.zeros(10, dtype=int), np.zeros(10, dtype=np.int8),
                            0, 30.0)
    assert empty["confirmed"] is False and empty["applicable"] is False


def _artifact(cadence_min: float) -> dict:
    """Minimal detector artifact binding the calibrated cadence."""
    return {
        "detector_type": "Statistical Baseline",
        "detector_method": "statistical",
        "station_id": "TEST-01",
        "backend_station_id": "TEST0000",
        "city": "Test City",
        "cadence_min": cadence_min,
        "pressure_semantics": "altimeter_qnh_hpa",
        "pressure_column": "altimeter_setting_hpa",
        "rh_provenance": "REPORTED",
        "data_mode": "HISTORICAL",
    }


# 6. Calibrated station detector surfaces the freeze trigger + cause.
def test_station_detector_confirms_flat_run():
    rng = np.random.default_rng(11)
    n = 400
    temp = 25 + 3 * np.sin(np.arange(n) / 12.0) + rng.normal(0, 0.2, n)
    temp[200:212] = 26.0
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="5min")
                            .strftime("%Y-%m-%d %H:%M:%S"),
        "temperature_c": temp,
        "pressure_hpa": 1008 + rng.normal(0, 0.2, n),
        "relative_humidity_pct": 60 + rng.normal(0, 0.5, n),
    })
    detector = StationStatisticalDetector(_artifact(5.0))
    results = detector.score_frame(frame)

    assert not results[0]["freeze"]["confirmed"]
    assert not any(r["freeze"]["confirmed"] for r in results[200:203])
    confirmed = [r for r in results[200:212] if r["freeze"]["confirmed"]]
    assert confirmed, "a 12-row flat temperature run must confirm a freeze"
    hit = confirmed[0]
    assert hit["anomaly"] is True
    assert hit["trigger"] in ("freeze", "statistical+freeze")
    assert hit["pattern_estimate"] == "FROZEN"
    assert hit["primary_reason"].startswith("FROZEN:")
    assert hit["freeze"]["variable"] == "temperature"
    assert hit["freeze"]["run_rows"] >= FE.MIN_RUN_ROWS
    assert hit["severity"] in ("LOW", "MEDIUM", "HIGH")


# 7. Live path confirms the same freeze and reports it honestly.
def test_live_inference_confirms_freeze():
    hist = LH.StationHistory("S1")
    start = dt.datetime(2026, 9, 29, 0, 0, tzinfo=dt.timezone.utc)
    for i in range(40):
        ts = start + dt.timedelta(minutes=5 * i)
        temp = 29.5 if i >= 32 else 29.0 + 0.05 * (i % 3)
        hist.add(LO.CanonicalObservation(
            station_id="S1", timestamp=ts, temperature_c=temp,
            pressure_hpa=1005.0 + 0.01 * i,
            relative_humidity_pct=60.0 + 0.05 * i, source="CONTROLLED",
            source_station_id="S1",
            source_observation_id=f"S1-{i}", pressure_basis="station_level",
            received_at=ts, raw_timestamp=ts.isoformat()))
    scored = LI.score_station(hist, {"S1": hist}, 5.0)
    assert scored["verdict"] == "ANOMALY"
    assert scored["freeze"]["confirmed"] is True
    assert scored["freeze"]["variable"] == "temperature"
    assert scored["pattern"]["estimate"] == "FROZEN"
    assert scored["trigger"] in ("freeze", "statistical+freeze")
    assert "FROZEN:" in scored["explanation"]


# 8. Ensemble severity bands are documented and bounded.
def test_ensemble_severity_bands():
    assert ES.severity_for(0.5, 1.0, False) == "NORMAL"
    assert ES.severity_for(1.0, 1.0, True) == "LOW"
    assert ES.severity_for(1.3, 1.0, True) == "MEDIUM"
    assert ES.severity_for(2.0, 1.0, True) == "HIGH"
    assert ES.severity_for(3.0, 1.0, True) == "CRITICAL"
    assert ES.severity_for(None, 1.0, True) is None
    assert ES.severity_for(1.0, 0.0, True) is None
    assert ES.rank("HIGH") > ES.rank("LOW") > ES.rank(None)
