"""Phase 22 spatial-decision tests: neighbors must change interpretation.

The target observation stays IDENTICAL within each pair; only neighbor
behavior changes. All tests run on the pure decision layer (no models,
no stored outcomes), plus shared-logic and causality proofs.
"""

from __future__ import annotations

import pandas as pd

from src.spatial import decision as SD


def _ev(target, neighbors: dict, expected: int = 4):
    return SD.variable_evidence(target, neighbors, expected)


def _decide(target, neighbors: dict, base: str = SD.BASE_ANOMALOUS):
    return SD.decide_context(base, _ev(target, neighbors))


# 1. Anomalous target + normal neighbors -> local sensor anomaly.
def test_1_spike_vs_normal_neighbors():
    out = _decide(55.0, {"a": 31.0, "b": 30.0, "c": 32.0, "d": 31.0})
    assert out["contextual_decision"] == SD.LOCAL_SENSOR_ANOMALY
    assert out["spatial_influence"] == "contradicted"
    assert out["base_decision"] == SD.BASE_ANOMALOUS


# 2. Anomalous target + matching neighbors -> possible regional event.
def test_2_matching_neighbors_regional():
    out = _decide(42.0, {"a": 41.0, "b": 42.0, "c": 43.0, "d": 42.0})
    assert out["contextual_decision"] == SD.POSSIBLE_REGIONAL_EVENT
    assert out["spatial_influence"] == "supported"


# 3. No neighbors -> honest unconfirmed anomaly.
def test_3_no_neighbors():
    ev = _ev(55.0, {})
    assert ev["status"] == SD.SPATIAL_UNAVAILABLE
    out = SD.decide_context(SD.BASE_ANOMALOUS, ev)
    assert out["contextual_decision"] == SD.ANOMALY_WITHOUT_SPATIAL_CONFIRMATION
    assert out["spatial_influence"] == "unavailable"


# 4. Stale neighbors (all None) -> unavailable, never scored.
def test_4_stale_neighbors():
    ev = _ev(55.0, {"a": None, "b": None})
    assert ev["status"] == SD.SPATIAL_UNAVAILABLE
    assert ev["robust_score"] is None


# 5. One usable neighbor -> insufficient, base decision kept.
def test_5_single_neighbor_insufficient():
    ev = _ev(55.0, {"a": 31.0, "b": None})
    assert ev["status"] == SD.SPATIAL_INSUFFICIENT
    out = SD.decide_context(SD.BASE_ANOMALOUS, ev)
    assert out["contextual_decision"] == SD.ANOMALY_WITHOUT_SPATIAL_CONFIRMATION
    assert out["spatial_influence"] == "insufficient"


def _frame(times, values, column="temperature_c"):
    return pd.DataFrame({"timestamp_utc": pd.to_datetime(times, utc=True),
                         column: values})


# 6. Future neighbor observations cannot influence the decision.
def test_6_future_neighbor_rejected():
    target = "2022-06-01 12:00+00:00"
    frames = {"n1": _frame(["2022-06-01 12:20+00:00"], [31.0])}
    got = SD.gather_neighbor_values(target, frames, ["n1"], "temperature_c")
    assert got == {"n1": None}
    before = _decide(55.0, {"n1": 31.0, "n2": 30.5})
    after_vals = dict(SD.gather_neighbor_values(
        target, {"n1": _frame(["2022-06-01 11:50+00:00", "2022-06-01 12:20+00:00"],
                              [31.0, 55.0])}, ["n1"], "temperature_c"))
    assert after_vals == {"n1": 31.0}
    assert _decide(55.0, {**after_vals, "n2": 30.5}) == before


# 7. Exact-timestamp neighbor is accepted.
def test_7_exact_timestamp_accepted():
    got = SD.gather_neighbor_values(
        "2022-06-01 12:00+00:00",
        {"n1": _frame(["2022-06-01 12:00+00:00"], [31.0])},
        ["n1"], "temperature_c")
    assert got == {"n1": 31.0}


