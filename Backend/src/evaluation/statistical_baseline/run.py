"""Batch runner for Phase 6 baseline evaluation.

Usage:
    python -m src.evaluation.statistical_baseline.run

Reads (read-only): data/benchmark/*, data/benchmark/labels/*.
Writes: data/evaluation/statistical_baseline/*.csv,
        reports/evaluation/statistical_baseline_evaluation.md + .json.
Freezes NO thresholds; trains NO model; modifies NO upstream data.
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from src.baseline.statistical_baseline import baseline_window_rows
from src.evaluation.statistical_baseline import diagnostics as D
from src.evaluation.statistical_baseline import report as R
from src.evaluation.statistical_baseline.evaluator import evaluate_split
from src.evaluation.statistical_baseline.event_metrics import build_event_results
from src.features.feature_builder import build_features_for_dataset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_eval_baseline.run")

UPSTREAM_WATCH = [
    "data/benchmark/jena/train.csv",
    "data/benchmark/jena/test_in_distribution.csv",
    "data/benchmark/jena/test_generalization.csv",
    "data/benchmark/delhi/train.csv",
    "data/benchmark/delhi/test_in_distribution.csv",
    "data/benchmark/delhi/test_generalization.csv",
    "data/benchmark/labels/jena_event_labels.csv",
    "data/benchmark/labels/delhi_event_labels.csv",
]

SPLITS = ("train", "test_in_distribution", "test_generalization")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _features_for_diagnostics(bench: pd.DataFrame, dataset: str) -> pd.DataFrame:
    from src.evaluation.statistical_baseline.evaluator import _as_feature_input

    return build_features_for_dataset(_as_feature_input(bench, dataset), dataset)


def run_evaluation(
    project_root: str | Path = ".",
    output_root: str | Path | None = None,
) -> dict:
    start = time.time()
    root = Path(project_root).resolve()
    out_root = Path(output_root).resolve() if output_root else root
    bench_root = root / "data" / "benchmark"
    out_dir = out_root / "data" / "evaluation" / "statistical_baseline"
    rep_dir = out_root / "reports" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)

    pre = {rel: _sha(root / rel) for rel in UPSTREAM_WATCH}

    results: dict = {"rows": {}, "events": {}, "summary": [], "diagnostics": [],
                     "gap_report": {}, "meta": {}, "fp_by_variable": [], "ood": []}
    for ds in ("jena", "delhi"):
        events = pd.read_csv(bench_root / "labels" / f"{ds}_event_labels.csv")
        n_gaps = int((events["fault_type"] == "COMMUNICATION_GAP").sum())
        results["gap_report"][ds] = {
            "communication_gap_events": n_gaps,
            "responsible_layer": "DATA_QUALITY",
            "sensor_metric_exclusion": "gap intervals contain no rows; excluded from row metrics",
        }
        for split in SPLITS:
            bench = pd.read_csv(bench_root / ds / f"{split}.csv")
            rows, baseline = evaluate_split(ds, split, bench)
            results["rows"][(ds, split)] = rows
            results["events"][(ds, split)] = build_event_results(rows, events, ds, split)
            results["summary"] += R.overall_metrics(rows, ds, split)
            results["summary"] += R.fault_metrics(rows, ds, split)
            results["summary"] += R.variable_metrics(rows, events, ds, split)
            results["summary"] += R.event_summary(results["events"][(ds, split)], ds, split)
            results["summary"] += [
                {**m, "scope": "false_positive", "group": "background"}
                for m in R.false_positive_summary(rows, ds, split)]
            results["fp_by_variable"] += R.false_positive_by_variable(rows, ds, split)
            results["diagnostics"] += D.z_threshold_diagnostics(rows, ds, split)
            features = _features_for_diagnostics(bench, ds)
            results["diagnostics"] += D.iqr_factor_diagnostics(
                features, baseline_window_rows(ds), rows, ds, split)
            results["meta"][f"{ds}_{split}"] = {
                "rows": int(len(rows)),
                "eligible_rows": int((rows["evaluation_eligible"] == 1).sum()),
                "injected_rows": int((rows["ground_truth_anomaly"] == 1).sum()),
            }

    results["ood"] = R.ood_comparison(results["summary"])
    payload = R.write_artifacts(results, out_dir, rep_dir)
    with open(rep_dir / "statistical_baseline_evaluation.md", "w", encoding="utf-8") as f:
        f.write(generate_markdown(results, payload))

    post = {rel: _sha(root / rel) for rel in UPSTREAM_WATCH}
    if pre != post:
        raise RuntimeError("CRITICAL: benchmark inputs changed during evaluation")
    exec_seconds = time.time() - start
    logger.info("Phase 6 evaluation complete in %.1fs.", exec_seconds)
    return {"summaries": results["summary"], "execution_time_seconds": exec_seconds}


def _sel(summary: list[dict], **kw) -> dict | None:
    for m in summary:
        if all(m.get(k) == v for k, v in kw.items()):
            return m
    return None


def _f(x) -> str:
    try:
        import math

        return "NaN" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.4f}"
    except Exception:
        return str(x)


def generate_markdown(results: dict, payload: dict) -> str:
    s = results["summary"]
    md: list[str] = []
    md.append("# Traditional Statistical QC Baseline — Benchmark Evaluation: Phase 6")
    md.append("")
    md.append("**Project**: SIH 2026 PS 26073. **Scope**: evaluate the FROZEN Phase 4 baseline only.")
    md.append("All numbers below describe the Traditional Statistical QC Baseline — no SkyGuard ML exists yet.")
    md.append("Benchmark signal: recomputed causally per split (Phase 3 features + Phase 2.5 quality + Phase 4 flags).")
    md.append("Background rows are non-injected background observations, NOT proven normal.")
    md.append("")
    md.append("## Metric equations")
    md.append("")
    md.append("Precision = TP/(TP+FP); Recall = TP/(TP+FN); F1 = 2PR/(P+R); "
              "FPR = FP/(FP+TN); FNR = FN/(TP+FN). Zero denominators → NaN.")
    md.append("")
    for ds in ("jena", "delhi"):
        gaps = results["gap_report"][ds]
        md.append(f"## {ds.title()} — communication gaps: {gaps['communication_gap_events']} events "
                  f"({gaps['responsible_layer']} responsible; {gaps['sensor_metric_exclusion']}).")
    md.append("")
    md.append("## Overall row metrics (eligible rows, official thresholds |z|>3.0, 1.5×IQR)")
    md.append("")
    md.append("| Dataset | Split | Method | Precision | Recall | F1 | FPR | FNR |")
    md.append("| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in SPLITS:
            for method in ("zscore", "iqr", "combined"):
                m = _sel(s, dataset=ds, split=split, method=method, scope="overall")
                md.append(f"| {ds} | {split} | {method} | {_f(m['precision'])} | {_f(m['recall'])} | "
                          f"{_f(m['f1'])} | {_f(m['fpr'])} | {_f(m['fnr'])} |")
    md.append("")
    md.append("## Event recall + latency (median/mean/min/max minutes)")
    md.append("")
    md.append("| Dataset | Split | Method | Events | Detected | Recall | Lat med | Lat mean | Lat min | Lat max |")
    md.append("| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in SPLITS:
            for method in ("zscore", "iqr", "combined"):
                m = _sel(s, dataset=ds, split=split, method=method, scope="event", group="all")
                md.append(f"| {ds} | {split} | {method} | {m['events']} | {m['events_detected']} | "
                          f"{_f(m['event_recall'])} | {_f(m['latency_median_min'])} | {_f(m['latency_mean_min'])} | "
                          f"{_f(m['latency_min_min'])} | {_f(m['latency_max_min'])} |")
    md.append("")
    md.append("## Per-fault recall (row level, ID vs OOD)")
    md.append("")
    md.append("| Dataset | Split | Fault | Z recall | IQR recall | Comb recall | Z event | IQR event | Comb event |")
    md.append("| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in SPLITS:
            for fault in ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE", "SPIKE_PLUS_DRIFT"):
                z = _sel(s, dataset=ds, split=split, method="zscore", scope="fault_type", group=fault)
                q = _sel(s, dataset=ds, split=split, method="iqr", scope="fault_type", group=fault)
                c = _sel(s, dataset=ds, split=split, method="combined", scope="fault_type", group=fault)
                ze = _sel(s, dataset=ds, split=split, method="zscore", scope="event_by_fault", group=fault)
                qe = _sel(s, dataset=ds, split=split, method="iqr", scope="event_by_fault", group=fault)
                ce = _sel(s, dataset=ds, split=split, method="combined", scope="event_by_fault", group=fault)
                if z is None:
                    continue
                md.append(f"| {ds} | {split} | {fault} | {_f(z['recall'])} | {_f(q['recall'])} | "
                          f"{_f(c['recall'])} | {_f(ze['event_recall'])} | {_f(qe['event_recall'])} | "
                          f"{_f(ce['event_recall'])} |")
    md.append("")
    md.append("## SPIKE_PLUS_DRIFT (OOD only, unseen combination)")
    md.append("")
    for ds in ("jena", "delhi"):
        for method in ("zscore", "iqr", "combined"):
            m = _sel(s, dataset=ds, split="test_generalization", method=method,
                     scope="event_by_fault", group="SPIKE_PLUS_DRIFT")
            r = _sel(s, dataset=ds, split="test_generalization", method=method,
                     scope="fault_type", group="SPIKE_PLUS_DRIFT")
            md.append(f"- {ds}/{method}: {m['events_detected']}/{m['events']} events, "
                      f"event recall {_f(m['event_recall'])}, row recall {_f(r['recall'])}.")
    md.append("")
    md.append("## False-positive analysis (eligible background rows only)")
    md.append("")
    md.append("| Dataset | Split | Method | Background rows | FP count | FP rate | FP per 10k |")
    md.append("| :--- | :--- | :--- | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in SPLITS:
            for method in ("zscore", "iqr", "combined"):
                m = _sel(s, dataset=ds, split=split, method=method,
                         scope="false_positive", group="background")
                md.append(f"| {ds} | {split} | {method} | {m['background_rows']} | "
                          f"{m['false_positive_count']} | {_f(m['background_flag_rate'])} | "
                          f"{_f(m['fp_per_10k'])} |")
    md.append("")
    md.append("Descriptive only: common FP patterns are single-variable IQR excursions on smooth "
              "diurnal segments; no root causes are invented. Full per-variable breakdown in "
              "`false_positive_analysis.csv`.")
    md.append("")
    md.append("## ID vs OOD generalization (delta = OOD − ID)")
    md.append("")
    md.append("| Dataset | Method | ID F1 | OOD F1 | ΔF1 | ID recall | OOD recall | Δrecall | "
              "ID event rec | OOD event rec |")
    md.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for d in results["ood"]:
        md.append(f"| {d['dataset']} | {d['method']} | {_f(d['id_f1'])} | {_f(d['ood_f1'])} | "
                  f"{_f(d['delta_f1'])} | {_f(d['id_recall'])} | {_f(d['ood_recall'])} | "
                  f"{_f(d['delta_recall'])} | {_f(d.get('id_event_recall'))} | {_f(d.get('ood_event_recall'))} |")
    md.append("")
    md.append("## Threshold diagnostics (sensitivity only; official settings unchanged)")
    md.append("")
    md.append("| Dataset | Split | Method | Threshold | Precision | Recall | FPR |")
    md.append("| :--- | :--- | :--- | ---: | ---: | ---: | ---: |")
    for d in payload["diagnostics"]:
        md.append(f"| {d['dataset']} | {d['split']} | {d['method']} | {d['threshold']} | "
                  f"{_f(d['precision'])} | {_f(d['recall'])} | {_f(d['fpr'])} |")
    md.append("")
    md.append("## Limitations and reproduction")
    md.append("")
    md.append("- Background flag rates use non-injected background (not guaranteed clean).")
    md.append("- Thresholds were NOT tuned; OOD was NOT used for selection; Phase 4 untouched.")
    md.append("- No pressure/temperature hard rules exist in this path (verified by Phase 4/5 tests); "
              "55 °C is flaggable only by statistical context, never deleted.")
    md.append("- Command: `python -m src.evaluation.statistical_baseline.run` (deterministic; timing excluded).")
    md.append("")
    return "\n".join(md)


if __name__ == "__main__":
    run_evaluation()
