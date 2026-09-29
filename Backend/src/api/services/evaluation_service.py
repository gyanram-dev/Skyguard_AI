"""Evaluation evidence service: read-only presentation of frozen reports.

Loads validated Phase 6/7/9/10/11/16 artifacts once and serves them
verbatim (NaN stays null, never estimated). No recomputation, no
retraining, no threshold changes. Missing artifacts fail fast instead
of serving invented metrics.
"""

from __future__ import annotations

import json
import logging
import math

import pandas as pd

logger = logging.getLogger("skyguard.evaluation")

REQUIRED_FILES = [
    "reports/ensemble/ensemble_metrics.csv",
    "reports/ensemble/event_metrics.csv",
    "reports/ensemble/ood_metrics.csv",
    "reports/ensemble/phase6_phase7_phase9_comparison.csv",
    "reports/root_cause/root_cause_metrics.csv",
    "reports/replay/performance.json",
]

REF_METHOD_LABELS = {
    "zscore": "statistical_zscore",
    "iqr": "statistical_iqr",
    "iforest": "isolation_forest",
    "lstm_ae": "lstm_autoencoder",
}

_CACHE: dict | None = None


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _per_class(raw) -> dict:
    """Parse the stored per-class JSON (NaN literals become null)."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return {}
    try:
        parsed = json.loads(str(raw).replace("NaN", "null"))
    except (ValueError, TypeError):
        return {}
    out = {}
    for cls, stats in (parsed.items() if isinstance(parsed, dict) else []):
        if not isinstance(stats, dict):
            continue
        out[str(cls)] = {k: _num(stats.get(k)) for k in
                         ("precision", "recall", "f1", "support")}
    return out


def load_evidence(root) -> dict:
    """Load and cache every frozen evidence table."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    missing = [rel for rel in REQUIRED_FILES if not (root / rel).exists()]
    if missing:
        raise RuntimeError(f"Missing evaluation artifacts: {missing}")
    det = pd.read_csv(root / "reports" / "ensemble" / "ensemble_metrics.csv")
    events = pd.read_csv(root / "reports" / "ensemble" / "event_metrics.csv")
    ood = pd.read_csv(root / "reports" / "ensemble" / "ood_metrics.csv")
    comp = pd.read_csv(root / "reports" / "ensemble" / "phase6_phase7_phase9_comparison.csv")
    rc = pd.read_csv(root / "reports" / "root_cause" / "root_cause_metrics.csv")
    perf = json.loads((root / "reports" / "replay" / "performance.json")
                      .read_text(encoding="utf-8"))

    det_overall = det[(det["scope"] == "overall") & (det["group"] == "all")
                      & (det["method"] == "ens_median")
                      & (det["dataset"] == "delhi")]
    detection = []
    for _, row in det_overall.iterrows():
        ev = events[(events["dataset"] == row["dataset"])
                    & (events["split"] == row["split"])
                    & (events["method"] == "ens_median")
                    & (events["scope"] == "event") & (events["group"] == "all")]
        ev_row = ev.iloc[0] if len(ev) else None
        detection.append({
            "dataset": str(row["dataset"]), "split": str(row["split"]),
            "method": "ens_median",
            "precision": _num(row.get("precision")), "recall": _num(row.get("recall")),
            "f1": _num(row.get("f1")), "fpr": _num(row.get("fpr")),
            "fnr": _num(row.get("fnr")),
            "events": int(ev_row["events"]) if ev_row is not None else None,
            "events_detected": int(ev_row["events_detected"])
            if ev_row is not None else None,
            "event_recall": _num(ev_row["event_recall"]) if ev_row is not None else None,
            "latency_median_min": _num(ev_row["latency_median_min"])
            if ev_row is not None else None,
        })

    comp_overall = comp[(comp["scope"] == "overall")
                        & (comp["ensemble_method"] == "ens_median")
                        & (comp["dataset"] == "delhi")]
    model_comparison = []
    for _, row in comp_overall.iterrows():
        entry = {"dataset": str(row["dataset"]), "split": str(row["split"]),
                 "reference_method": str(row["reference_method"]),
                 "method": REF_METHOD_LABELS.get(str(row["reference_method"]),
                                                 str(row["reference_method"])),
                 "precision": _num(row.get("ref_precision")),
                 "recall": _num(row.get("ref_recall")),
                 "f1": _num(row.get("ref_f1")),
                 "event_recall": None,
                 "fpr": _num(row.get("ref_fpr"))}
        model_comparison.append(entry)
    for item in detection:
        model_comparison.append({
            "dataset": item["dataset"], "split": item["split"],
            "reference_method": "ens_median", "method": "ensemble",
            "precision": item["precision"], "recall": item["recall"],
            "f1": item["f1"], "event_recall": item["event_recall"],
            "fpr": item["fpr"]})

    generalization = []
    ood_overall = ood[(ood["method"] == "ens_median")
                      & (ood["dataset"] == "delhi")]
    for _, row in ood_overall.iterrows():
        ev_id = events[(events["dataset"] == row["dataset"])
                       & (events["split"] == "test_in_distribution")
                       & (events["method"] == "ens_median")
                       & (events["scope"] == "event") & (events["group"] == "all")]
        ev_ood = events[(events["dataset"] == row["dataset"])
                        & (events["split"] == "test_generalization")
                        & (events["method"] == "ens_median")
                        & (events["scope"] == "event") & (events["group"] == "all")]
        generalization.append({
            "dataset": str(row["dataset"]), "method": "ens_median",
            "id_precision": _num(row.get("id_precision")),
            "id_recall": _num(row.get("id_recall")),
            "id_f1": _num(row.get("id_f1")),
            "id_event_recall": _num(ev_id.iloc[0]["event_recall"]) if len(ev_id) else None,
            "ood_precision": _num(row.get("ood_precision")),
            "ood_recall": _num(row.get("ood_recall")),
            "ood_f1": _num(row.get("ood_f1")),
            "ood_event_recall": _num(ev_ood.iloc[0]["event_recall"])
            if len(ev_ood) else None,
        })

    rc_operating = rc[(rc["scope"] == "classifier_operating")
                      & (rc["dataset"] == "delhi")]
    root_cause = []
    for _, row in rc_operating.iterrows():
        root_cause.append({
            "dataset": str(row["dataset"]), "split": str(row["split"]),
            "n_diagnosed": int(row["n_diagnosed"]),
            "accuracy_incl_unknown": _num(row.get("accuracy_incl_unknown")),
            "accuracy_excl_unknown": _num(row.get("accuracy_excl_unknown")),
            "unknown_rate": _num(row.get("unknown_rate")),
            "macro_f1": _num(row.get("macro_f1")),
            "per_class": _per_class(row.get("per_class")),
        })

    _CACHE = {
        "data_mode": "benchmark_evaluation",
        "provenance": {
            "detection": "reports/ensemble/ensemble_metrics.csv + event_metrics.csv",
            "model_comparison": "reports/ensemble/phase6_phase7_phase9_comparison.csv",
            "generalization": "reports/ensemble/ood_metrics.csv + event_metrics.csv",
            "root_cause": "reports/root_cause/root_cause_metrics.csv",
            "runtime": "reports/replay/performance.json",
        },
        "detection": detection,
        "model_comparison": model_comparison,
        "generalization": generalization,
        "root_cause": root_cause,
        "runtime": perf,
        "notes": [
            "Row-level detection uses the frozen ens_median ensemble at its 99th-percentile clean-training threshold.",
            "Event recall counts a controlled injected event as detected on first flagged row; latency is detection delay in minutes.",
            "Root-cause accuracy_incl_unknown counts UNKNOWN as wrong; accuracy_excl_unknown only over classified rows.",
            "Runtime values are single-machine live measurements (see reports/replay/performance.json), not vendor claims.",
        ],
    }
    logger.info("Evaluation evidence cached (%d detection rows)", len(detection))
    return _CACHE
