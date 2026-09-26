"""Phase 10 pipeline: calibrate, freeze, evaluate, compare the ensemble.

Usage:
    python -m src.ensemble.run

Calibration/thresholds: clean-training component scores only (frozen
models scored, never retrained). Evaluation: frozen benchmark splits.
Reads (read-only): clean files, baseline CSVs, frozen model artifacts,
frozen prediction/evaluation files, benchmark splits/labels, NOAA context
validation (availability only). Writes: models/ensemble/*,
data/ensemble/*, reports/ensemble/*.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.ensemble import evaluator as E
from src.ensemble.threshold import THRESHOLD_METHOD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_ensemble.run")

EVAL_SPLITS = ("test_in_distribution", "test_generalization")

UPSTREAM_WATCH = [
    "data/processed/jena_clean.csv",
    "data/processed/delhi_clean.csv",
    "data/baseline/jena_statistical_baseline.csv",
    "data/baseline/delhi_statistical_baseline.csv",
    "data/benchmark/manifests/benchmark_manifest.json",
    "data/benchmark/jena/test_in_distribution.csv",
    "data/benchmark/jena/test_generalization.csv",
    "data/benchmark/delhi/test_in_distribution.csv",
    "data/benchmark/delhi/test_generalization.csv",
    "data/benchmark/labels/jena_event_labels.csv",
    "data/benchmark/labels/delhi_event_labels.csv",
    "data/evaluation/statistical_baseline/summary_metrics.csv",
    "reports/isolation_forest/isolation_forest_metrics.csv",
    "reports/lstm_autoencoder/lstm_autoencoder_metrics.csv",
    "models/isolation_forest/jena_isolation_forest.joblib",
    "models/isolation_forest/delhi_isolation_forest.joblib",
    "models/lstm_autoencoder/jena_lstm_autoencoder.keras",
    "models/lstm_autoencoder/delhi_lstm_autoencoder.keras",
    "models/lstm_autoencoder/jena_scaler.joblib",
    "models/lstm_autoencoder/delhi_scaler.joblib",
]


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _f(x) -> str:
    import math

    return "NaN" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.4f}"


def run_ensemble_pipeline(project_root: str | Path = ".") -> dict:
    """Calibrate, freeze, evaluate, and compare the ensemble."""
    start = time.time()
    root = Path(project_root).resolve()
    bench_root = root / "data" / "benchmark"
    model_dir = root / "models" / "ensemble"
    pred_dir = root / "data" / "ensemble"
    rep_dir = root / "reports" / "ensemble"
    for d in (model_dir, pred_dir, rep_dir):
        d.mkdir(parents=True, exist_ok=True)

    pre = {rel: _sha(root / rel) for rel in UPSTREAM_WATCH}
    phase6 = pd.read_csv(root / "data" / "evaluation" / "statistical_baseline" / "summary_metrics.csv")
    phase7 = pd.read_csv(root / "reports" / "isolation_forest" / "isolation_forest_metrics.csv")
    phase9 = pd.read_csv(root / "reports" / "lstm_autoencoder" / "lstm_autoencoder_metrics.csv")

    summary: list[dict] = []
    comparison: list[dict] = []
    configs: dict = {}
    event_frames: dict = {}
    noaa_notes: dict = {}
    for ds in ("jena", "delhi"):
        logger.info("Calibrating %s ensemble on CLEAN training scores...", ds)
        train = E.clean_component_frame(ds, root)
        cal = E.fit_calibration(train)
        train_cal = E.apply_calibration(train, cal)
        thresholds = E.fit_thresholds(train_cal)
        joblib.dump({"ecdf": cal, "thresholds": {k: v["value"] for k, v in thresholds.items()},
                     "dataset": ds}, model_dir / f"{ds}_calibration.joblib")
        configs[ds] = {
            "dataset": ds,
            "training_source": f"data/processed/{ds}_clean.csv",
            "training_period": [str(train["timestamp"].iloc[0]), str(train["timestamp"].iloc[-1])],
            "n_clean_train_rows": int(len(train)),
            "detector_components": ["statistical(z,iqr)", "isolation_forest", "lstm_autoencoder"],
            "score_transformations": {
                "z": "max|z| over T/P/RH -> ECDF vs clean-train",
                "iqr": "combined binary flag -> ECDF vs clean-train (two-level)",
                "if": "IsolationForest -decision_function -> ECDF vs clean-train",
                "lstm": "final-timestep MSE -> ECDF vs clean-train",
                "stat": "mean of available calibrated z/iqr",
            },
            "aggregation_methods": ["ens_mean (equal-weight mean)", "ens_median (median)",
                                    "diag_mean/diag_median (4-input diagnostic)"],
            "availability_policy": "FULL=3 components, PARTIAL=2, INSUFFICIENT<2 -> NaN",
            "threshold_method": THRESHOLD_METHOD,
            "thresholds": {k: v["value"] for k, v in thresholds.items()},
            "threshold_basis": {k: v["diag"] for k, v in thresholds.items()},
            "benchmark_labels_used_for_calibration": False,
            "benchmark_labels_used_for_threshold": False,
            "benchmark_train_used_for_calibration": False,
            "synthetic_training_contamination": 0,
            "random_seeds": "inherited frozen components (IF 26073, LSTM 26073); "
                            "no stochastic fitting in Phase 10",
            "software_versions": {"pandas": pd.__version__, "numpy": np.__version__,
                                  "sklearn": __import__("sklearn").__version__},
        }

        pred_frames = []
        for split in EVAL_SPLITS:
            events = pd.read_csv(bench_root / "labels" / f"{ds}_event_labels.csv")
            frame = E.load_eval_frame(ds, split, root)
            frame = E.apply_calibration(frame, cal)
            frame = E.flag_frame(frame, thresholds)
            pred_frames.append(frame)
            srows, split_events = E.summarize_rows(frame, ds, split, events)
            summary += srows
            event_frames[(ds, split)] = split_events
            logger.info("%s %s: mean_flags=%d median_flags=%d eligible=%d", ds, split,
                        int(frame["ens_mean_flag"].sum()), int(frame["ens_median_flag"].sum()),
                        int(frame["evaluation_eligible"].sum()))
        pd.concat(pred_frames, ignore_index=True).to_csv(
            pred_dir / f"{ds}_ensemble_predictions.csv", index=False)

        for split in EVAL_SPLITS:
            for scope, group in (("overall", "all"), ("event", "all")):
                for method in ("ens_mean", "ens_median"):
                    mine = next(m for m in summary if m["dataset"] == ds and m["split"] == split
                                and m["method"] == method and m["scope"] == scope)
                    keys = ["precision", "recall", "f1", "fpr", "fnr"] if scope == "overall" else \
                        ["event_recall", "latency_median_min", "latency_mean_min"]
                    for ref_name, ref_frame, ref_method, prefix in (
                            ("zscore", phase6, "zscore", "ref"),
                            ("iqr", phase6, "iqr", "ref"),
                            ("iforest", phase7, "iforest", "ref"),
                            ("lstm_ae", phase9, "lstm_ae", "ref")):
                        ref = ref_frame[(ref_frame["dataset"] == ds) & (ref_frame["split"] == split)
                                        & (ref_frame["method"] == ref_method)
                                        & (ref_frame["scope"] == scope) & (ref_frame["group"] == "all")]
                        if len(ref) == 0:
                            continue
                        ref = ref.iloc[0].to_dict()
                        rec: dict = {"dataset": ds, "split": split, "scope": scope,
                                     "ensemble_method": method, "reference_method": ref_name}
                        for k in keys:
                            rec[f"ref_{k}"] = ref.get(k)
                            rec[f"ens_{k}"] = mine.get(k)
                        comparison.append(rec)
        noaa_notes[ds] = _noaa_availability(ds, root)

    pd.DataFrame(summary).to_csv(rep_dir / "ensemble_metrics.csv", index=False)
    ev_rows = [m for m in summary if m["scope"] in ("event", "event_by_fault")]
    pd.DataFrame(ev_rows).to_csv(rep_dir / "event_metrics.csv", index=False)
    ood = []
    for ds in ("jena", "delhi"):
        for method in ("ens_mean", "ens_median"):
            idm = next(m for m in summary if m["dataset"] == ds and m["split"] == "test_in_distribution"
                       and m["method"] == method and m["scope"] == "overall")
            oodm = next(m for m in summary if m["dataset"] == ds and m["split"] == "test_generalization"
                        and m["method"] == method and m["scope"] == "overall")
            ood.append({"dataset": ds, "method": method,
                        **{f"id_{k}": idm[k] for k in ("precision", "recall", "f1", "fpr", "fnr")},
                        **{f"ood_{k}": oodm[k] for k in ("precision", "recall", "f1", "fpr", "fnr")}})
    pd.DataFrame(ood).to_csv(rep_dir / "ood_metrics.csv", index=False)
    fp = [m for m in summary if m["scope"] == "false_positive"]
    pd.DataFrame(fp).to_csv(rep_dir / "false_positive_analysis.csv", index=False)
    for ds in ("jena", "delhi"):
        splits = sorted({sp for (d, sp) in event_frames if d == ds})
        pd.concat([event_frames[(ds, sp)] for sp in splits],
                  ignore_index=True).to_csv(rep_dir / f"{ds}_event_results.csv", index=False)
    pd.DataFrame(comparison).to_csv(rep_dir / "phase6_phase7_phase9_comparison.csv", index=False)
    with open(rep_dir / "calibration_config.json", "w", encoding="utf-8") as f:
        json.dump(configs, f, indent=2, default=str)
    with open(rep_dir / "ensemble_evaluation.md", "w", encoding="utf-8") as f:
        f.write(generate_markdown(configs, summary, comparison, noaa_notes,
                                  time.time() - start))
    post = {rel: _sha(root / rel) for rel in UPSTREAM_WATCH}
    if pre != post:
        raise RuntimeError("CRITICAL: upstream inputs changed during ensemble run")
    exec_seconds = time.time() - start
    logger.info("Phase 10 complete in %.1fs.", exec_seconds)
    return {"summaries": summary, "execution_time_seconds": exec_seconds}


def _noaa_availability(ds: str, root: Path) -> dict:
    """Contextual NOAA availability for benchmark rows (never scored).

    Delhi benchmark timestamps are a subset of delhi_clean timestamps, so a
    timestamp join to the Phase 8B AWS context validation is reproducible.
    Jena has no valid join (different country and period) and reports zero.
    """
    if ds != "delhi":
        return {"join": "none (geographic/temporal disjointness)",
                "benchmark_rows_with_context": 0, "note": "Jena predates and is outside NOAA coverage"}
    ctx = pd.read_csv(root / "reports" / "noaa" / "aws_context_validation.csv",
                      usecols=["timestamp_ist", "ctx_temp_station_count"])
    ctx = ctx.rename(columns={"timestamp_ist": "timestamp"})
    out = {}
    for split in ("test_in_distribution", "test_generalization"):
        bench = pd.read_csv(root / "data" / "benchmark" / "delhi" / f"{split}.csv",
                            usecols=["timestamp"])
        merged = pd.merge(bench, ctx, on="timestamp", how="left", validate="one_to_one")
        matched = int(merged["ctx_temp_station_count"].notna().sum())
        with_ctx = int((merged["ctx_temp_station_count"] > 0).sum())
        out[split] = {"benchmark_rows": int(len(bench)), "joined_rows": matched,
                      "rows_with_context": with_ctx,
                      "fraction": round(with_ctx / len(bench), 4)}
    out["join"] = "timestamp join benchmark -> Phase 8B aws_context_validation"
    out["usage"] = "availability reporting only; excluded from official ensemble score"
    return out


def generate_markdown(configs: dict, summary: list[dict], comparison: list[dict],
                      noaa_notes: dict, exec_seconds: float) -> str:
    def sel(**kw):
        return next(m for m in summary if all(m.get(k) == v for k, v in kw.items()))

    md: list[str] = []
    md.append("# Calibrated Multi-Detector Ensemble — Evaluation: Phase 10")
    md.append("")
    md.append("**Scope**: calibrated combination of statistical, Isolation Forest, and "
              "LSTM evidence. No retraining/retuning; NOAA contextual only; no "
              "root-cause, SHAP, API, or frontend work.")
    md.append("Calibration (ECDF) and thresholds from clean-training scores only; "
              "benchmark labels used for measurement only. Scores are NOT probabilities.")
    md.append("")
    md.append("## Calibration and configuration (per dataset)")
    md.append("")
    for ds in ("jena", "delhi"):
        c = configs[ds]
        md.append(f"- `{ds}`: train {c['training_period'][0]} → {c['training_period'][1]} "
                  f"({c['n_clean_train_rows']:,} rows); thresholds mean "
                  f"{c['thresholds']['ens_mean']:.4f} / median {c['thresholds']['ens_median']:.4f} "
                  f"({c['threshold_method']}); contamination 0.")
    md.append("")
    md.append("Final ensemble: 3 components {statistical(z,iqr), IF, LSTM} with "
              "equal-weight mean (`ens_mean`) and median (`ens_median`); diagnostic "
              "4-input variants (`diag_mean`, `diag_median`) keep z/iqr separate. "
              "Availability: FULL=3, PARTIAL=2, INSUFFICIENT<2 → NaN (never zero-filled).")
    md.append("")
    md.append("## Row metrics (frozen thresholds)")
    md.append("")
    md.append("| Dataset | Split | Method | Precision | Recall | F1 | FPR | FNR |")
    md.append("| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in ("test_in_distribution", "test_generalization"):
            for method in ("ens_mean", "ens_median"):
                m = sel(dataset=ds, split=split, method=method, scope="overall")
                md.append(f"| {ds} | {split} | {method} | {_f(m['precision'])} | {_f(m['recall'])} | "
                          f"{_f(m['f1'])} | {_f(m['fpr'])} | {_f(m['fnr'])} |")
    md.append("")
    md.append("## Event metrics")
    md.append("")
    md.append("| Dataset | Split | Method | Events | Detected | Recall | Lat med | Lat mean |")
    md.append("| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            for method in ("ens_mean", "ens_median"):
                m = sel(dataset=ds, split=split, method=method, scope="event", group="all")
                md.append(f"| {ds} | {split} | {method} | {m['events']} | {m['events_detected']} | "
                          f"{_f(m['event_recall'])} | {_f(m['latency_median_min'])} | "
                          f"{_f(m['latency_mean_min'])} |")
    md.append("")
    md.append("## Per-fault row recall (official methods)")
    md.append("")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            for method in ("ens_mean", "ens_median"):
                parts = []
                for fault in ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE", "SPIKE_PLUS_DRIFT"):
                    matches = [m for m in summary if m["dataset"] == ds and m["split"] == split
                               and m["method"] == method and m["scope"] == "fault_type"
                               and m["group"] == fault]
                    if not matches or "recall" not in matches[0]:
                        parts.append(f"{fault}=absent")
                    else:
                        parts.append(f"{fault}={_f(matches[0]['recall'])}")
                md.append(f"- {ds}/{split}/{method}: " + ", ".join(parts))
    md.append("")
    md.append("## SPIKE_PLUS_DRIFT (OOD unseen combinations)")
    md.append("")
    for ds in ("jena", "delhi"):
        for method in ("ens_mean", "ens_median"):
            m = sel(dataset=ds, split="test_generalization", method=method,
                    scope="event_by_fault", group="SPIKE_PLUS_DRIFT")
            r = sel(dataset=ds, split="test_generalization", method=method,
                    scope="fault_type", group="SPIKE_PLUS_DRIFT")
            md.append(f"- {ds}/{method}: {m['events_detected']}/{m['events']} events "
                      f"(recall {_f(m['event_recall'])}), row recall {_f(r['recall'])}.")
    md.append("")
    md.append("## False positives")
    md.append("")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            for method in ("ens_mean", "ens_median"):
                m = sel(dataset=ds, split=split, method=method, scope="false_positive",
                        group="background")
                md.append(f"- {ds}/{split}/{method}: {m['false_positive_count']:,}/"
                          f"{m['background_rows']:,} background flagged (rate "
                          f"{_f(m['background_flag_rate'])}, {_f(m['fp_per_10k'])}/10k). "
                          "No root-cause inference.")
    md.append("")
    md.append("## Comparison with Phase 6/7/9 (descriptive; no winner declared)")
    md.append("")
    for c in comparison:
        if c["scope"] == "overall" and c["ensemble_method"] in ("ens_mean", "ens_median"):
            md.append(f"- {c['dataset']}/{c['split']}/{c['ensemble_method']} vs "
                      f"{c['reference_method']}: P {_f(c['ref_precision'])} → {_f(c['ens_precision'])}; "
                      f"R {_f(c['ref_recall'])} → {_f(c['ens_recall'])}; "
                      f"F1 {_f(c['ref_f1'])} → {_f(c['ens_f1'])}.")
    md.append("")
    md.append("Full side-by-side (incl. event recall/latency) in "
              "`phase6_phase7_phase9_comparison.csv`.")
    md.append("## NOAA contextual treatment")
    md.append("")
    for ds in ("jena", "delhi"):
        md.append(f"- {ds}: {noaa_notes[ds]}")
    md.append("")
    md.append("NOAA excluded from the official ensemble score; availability only.")
    md.append(f"Command: `python -m src.ensemble.run` (~{exec_seconds:.0f}s). No tuning on ID/OOD.")
    md.append("")
    return "\n".join(md)


if __name__ == "__main__":
    run_ensemble_pipeline()