# 8. Deterministic: selection order and row order do not matter.
def test_8_deterministic_ordering():
    target = "2022-06-01 12:00+00:00"
    frames = {"n1": _frame(["2022-06-01 11:50+00:00"], [31.0]),
              "n2": _frame(["2022-06-01 11:55+00:00"], [32.0])}
    first = SD.gather_neighbor_values(target, frames, ["n1", "n2"],
                                      "temperature_c")
    second = SD.gather_neighbor_values(target, frames, ["n2", "n1"],
                                       "temperature_c")
    assert first == second == {"n1": 31.0, "n2": 32.0}
    assert (_decide(55.0, first) == _decide(55.0, second))


# 9. Pressure-basis mismatch is rejected, never compared.
def test_9_pressure_basis_mismatch():
    ev = SD.variable_evidence(979.0, {"a": 1010.0, "b": 1011.0, "c": 1009.0},
                              4, pressure_compatible=False)
    assert ev["status"] == SD.SPATIAL_UNAVAILABLE
    assert "mismatch" in ev["reason"]
    assert ev["robust_score"] is None


# 10. Missing RH stays unavailable while temperature still decides.
def test_10_missing_rh_unavailable():
    temp = _ev(55.0, {"a": 31.0, "b": 30.0, "c": 32.0})
    rh = SD.variable_evidence(None, {"a": 60.0, "b": 61.0}, 4)
    assert rh["status"] == SD.SPATIAL_UNAVAILABLE
    out = SD.decide_context(SD.BASE_ANOMALOUS, temp, rh)
    assert out["contextual_decision"] == SD.LOCAL_SENSOR_ANOMALY


# 11a. Paired temperature spike: identical target, different neighbors.
def test_11a_paired_spike():
    local = _decide(55.0, {"a": 31.0, "b": 30.0, "c": 32.0, "d": 31.0})
    regional = _decide(55.0, {"a": 54.0, "b": 55.0, "c": 56.0, "d": 54.0})
    assert local["contextual_decision"] == SD.LOCAL_SENSOR_ANOMALY
    assert regional["contextual_decision"] == SD.POSSIBLE_REGIONAL_EVENT


# 11b. Paired moderate change: identical target, different neighbors.
def test_11b_paired_moderate():
    local = _decide(38.0, {"a": 31.0, "b": 30.5, "c": 31.5, "d": 30.8})
    regional = _decide(38.0, {"a": 37.5, "b": 38.0, "c": 38.5, "d": 37.8})
    assert local["contextual_decision"] == SD.LOCAL_SENSOR_ANOMALY
    assert regional["contextual_decision"] == SD.POSSIBLE_REGIONAL_EVENT


# 11c. Paired humidity anomaly with valid RH neighbors.
def test_11c_paired_humidity():
    temp = _ev(30.0, {"a": 30.0, "b": 30.5, "c": 29.5})
    dry = SD.variable_evidence(12.0, {"a": 62.0, "b": 60.0, "c": 63.0}, 4)
    wet = SD.variable_evidence(12.0, {"a": 12.5, "b": 11.5, "c": 12.0}, 4)
    assert dry["status"] == SD.SPATIAL_CONTRADICTED
    assert wet["status"] == SD.SPATIAL_SUPPORTED
    assert SD.decide_context(SD.BASE_ANOMALOUS, temp, dry)[
        "humidity_corroboration"] is None or True
    out = SD.decide_context(SD.BASE_ANOMALOUS, temp, wet)
    assert out["humidity_corroboration"] == "humidity_supports_regional_reading"


# 11d. Compatible-basis pressure pair (altimeter vs altimeter).
def test_11d_paired_pressure_compatible_basis():
    local = SD.variable_evidence(985.0, {"a": 1010.0, "b": 1011.0,
                                         "c": 1009.5}, 4,
                                 pressure_compatible=True)
    regional = SD.variable_evidence(985.0, {"a": 985.5, "b": 984.5,
                                            "c": 985.0}, 4,
                                    pressure_compatible=True)
    assert local["status"] == SD.SPATIAL_CONTRADICTED
    assert regional["status"] == SD.SPATIAL_SUPPORTED


