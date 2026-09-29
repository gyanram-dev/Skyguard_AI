"""Phase 17 evaluation tests: GET /api/v1/evaluation/summary honesty."""

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


def summary(client) -> dict:
    response = client.get("/api/v1/evaluation/summary")
    assert response.status_code == 200
    return S.EvaluationSummary.model_validate(response.json())


# 1+2. Endpoint 200 with a valid schema.
def test_1_2_status_and_schema(client):
    body = summary(client)
    assert body.data_mode == "benchmark_evaluation"


# 3+4. Only Indian Delhi evaluation is exposed by the product API.
def test_3_4_id_ood_present(client):
    body = summary(client)
    assert {row.dataset for row in body.generalization} == {"delhi"}
    assert {row.dataset for row in body.detection} == {"delhi"}
    for dataset in ("delhi",):
        row = next(r for r in body.generalization if r.dataset == dataset)
        assert row.id_f1 is not None and row.ood_f1 is not None
        assert row.id_event_recall is not None and row.ood_event_recall is not None
        det = [d for d in body.detection if d.dataset == dataset]
        assert {d.split for d in det} == {"test_in_distribution", "test_generalization"}


# 5. Missing metrics stay null (event recall has no reference values).
def test_5_missing_stays_null(client):
    body = summary(client)
    refs = [m for m in body.model_comparison if m.method != "ensemble"]
    assert refs
    assert all(m.event_recall is None for m in refs)


# 6. Provenance and data mode are present.
def test_6_provenance(client):
    body = summary(client)
    assert set(body.provenance) >= {"detection", "model_comparison", "generalization",
                                    "root_cause", "runtime"}
    assert all(body.provenance.values())


# 7. No filesystem paths leak into the response.
def test_7_no_path_leak(client):
    import json

    response = client.get("/api/v1/evaluation/summary")
    text = json.dumps(response.json())
    assert "D:" not in text and "/home" not in text and "C:" not in text
    assert ".csv" in text  # provenance cites report filenames only


# 8+9. Read-only: repeated calls identical, models untouched.
def test_8_9_read_only(client):
    first = client.get("/api/v1/evaluation/summary").json()
    second = client.get("/api/v1/evaluation/summary").json()
    assert first == second
    import hashlib
    from pathlib import Path

    digest = hashlib.sha256(
        (Path("models/isolation_forest/delhi_isolation_forest.joblib"))
        .read_bytes()).hexdigest()
    client.get("/api/v1/evaluation/summary")
    assert hashlib.sha256(
        (Path("models/isolation_forest/delhi_isolation_forest.joblib"))
        .read_bytes()).hexdigest() == digest


# 10. Values match the authoritative artifacts exactly.
def test_10_values_match_artifacts(client):
    body = summary(client)
    det = pd.read_csv("reports/ensemble/ensemble_metrics.csv")
    ref = det[(det["scope"] == "overall") & (det["group"] == "all")
              & (det["method"] == "ens_median")
              & (det["dataset"] == "delhi")
              & (det["split"] == "test_generalization")].iloc[0]
    got = next(d for d in body.detection
               if d.dataset == "delhi" and d.split == "test_generalization")
    assert got.precision == pytest.approx(float(ref["precision"]))
    assert got.recall == pytest.approx(float(ref["recall"]))
    assert got.f1 == pytest.approx(float(ref["f1"]))
    assert got.event_recall == pytest.approx(0.6714285714285714)
    rc = pd.read_csv("reports/root_cause/root_cause_metrics.csv")
    rc_ref = rc[(rc["scope"] == "classifier_operating")
                & (rc["dataset"] == "delhi")
                & (rc["split"] == "test_generalization")].iloc[0]
    rc_got = next(r for r in body.root_cause
                  if r.dataset == "delhi" and r.split == "test_generalization")
    assert rc_got.unknown_rate == pytest.approx(float(rc_ref["unknown_rate"]))
    assert rc_got.macro_f1 == pytest.approx(float(rc_ref["macro_f1"]))
