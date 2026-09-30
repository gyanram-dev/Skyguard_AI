"""Ensemble scoring-path freeze integration (real frozen Delhi artifacts).

Verifies that the shared single-row scorer used by the probe, the replay
stream and the station snapshot combines the ensemble verdict with the
freeze confirmation, overrides the root-cause class by rule, and reports
the documented severity/confidence — no labels involved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api.dependencies import DataStore
from src.api.services import scoring as SC


@pytest.fixture(scope="module")
def store() -> DataStore:
    """Real frozen artifacts, loaded once (same loader as the API)."""
    return DataStore.load(Path("."))


def test_ensemble_path_confirms_flatline(store: DataStore):
    obs = store.pipeline["delhi"]["obs"]
    tail = obs.tail(400).reset_index(drop=True).copy()
    tail.loc[388:399, "temperature_c"] = 32.5   # 12 identical readings
    frames = SC.build_frames(store, "delhi", tail)
    scored = SC.score_position(frames, "delhi", len(tail) - 1)

    assert scored["freeze"]["confirmed"] is True
    assert scored["freeze"]["variable"] == "temperature"
    assert scored["freeze"]["run_rows"] >= 6
    assert scored["verdict"]["is_anomalous"] is True
    assert scored["verdict"]["trigger"] in ("freeze", "ensemble+freeze")
    assert scored["root_cause"]["class"] == "FROZEN"
    assert scored["root_cause"]["basis"] in ("freeze_rule", "freeze_rule_override")
    assert "FROZEN:" in scored["explanation"]["text"]
    assert scored["verdict"]["severity"] in ("LOW", "MEDIUM", "HIGH")
    assert scored["verdict"]["confidence"] is not None
    assert "probability" in (scored["verdict"]["confidence_basis"] or "") or \
        "margin" in (scored["verdict"]["confidence_basis"] or "")
    # Spatial interpretation still receives an anomalous base state.
    assert scored["spatial_decision"]["base_decision"] == "BASE_ANOMALOUS"


def test_ensemble_path_without_flatline_is_not_freeze_triggered(store: DataStore):
    obs = store.pipeline["delhi"]["obs"]
    tail = obs.tail(400).reset_index(drop=True).copy()
    frames = SC.build_frames(store, "delhi", tail)
    scored = SC.score_position(frames, "delhi", 200)
    assert scored["freeze"]["confirmed"] is False
    assert scored["verdict"]["trigger"] != "freeze"
    if not scored["verdict"]["is_anomalous"]:
        assert scored["verdict"]["severity"] == "NORMAL"
