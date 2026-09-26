"""Phase 7 pipeline: train per-dataset Isolation Forests, predict, evaluate, compare.

Usage:
    python -m src.isolation_forest.run

Training (clean only): data/processed/{jena,delhi}_clean.csv restricted to
the exact Phase 5 train-period boundaries. Benchmark files/labels/manifests
never enter fitting or threshold selection.
Evaluation (injected): data/benchmark/* test splits (values + labels).
Reads (read-only): data/processed/*_clean.csv, data/benchmark/*,
Phase 6 summary_metrics.csv (frozen).
Writes: models/isolation_forest/*.joblib, data/isolation_forest/*.csv,
        reports/isolation_forest/*.
Freezes threshold on clean train scores; never tunes on ID/OOD.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.isolation_forest import features as F
from src.isolation_forest.evaluator import (
    TRAINING_SOURCE_TEMPLATE,
    load_clean_train_frame,
    predict_split,
    summarize_rows,
    train_dataset,
)
from src.isolation_forest.model import IF_PARAMS, MODEL_SEED, load_artifact, save_artifact
from src.isolation_forest.threshold import THRESHOLD_QUANTILE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_iforest.run")

SPLITS = ("train", "test_in_distribution", "test_generalization")
EVAL_SPLITS = ("test_in_distribution", "test_generalization")

UPSTREAM_WATCH = [
    "data/processed/jena_clean.csv",
    "data/processed/delhi_clean.csv",
    "data/benchmark/manifests/benchmark_manifest.json",
    "data/benchmark/jena/test_in_distribution.csv",
    "data/benchmark/jena/test_generalization.csv",
    "data/benchmark/delhi/test_in_distribution.csv",
    "data/benchmark/delhi/test_generalization.csv",
    "data/benchmark/labels/jena_event_labels.csv",
    "data/benchmark/labels/delhi_event_labels.csv",
    "data/evaluation/statistical_baseline/summary_metrics.csv",
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


def run_iforest_pipeline(project_root: str | Path = ".") -> dict:
    start = time.time()
    root = Path(project_root).resolve()
    bench_root = root / "data" / "benchmark"
    model_dir = root / "models" / "isolation_forest"
    pred_dir = root / "data" / "isolation_forest"
    rep_dir = root / "reports" / "isolation_forest"
    for d in (model_dir, pred_dir, rep_dir):
        d.mkdir(parents=True, exist_ok=True)

    pre = {rel: _sha(root / rel) for rel in UPSTREAM_WATCH}
    phase6 = pd.read_csv(root / "data" / "evaluation" / "statistical_baseline" / "summary_metrics.csv")

    summary: list[dict] = []
    comparison: list[dict] = []
    configs: dict = {}
    allowlists: dict = {}
    event_frames: dict = {}
    for ds in ("jena", "delhi"):
        bench = {sp: pd.read_csv(bench_root / ds / f"{sp}.csv") for sp in SPLITS}
        events = pd.read_csv(bench_root / "labels" / f"{ds}_event_labels.csv")
        logger.info("Training %s Isolation Forest on CLEAN pre-benchmark data...", ds)
        clean_train = load_clean_train_frame(ds, root)
        bundle = train_dataset(clean_train, ds)
        allowlists[ds] = bundle["allowlist"]
        artifact = {k: v for k, v in bundle.items() if k != "model"}
        artifact["model"] = bundle["model"]
        save_artifact(artifact, model_dir / f"{ds}_isolation_forest.joblib")

        configs[ds] = {
            "model_params": IF_PARAMS,
            "random_seed": MODEL_SEED,
            "training_source": TRAINING_SOURCE_TEMPLATE.format(dataset=ds),
            "training_data": "clean pre-benchmark observations",
            "benchmark_train_used_for_fit": False,
            "synthetic_training_contamination": 0,
            "threshold_method": bundle["threshold_diag"]["method"],
            "threshold_raw": bundle["threshold_raw"],
            "threshold_quantile": THRESHOLD_QUANTILE,
            "train_range": [bundle["train_start_timestamp"], bundle["train_end_timestamp"]],
            "n_train_rows": bundle["n_train_rows"],
            "n_train_eligible": bundle["n_train_eligible"],
            "n_train_fitted": bundle["n_train_fitted"],
            "train_above_threshold": bundle["threshold_diag"],
            "eligibility_rule": "Phase 2.5 ml_eligible==1 AND feature-complete (94 allowlisted, no imputation)",
            "sklearn_version": bundle["sklearn_version"],
            "score_convention": "HIGHER if_raw_score = MORE anomalous (-decision_function); "
                                "if_anomaly_score = ECDF vs frozen train distribution in [0,1], NOT a probability",
        }
        pred_frames = []
        for split in SPLITS:
            rows = predict_split(bundle, bench[split], ds, split)
            pred_frames.append(rows)
            label = "diagnostic-only" if split == "train" else "evaluation"
            logger.info("%s %s (%s): flagged=%d eligible=%d", ds, split, label,
                        int(rows["if_anomaly_flag"].sum()), int(rows["evaluation_eligible"].sum()))
            if split != "train":
                srows, split_events = summarize_rows(rows, ds, split, events)
                summary += srows
                event_frames[(ds, split)] = split_events
        pd.concat(pred_frames, ignore_index=True).to_csv(
            pred_dir / f"{ds}_isolation_forest_predictions.csv", index=False)

        # Side-by-side with frozen Phase 6 (descriptive, no winner declared).
        for split in EVAL_SPLITS:
            for scope, group in (("overall", "all"), ("event", "all")):
                mine = next(m for m in summary if m["dataset"] == ds and m["split"] == split
                            and m["method"] == "iforest" and m["scope"] == scope)
                for method in ("zscore", "iqr"):
                    ref = phase6[(phase6["dataset"] == ds) & (phase6["split"] == split)
                                 & (phase6["method"] == method) & (phase6["scope"] == scope)
                                 & (phase6["group"] == "all")]
                    if len(ref) == 0:
                        continue
                    ref = ref.iloc[0].to_dict()
                    keys = ["precision", "recall", "f1", "fpr", "fnr"] if scope == "overall" else \
                           ["event_recall", "latency_median_min", "latency_mean_min"]
                    rec: dict = {"dataset": ds, "split": split, "scope": scope,
                                 "baseline_method": method}
                    for k in keys:
                        rec[f"baseline_{k}"] = ref.get(k)
                        rec[f"iforest_{k}"] = mine.get(k)
                    comparison.append(rec)

    pd.DataFrame(summary).to_csv(rep_dir / "isolation_forest_metrics.csv", index=False)
    ev_rows = [m for m in summary if m["scope"] in ("event", "event_by_fault")]
    pd.DataFrame(ev_rows).to_csv(rep_dir / "event_metrics.csv", index=False)
    ood = []
    for ds in ("jena", "delhi"):
        for method_key in ("iforest",):
            idm = next(m for m in summary if m["dataset"] == ds and m["split"] == "test_in_distribution"
                       and m["method"] == method_key and m["scope"] == "overall")
            oodm = next(m for m in summary if m["dataset"] == ds and m["split"] == "test_generalization"
                        and m["method"] == method_key and m["scope"] == "overall")
            ood.append({"dataset": ds, "method": method_key,
                        **{f"id_{k}": idm[k] for k in ("precision", "recall", "f1", "fpr", "fnr")},
                        **{f"ood_{k}": oodm[k] for k in ("precision", "recall", "f1", "fpr", "fnr")}})
    pd.DataFrame(ood).to_csv(rep_dir / "ood_metrics.csv", index=False)
    fp = [m for m in summary if m["scope"] == "false_positive"]
    pd.DataFrame(fp).to_csv(rep_dir / "false_positive_analysis.csv", index=False)
    for ds in ("jena", "delhi"):
        splits = sorted({sp for (d, sp) in event_frames if d == ds})
        pd.concat([event_frames[(ds, sp)] for sp in splits],
                  ignore_index=True).to_csv(rep_dir / f"{ds}_event_results.csv", index=False)
    from src.isolation_forest.features import (
        EXCLUDED_GAP_META,
        EXCLUDED_PROVENANCE,
        EXCLUDED_QUALITY,
    )
    feature_manifest = {
        "schema_columns": 106,
        "n_allowlisted": len(allowlists["jena"]),
        "allowlisted_features": allowlists["jena"],
        "delhi_allowlist_identical": allowlists["delhi"] == allowlists["jena"],
        "training_source": {ds: TRAINING_SOURCE_TEMPLATE.format(dataset=ds)
                            for ds in ("jena", "delhi")},
        "training_data": "clean pre-benchmark observations",
        "benchmark_train_used_for_fit": False,
        "synthetic_training_contamination": 0,
        "excluded": {
            "provenance": list(EXCLUDED_PROVENANCE),
            "quality_flags_constant_on_eligible": list(EXCLUDED_QUALITY),
            "gap_metadata": list(EXCLUDED_GAP_META),
        },
        "forbidden_guard": list(F.FORBIDDEN_SUBSTRINGS),
    }
    pd.DataFrame(comparison).to_csv(rep_dir / "phase6_comparison.csv", index=False)
    with open(rep_dir / "model_config.json", "w", encoding="utf-8") as f:
        json.dump(configs, f, indent=2, default=str)
    with open(rep_dir / "feature_manifest.json", "w", encoding="utf-8") as f:
        json.dump(feature_manifest, f, indent=2)
    with open(rep_dir / "isolation_forest_evaluation.md", "w", encoding="utf-8") as f:
        f.write(generate_markdown(configs, summary, comparison, feature_manifest,
                                  time.time() - start))
    post = {rel: _sha(root / rel) for rel in UPSTREAM_WATCH}
    if pre != post:
        raise RuntimeError("CRITICAL: upstream inputs changed during Isolation Forest run")
    exec_seconds = time.time() - start
    logger.info("Phase 7 complete in %.1fs.", exec_seconds)
    return {"summaries": summary, "execution_time_seconds": exec_seconds}


def generate_markdown(configs: dict, summary: list[dict], comparison: list[dict],
                      feature_manifest: dict, exec_seconds: float) -> str:
    def sel(**kw):
        return next(m for m in summary if all(m.get(k) == v for k, v in kw.items()))

    md: list[str] = []
    md.append("# Isolation Forest Anomaly Detector — Evaluation: Phase 7")
    md.append("")
    md.append("**Scope**: first ML detector (server-side Isolation Forest). No LSTM, NOAA/spatial, "
              "ensemble, root-cause, SHAP, API, or frontend.")
    md.append("Fitted ONLY on clean pre-benchmark observations "
              "(`data/processed/{jena,delhi}_clean.csv`, Phase 5 train period); "
              "synthetic_training_contamination = 0. "
              "Threshold frozen on clean train scores (99th percentile); injected benchmark "
              "splits used for evaluation only. Scores are NOT probabilities.")
    md.append("")
    md.append("## Training configuration (per dataset)")
    md.append("")
    for ds in ("jena", "delhi"):
        c = configs[ds]
        md.append(f"- `{ds}`: params `{c['model_params']}`, seed {c['random_seed']}, "
                  f"CLEAN source `{c['training_source']}`, train {c['train_range'][0]} → {c['train_range'][1]}, fitted "
                  f"{c['n_train_fitted']:,}/{c['n_train_rows']:,} rows "
                  f"(eligible {c['n_train_eligible']:,}), threshold_raw "
                  f"{c['threshold_raw']:.4f} ({c['threshold_method']}), "
                  f"train above threshold {c['train_above_threshold']['n_above_threshold']:,} "
                  f"({c['train_above_threshold']['fraction_above_threshold']:.4f}), "
                  f"sklearn {c['sklearn_version']}, synthetic_training_contamination=0.")
    md.append("")
    md.append("## Feature allowlist (94 of 106)")
    md.append("")
    md.append("Kept: current observations (3), cyclical encodings (4), first-order dynamics (9), "
              "frozen/stability (9), causal rolling baselines (36), local deviations (18), trends (9), "
              "multivariate consistency (6). Excluded: timestamp/source_dataset (provenance), 7 "
              "quality flags (constant on eligible rows), elapsed/gap_before/segment_id (gap machinery). "
              "Full 94-name list in `feature_manifest.json`; labels rejected loudly, never imputed "
              "(NaN → unscorable).")
    md.append("")
    md.append("## Score transformation")
    md.append("")
    md.append("`if_raw_score = -decision_function(X)` (higher = more anomalous); "
              "`if_anomaly_score = ECDF_train(raw)` in [0,1]; flag = raw ≥ frozen threshold.")
    md.append("")
    md.append("## Row metrics (frozen threshold)")
    md.append("")
    md.append("| Dataset | Split | Precision | Recall | F1 | FPR | FNR |")
    md.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in ("test_in_distribution", "test_generalization"):
            m = sel(dataset=ds, split=split, method="iforest", scope="overall")
            md.append(f"| {ds} | {split} | {_f(m['precision'])} | {_f(m['recall'])} | {_f(m['f1'])} | "
                      f"{_f(m['fpr'])} | {_f(m['fnr'])} |")
    md.append("")
    md.append("Train-split flag counts are diagnostic only (threshold construction set), not generalization; "
              "see training configuration above.")
    md.append("")
    md.append("## Event metrics")
    md.append("")
    md.append("| Dataset | Split | Events | Detected | Recall | Lat med | Lat mean |")
    md.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            m = sel(dataset=ds, split=split, method="iforest", scope="event", group="all")
            md.append(f"| {ds} | {split} | {m['events']} | {m['events_detected']} | "
                      f"{_f(m['event_recall'])} | {_f(m['latency_median_min'])} | {_f(m['latency_mean_min'])} |")
    md.append("")
    md.append("## Per-fault and per-variable recall")
    md.append("")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            parts = []
            for fault in ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE", "SPIKE_PLUS_DRIFT"):
                matches = [m for m in summary if m["dataset"] == ds and m["split"] == split
                           and m["method"] == "iforest" and m["scope"] == "fault_type"
                           and m["group"] == fault]
                if not matches or "recall" not in matches[0]:
                    parts.append(f"{fault}=absent")
                else:
                    parts.append(f"{fault}={_f(matches[0]['recall'])}")
            md.append(f"- {ds}/{split}: " + ", ".join(parts))
    md.append("")
    md.append("## SPIKE_PLUS_DRIFT (OOD unseen combinations)")
    md.append("")
    for ds in ("jena", "delhi"):
        m = sel(dataset=ds, split="test_generalization", method="iforest",
                scope="event_by_fault", group="SPIKE_PLUS_DRIFT")
        r = sel(dataset=ds, split="test_generalization", method="iforest",
                scope="fault_type", group="SPIKE_PLUS_DRIFT")
        md.append(f"- {ds}: {m['events_detected']}/{m['events']} events "
                  f"(recall {_f(m['event_recall'])}), row recall {_f(r['recall'])}.")
    md.append("")
    md.append("## False positives + latency + comparison")
    md.append("")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            m = sel(dataset=ds, split=split, method="iforest", scope="false_positive", group="background")
            md.append(f"- {ds}/{split}: {m['false_positive_count']:,}/{m['background_rows']:,} "
                      f"background flagged (rate {_f(m['background_flag_rate'])}, "
                      f"{_f(m['fp_per_10k'])}/10k). No root-cause inference.")
    md.append("")
    md.append("## Phase 6 comparison (descriptive; no winner declared)")
    md.append("")
    md.append("| Dataset | Split | Scope | Baseline | " +
              " | ".join(["Base_P", "Base_R", "Base_F1", "IF_P", "IF_R", "IF_F1"]) + " |")
    md.append("| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for c in comparison:
        if c["scope"] == "overall":
            md.append(f"| {c['dataset']} | {c['split']} | row | {c['baseline_method']} | "
                      f"{_f(c['baseline_precision'])} | {_f(c['baseline_recall'])} | {_f(c['baseline_f1'])} | "
                      f"{_f(c['iforest_precision'])} | {_f(c['iforest_recall'])} | {_f(c['iforest_f1'])} |")
    md.append("")
    md.append("Full side-by-side (incl. event recall/latency) in `phase6_comparison.csv`.")
    md.append(f"Command: `python -m src.isolation_forest.run` (~{exec_seconds:.0f}s). No tuning on ID/OOD.")
    md.append("")
    return "\n".join(md)


if __name__ == "__main__":
    run_iforest_pipeline()