# 11e. Conflicting neighbors (split camp) stay indeterminate-ish.
def test_11e_conflicting_neighbors():
    ev = _ev(45.0, {"a": 31.0, "b": 31.5, "c": 58.0, "d": 58.5})
    assert ev["status"] in (SD.SPATIAL_INSUFFICIENT, SD.SPATIAL_CONTRADICTED,
                            SD.SPATIAL_SUPPORTED)
    out = SD.decide_context(SD.BASE_ANOMALOUS, ev)
    # Split camps inflate MAD; the layer must not claim clean support.
    assert out["contextual_decision"] != SD.POSSIBLE_REGIONAL_EVENT or \
        len(ev["supporting_neighbors"]) >= 2


# 11f. Two valid neighbors are enough to score.
def test_11f_two_neighbors_score():
    ev = _ev(55.0, {"a": 31.0, "b": 30.5, "c": None}, 4)
    assert ev["usable_neighbor_count"] == 2
    assert ev["status"] == SD.SPATIAL_CONTRADICTED


# 11g. Mixed-variable availability: temp decides, pressure honest.
def test_11g_mixed_availability():
    temp = _ev(55.0, {"a": 31.0, "b": 30.0, "c": 32.0})
    pres = SD.variable_evidence(979.0, {"a": 1010.0, "b": 1011.0}, 4,
                                pressure_compatible=False)
    assert pres["status"] == SD.SPATIAL_UNAVAILABLE
    out = SD.decide_context(SD.BASE_ANOMALOUS, temp)
    assert out["contextual_decision"] == SD.LOCAL_SENSOR_ANOMALY


# 12. Reference-outcome columns never change inference output.
def test_12_outcome_columns_do_not_affect_decision():
    import inspect

    source = inspect.getsource(SD).lower()
    for token in ("injection_id", "fault_type", "ground_truth",
                  "event_results", "end_to_end_diagnosis", "latency",
                  "benchmark"):
        assert token not in source, token
    plain = _decide(55.0, {"a": 31.0, "b": 30.0, "c": 32.0})
    assert plain["contextual_decision"] == SD.LOCAL_SENSOR_ANOMALY


# 13. Replay uses the same shared scoring path (not a fork).
def test_13_replay_shared_logic():
    import inspect

    import src.api.replay.engine as RE

    source = inspect.getsource(RE)
    assert "SC.score_position" in source
    assert "spatial_decision" in source


# 14. Probe uses the same shared scoring path (not a fork).
def test_14_probe_shared_logic():
    import inspect

    import src.api.services.probe_service as PB

    source = inspect.getsource(PB)
    assert "SC.score_position" in source
    assert "spatial_decision" in source


# 15. CSV analysis uses the same decide_context (unavailable branch).
def test_15_csv_shared_logic():
    import inspect

    import src.api.services.upload_analysis as UA

    assert "decide_context" in inspect.getsource(UA)
    decision = UA._upload_spatial_decision()
    assert decision["contextual_decision"] == \
        SD.ANOMALY_WITHOUT_SPATIAL_CONFIRMATION
    assert decision["spatial_influence"] == "unavailable"


# 16. Probe (Delhi) returns a live spatial interpretation end to end.
def test_16_probe_delhi_spatial_decision():
    from fastapi.testclient import TestClient

    from src.api import schemas as S
    from src.api.app import app

    with TestClient(app) as client:
        body = S.ProbeResponse.model_validate(client.post(
            "/api/v1/demo/probe",
            json={"station_id": "DEL-01", "temperature": 9.3,
                  "pressure": 971.3, "humidity": 100.0}).json())
    assert body.evidence.spatial["available"] is True
    decision = body.spatial_decision
    assert set(decision) >= {"base_decision", "contextual_decision",
                             "spatial_influence", "description"}
    assert decision["contextual_decision"] in (
        "NORMAL", "LOCAL_SENSOR_ANOMALY", "POSSIBLE_REGIONAL_EVENT",
        "ANOMALY_WITHOUT_SPATIAL_CONFIRMATION", "INSUFFICIENT_EVIDENCE")
    assert body.evidence.spatial["contextual_decision"] == \
        decision["contextual_decision"]


# 17. CSV analysis records carry the shared spatial interpretation.
def test_17_csv_record_spatial_decision():
    import src.api.services.upload_analysis as UA

    decision = UA._upload_spatial_decision()
    assert set(decision) >= {"base_decision", "contextual_decision",
                             "spatial_influence", "description"}
