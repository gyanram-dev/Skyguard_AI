"""Aggregation of per-split results into summary tables + JSON + markdown."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.evaluation.statistical_baseline.metrics import confusion_counts, prf_metrics

METHODS = (("zscore", "zscore_combined_flag"), ("iqr", "iqr_combined_flag"),
           ("combined", "combined_flag"))
EVENT_METHODS = ("zscore", "iqr", "combined")


def _eligible(rows: pd.DataFrame) -> pd.DataFrame:
    return rows[rows["evaluation_eligible"] == 1].copy()


def overall_metrics(rows: pd.DataFrame, dataset: str, split: str) -> list[dict]:
    """Overall row-level metrics per method on eligible rows."""
    out = []
    el = _eligible(rows)
    y_true = el["ground_truth_anomaly"].to_numpy(dtype=int)
    for method, col in METHODS:
        y_pred = el[col].to_numpy(dtype=int)
        cc = confusion_counts(y_true, y_pred)
        out.append({"dataset": dataset, "split": split, "method": method,
                    "scope": "overall", "group": "all", **cc,
                    **prf_metrics(cc["tp"], cc["fp"], cc["tn"], cc["fn"]),
                    "eligible_rows": int(len(el))})
    return out


def fault_metrics(rows: pd.DataFrame, dataset: str, split: str) -> list[dict]:
    """Per-fault-type row metrics ( plus event recall joined later)."""
    out = []
    el = _eligible(rows)
    for fault in ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE", "SPIKE_PLUS_DRIFT"):
        sub = el[el["ground_truth_fault_type"] == fault]
        injected = int((sub["ground_truth_anomaly"] == 1).sum())
        if injected == 0 and len(sub) == 0:
            continue
        for method, col in METHODS:
            y_true = sub["ground_truth_anomaly"].to_numpy(dtype=int)
            y_pred = sub[col].to_numpy(dtype=int)
            cc = confusion_counts(y_true, y_pred)
            out.append({"dataset": dataset, "split": split, "method": method,
                        "scope": "fault_type", "group": fault,
                        "injected_rows": injected, **cc,
                        **prf_metrics(cc["tp"], cc["fp"], cc["tn"], cc["fn"]),
                        "eligible_rows": int(len(sub))})
    return out


def variable_metrics(rows: pd.DataFrame, event_labels: pd.DataFrame,
                     dataset: str, split: str) -> list[dict]:
    """Per-variable recall for single-variable faults (via event target map)."""
    out = []
    el = _eligible(rows)
    faults = event_labels[(event_labels["split"] == split)
                          & (event_labels["fault_type"].isin(("SPIKE", "FROZEN", "DRIFT")))]
    target_of = dict(zip(faults["injection_id"].astype(str), faults["target_variable"].astype(str)))
    el = el.copy()
    el["event_target"] = el["injection_id"].map(target_of)
    for var in ("temperature_c", "pressure_hpa", "relative_humidity_pct"):
        sub = el[(el["ground_truth_anomaly"] == 1) & (el["event_target"] == var)]
        injected = int(len(sub))
        if injected == 0:
            continue
        for method, col in METHODS:
            detected = int((sub[col] == 1).sum())
            missed = injected - detected
            out.append({"dataset": dataset, "split": split, "method": method,
                        "scope": "variable", "group": var,
                        "injected_rows": injected, "detected_rows": detected,
                        "missed_rows": missed,
                        "recall": (detected / injected) if injected else float("nan")})
    return out


def _method_arrays(event_results: pd.DataFrame, method: str) -> tuple[np.ndarray, np.ndarray]:
    if method == "combined":
        det = np.maximum(event_results["zscore_detected"].to_numpy(dtype=int),
                         event_results["iqr_detected"].to_numpy(dtype=int))
        zl = event_results["zscore_latency_minutes"].to_numpy(dtype=float)
        ql = event_results["iqr_latency_minutes"].to_numpy(dtype=float)
        lat = np.where(np.isnan(zl), ql, np.where(np.isnan(ql), zl, np.minimum(zl, ql)))
        return det, lat
    return (event_results[f"{method}_detected"].to_numpy(dtype=int),
            event_results[f"{method}_latency_minutes"].to_numpy(dtype=float))


def _lat_stats(lat: np.ndarray) -> dict:
    ok = lat[~np.isnan(lat)]
    if len(ok) == 0:
        return {"latency_median_min": float("nan"), "latency_mean_min": float("nan"),
                "latency_min_min": float("nan"), "latency_max_min": float("nan")}
    return {"latency_median_min": float(np.median(ok)), "latency_mean_min": float(np.mean(ok)),
            "latency_min_min": float(np.min(ok)), "latency_max_min": float(np.max(ok))}


def event_summary(event_results: pd.DataFrame, dataset: str, split: str) -> list[dict]:
    """Event recall + latency stats per method (and per fault type)."""
    out = []
    for method in EVENT_METHODS:
        det, lat = _method_arrays(event_results, method)
        out.append({"dataset": dataset, "split": split, "method": method,
                    "scope": "event", "group": "all",
                    "events": int(len(event_results)),
                    "events_detected": int(det.sum()),
                    "event_recall": float(det.mean()) if len(det) else float("nan"),
                    **_lat_stats(lat)})
        for fault, sub in event_results.groupby("fault_type"):
            det2, lat2 = _method_arrays(sub, method)
            out.append({"dataset": dataset, "split": split, "method": method,
                        "scope": "event_by_fault", "group": str(fault),
                        "events": int(len(sub)),
                        "events_detected": int(det2.sum()),
                        "event_recall": float(det2.mean()) if len(det2) else float("nan"),
                        **_lat_stats(lat2)})
    return out


def false_positive_summary(rows: pd.DataFrame, dataset: str, split: str) -> list[dict]:
    """Background flag behavior on eligible non-injected rows."""
    out = []
    bg = rows[(rows["evaluation_eligible"] == 1) & (rows["ground_truth_anomaly"] == 0)]
    for method, col in METHODS:
        flagged = int((bg[col] == 1).sum())
        total = int(len(bg))
        out.append({"dataset": dataset, "split": split, "method": method,
                    "background_rows": total, "false_positive_count": flagged,
                    "background_flag_rate": (flagged / total) if total else float("nan"),
                    "fp_per_10k": (flagged / total * 10000.0) if total else float("nan")})
    return out


FP_VARIABLE_FLAGS = {
    "zscore": (("temperature", "temperature_zscore_flag"),
               ("pressure", "pressure_zscore_flag"),
               ("humidity", "humidity_zscore_flag")),
    "iqr": (("temperature", "temperature_iqr_flag"),
            ("pressure", "pressure_iqr_flag"),
            ("humidity", "humidity_iqr_flag")),
    "combined": (("temperature", "temperature_zscore_flag", "temperature_iqr_flag"),
                 ("pressure", "pressure_zscore_flag", "pressure_iqr_flag"),
                 ("humidity", "humidity_zscore_flag", "humidity_iqr_flag")),
}


def false_positive_by_variable(rows: pd.DataFrame, dataset: str, split: str) -> list[dict]:
    """Descriptive FP patterns per variable on eligible background rows."""
    out = []
    bg = rows[(rows["evaluation_eligible"] == 1) & (rows["ground_truth_anomaly"] == 0)]
    total = int(len(bg))
    for method, entries in FP_VARIABLE_FLAGS.items():
        for entry in entries:
            var, cols = entry[0], entry[1:]
            mat = np.stack([np.nan_to_num(bg[c].to_numpy(dtype=float), nan=0.0) for c in cols])
            flagged = int((mat == 1.0).any(axis=0).sum())
            out.append({"dataset": dataset, "split": split, "method": method,
                        "variable": var, "background_rows": total,
                        "false_positive_count": flagged,
                        "background_flag_rate": (flagged / total) if total else float("nan"),
                        "fp_per_10k": (flagged / total * 10000.0) if total else float("nan")})
    return out


def ood_comparison(summary: list[dict]) -> list[dict]:
    """ID vs OOD side-by-side with deltas (OOD minus ID) per dataset/method."""
    out = []
    for ds in ("jena", "delhi"):
        for method, _ in METHODS:
            idm = next((m for m in summary if m["dataset"] == ds and m["split"] == "test_in_distribution"
                        and m["method"] == method and m["scope"] == "overall"), None)
            ood = next((m for m in summary if m["dataset"] == ds and m["split"] == "test_generalization"
                        and m["method"] == method and m["scope"] == "overall"), None)
            ide = next((m for m in summary if m["dataset"] == ds and m["split"] == "test_in_distribution"
                        and m["method"] == method and m["scope"] == "event" and m["group"] == "all"), None)
            oode = next((m for m in summary if m["dataset"] == ds and m["split"] == "test_generalization"
                         and m["method"] == method and m["scope"] == "event" and m["group"] == "all"), None)
            if idm is None or ood is None:
                continue
            row: dict = {"dataset": ds, "method": method}
            for k in ("precision", "recall", "f1", "fpr", "fnr"):
                row[f"id_{k}"] = idm[k]
                row[f"ood_{k}"] = ood[k]
                try:
                    row[f"delta_{k}"] = float(ood[k]) - float(idm[k])
                    if row[f"delta_{k}"] != row[f"delta_{k}"]:  # NaN guard
                        row[f"delta_{k}"] = float("nan")
                except Exception:
                    row[f"delta_{k}"] = float("nan")
            if ide is not None and oode is not None:
                row["id_event_recall"] = ide["event_recall"]
                row["ood_event_recall"] = oode["event_recall"]
                row["id_latency_median_min"] = ide["latency_median_min"]
                row["ood_latency_median_min"] = oode["latency_median_min"]
            out.append(row)
    return out


def write_artifacts(results: dict, out_dir: Path, reports_dir: Path) -> dict:
    """Write CSV/JSON artifacts. Return the metrics JSON payload."""
    out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    for (ds, sp), frame in results["rows"].items():
        frame.to_csv(out_dir / f"{ds}_{sp}_results.csv", index=False)
    for ds in ("jena", "delhi"):
        splits = sorted({sp for (d, sp) in results["events"] if d == ds})
        combined_events = pd.concat([results["events"][(ds, sp)] for sp in splits],
                                    ignore_index=True)
        combined_events.to_csv(out_dir / f"{ds}_event_results.csv", index=False)
        combined_rows = pd.concat([results["rows"][(ds, sp)] for sp in splits],
                                  ignore_index=True)
        combined_rows.to_csv(out_dir.parent / f"{ds}_statistical_evaluation.csv", index=False)
    summary = pd.DataFrame(results["summary"])
    summary.to_csv(out_dir / "summary_metrics.csv", index=False)
    summary.to_csv(out_dir / "statistical_metrics.csv", index=False)
    pd.DataFrame([r for r in results["summary"] if r.get("scope") == "event"]).to_csv(
        out_dir / "event_metrics.csv", index=False)
    pd.DataFrame(results["ood"]).to_csv(out_dir / "ood_metrics.csv", index=False)
    pd.DataFrame(results["fp_by_variable"]).to_csv(out_dir / "false_positive_analysis.csv", index=False)
    diag = pd.DataFrame(results["diagnostics"])
    diag.to_csv(out_dir / "threshold_diagnostics.csv", index=False)
    payload = {"metrics": results["summary"], "diagnostics": results["diagnostics"],
               "ood_comparison": results["ood"], "fp_by_variable": results["fp_by_variable"]}
    with open(reports_dir / "statistical_baseline_metrics.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    return payload
