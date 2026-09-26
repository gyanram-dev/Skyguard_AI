"""Phase 9 pipeline: clean-train LSTM autoencoders, freeze, evaluate, compare.

Usage:
    python -m src.lstm_autoencoder.run

Training (clean only): data/processed/{jena,delhi}_clean.csv in the exact
Phase 5 train periods. Evaluation (injected): benchmark ID/OOD splits.
Reads (read-only): processed clean files, benchmark splits/labels, frozen
Phase 6 + Phase 7 metric files. Writes: models/lstm_autoencoder/*,
data/lstm_autoencoder/*, reports/lstm_autoencoder/*.
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
import tensorflow as tf

from src.isolation_forest.evaluator import (
    EXPECTED_TRAIN_PERIODS,
    TRAINING_SOURCE_TEMPLATE,
    load_clean_train_frame,
)
from src.lstm_autoencoder import evaluator as E
from src.lstm_autoencoder import model as M
from src.lstm_autoencoder import training as T
from src.lstm_autoencoder.features import LSTM_FEATURES
from src.lstm_autoencoder.sequences import LOOKBACK
from src.lstm_autoencoder.training import VAL_FRACTION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_lstm.run")

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
    "reports/isolation_forest/isolation_forest_metrics.csv",
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


def run_lstm_pipeline(project_root: str | Path = ".") -> dict:
    """Train, freeze, predict, evaluate, and compare the LSTM detectors."""
    start = time.time()
    root = Path(project_root).resolve()
    bench_root = root / "data" / "benchmark"
    model_dir = root / "models" / "lstm_autoencoder"
    pred_dir = root / "data" / "lstm_autoencoder"
    rep_dir = root / "reports" / "lstm_autoencoder"
    for d in (model_dir, pred_dir, rep_dir):
        d.mkdir(parents=True, exist_ok=True)

    pre = {rel: _sha(root / rel) for rel in UPSTREAM_WATCH}
    phase6 = pd.read_csv(root / "data" / "evaluation" / "statistical_baseline" / "summary_metrics.csv")
    phase7 = pd.read_csv(root / "reports" / "isolation_forest" / "isolation_forest_metrics.csv")

    summary: list[dict] = []
    comparison: list[dict] = []
    configs: dict = {}
    event_frames: dict = {}
    for ds in ("jena", "delhi"):
        bench = {sp: pd.read_csv(bench_root / ds / f"{sp}.csv") for sp in SPLITS}
        events = pd.read_csv(bench_root / "labels" / f"{ds}_event_labels.csv")
        logger.info("Training %s LSTM autoencoder on CLEAN data...", ds)
        clean = load_clean_train_frame(ds, root)
        bundle = E.train_pipeline(clean, ds)
        model_path = model_dir / f"{ds}_lstm_autoencoder.keras"
        bundle["model"].save(model_path)
        T.save_scaler(bundle["scaler"], bundle["feature_list"],
                      model_dir / f"{ds}_scaler.joblib")
        bundle["scaler"] = {"scaler": bundle["scaler"],
                            "feature_order": bundle["feature_list"]}

        configs[ds] = {
            "dataset": ds,
            "training_source": TRAINING_SOURCE_TEMPLATE.format(dataset=ds),
            "training_data": "clean pre-benchmark observations",
            "benchmark_train_used_for_fit": False,
            "synthetic_training_contamination": 0,
            "train_range": [bundle["train_start"], bundle["train_end"]],
            "expected_train_period": list(EXPECTED_TRAIN_PERIODS[ds]),
            "validation_split": f"chronological final {VAL_FRACTION:.0%} of clean sequences",
            "validation_range": ("final 10% of valid clean-train sequences, "
                                 f"{bundle['train_info']['n_val_sequences']:,} sequences"),
            "validation_range_note": "final 10% of valid clean-train sequences (causal)",
            "lookback": LOOKBACK,
            "lookback_convention": "12-step historical sequence [t-11 .. t]; not a fixed duration",
            "n_features": len(LSTM_FEATURES),
            "feature_list": list(LSTM_FEATURES),
            "scaler_type": "StandardScaler",
            "scaler_basis": f"{bundle['n_eligible_finite_rows']:,} eligible finite clean rows",
            "architecture": M.ARCHITECTURE,
            "epochs_requested": bundle["train_info"]["epochs_requested"],
            "epochs_actual": bundle["train_info"]["epochs_actual"],
            "early_stopped": bundle["train_info"]["early_stopped"],
            "batch_size": M.BATCH_SIZE,
            "optimizer": M.OPTIMIZER,
            "learning_rate": M.LEARNING_RATE,
            "loss": M.LOSS,
            "random_seed": M.MODEL_SEED,
            "threshold_method": bundle["threshold_method"],
            "threshold_value": bundle["threshold"],
            "threshold_basis": bundle["threshold_diag"],
            "n_clean_rows": bundle["n_clean_rows"],
            "n_train_sequences": bundle["n_train_sequences"],
            "training_sequence_count": bundle["n_train_sequences"],
            "validation_sequence_count": bundle["train_info"]["n_val_sequences"],
            "n_fit_sequences": bundle["train_info"]["n_train_sequences"],
            "n_val_sequences": bundle["train_info"]["n_val_sequences"],
            "best_val_loss": bundle["train_info"]["best_val_loss"],
            "score_definition": "final-timestep MSE (official); full-sequence MSE diagnostic; "
                                "HIGHER = MORE anomalous, NOT a probability",
            "tensorflow_version": tf.__version__,
            "software_versions": {
                "tensorflow": tf.__version__,
                "sklearn": __import__("sklearn").__version__,
                "pandas": pd.__version__,
                "numpy": np.__version__,
            },
        }
        scored_counts: dict[str, int] = {}
        pred_frames = []
        for split in SPLITS:
            rows = E.predict_split(bundle, bench[split], ds, split)
            pred_frames.append(rows)
            scored_counts[split] = int(rows["scorable"].sum())
            label = "diagnostic-only" if split == "train" else "evaluation"
            logger.info("%s %s (%s): flagged=%d eligible=%d", ds, split, label,
                        int(rows["lstm_anomaly_flag"].sum()),
                        int(rows["evaluation_eligible"].sum()))
            if split != "train":
                srows, split_events = E.summarize_rows(rows, ds, split, events)
                summary += srows
                event_frames[(ds, split)] = split_events
        pd.concat(pred_frames, ignore_index=True).to_csv(
            pred_dir / f"{ds}_lstm_predictions.csv", index=False)
        configs[ds]["scored_sequence_counts"] = scored_counts

        for split in EVAL_SPLITS:
            for scope, group in (("overall", "all"), ("event", "all")):
                mine = next(m for m in summary if m["dataset"] == ds and m["split"] == split
                            and m["method"] == "lstm_ae" and m["scope"] == scope)
                keys = ["precision", "recall", "f1", "fpr", "fnr"] if scope == "overall" else \
                    ["event_recall", "latency_median_min", "latency_mean_min"]
                for ref_name, ref_frame, col in (
                        ("zscore", phase6, "baseline"), ("iqr", phase6, "baseline"),
                        ("iforest", phase7, "iforest")):
                    ref = ref_frame[(ref_frame["dataset"] == ds) & (ref_frame["split"] == split)
                                    & (ref_frame["scope"] == scope) & (ref_frame["group"] == "all")]
                    if ref_name != "iforest":
                        ref = ref[ref["method"] == ref_name]
                    else:
                        ref = ref[ref["method"] == "iforest"]
                    if len(ref) == 0:
                        continue
                    ref = ref.iloc[0].to_dict()
                    rec: dict = {"dataset": ds, "split": split, "scope": scope,
                                 "reference_method": ref_name}
                    for k in keys:
                        rec[f"{col}_{k}"] = ref.get(k)
                        rec[f"lstm_{k}"] = mine.get(k)
                    comparison.append(rec)

    pd.DataFrame(summary).to_csv(rep_dir / "lstm_autoencoder_metrics.csv", index=False)
    ev_rows = [m for m in summary if m["scope"] in ("event", "event_by_fault")]
    pd.DataFrame(ev_rows).to_csv(rep_dir / "event_metrics.csv", index=False)
    ood = []
    for ds in ("jena", "delhi"):
        idm = next(m for m in summary if m["dataset"] == ds and m["split"] == "test_in_distribution"
                   and m["method"] == "lstm_ae" and m["scope"] == "overall")
        oodm = next(m for m in summary if m["dataset"] == ds and m["split"] == "test_generalization"
                    and m["method"] == "lstm_ae" and m["scope"] == "overall")
        ood.append({"dataset": ds, "method": "lstm_ae",
                    **{f"id_{k}": idm[k] for k in ("precision", "recall", "f1", "fpr", "fnr")},
                    **{f"ood_{k}": oodm[k] for k in ("precision", "recall", "f1", "fpr", "fnr")}})
    pd.DataFrame(ood).to_csv(rep_dir / "ood_metrics.csv", index=False)
    fp = [m for m in summary if m["scope"] == "false_positive"]
    pd.DataFrame(fp).to_csv(rep_dir / "false_positive_analysis.csv", index=False)
    for ds in ("jena", "delhi"):
        splits = sorted({sp for (d, sp) in event_frames if d == ds})
        pd.concat([event_frames[(ds, sp)] for sp in splits],
                  ignore_index=True).to_csv(rep_dir / f"{ds}_event_results.csv", index=False)
    feature_manifest = {
        "n_features": len(LSTM_FEATURES),
        "features": list(LSTM_FEATURES),
        "subset_of_phase7_allowlist": True,
        "training_source": {ds: TRAINING_SOURCE_TEMPLATE.format(dataset=ds)
                            for ds in ("jena", "delhi")},
        "training_data": "clean pre-benchmark observations",
        "benchmark_train_used_for_fit": False,
        "synthetic_training_contamination": 0,
        "forbidden_guard": "src.isolation_forest.features.assert_no_forbidden_columns",
    }
    pd.DataFrame(comparison).to_csv(rep_dir / "phase6_phase7_comparison.csv", index=False)
    with open(rep_dir / "model_config.json", "w", encoding="utf-8") as f:
        json.dump(configs, f, indent=2, default=str)
    with open(rep_dir / "feature_manifest.json", "w", encoding="utf-8") as f:
        json.dump(feature_manifest, f, indent=2)
    with open(rep_dir / "lstm_autoencoder_evaluation.md", "w", encoding="utf-8") as f:
        f.write(generate_markdown(configs, summary, comparison, time.time() - start))
    post = {rel: _sha(root / rel) for rel in UPSTREAM_WATCH}
    if pre != post:
        raise RuntimeError("CRITICAL: upstream inputs changed during LSTM run")
    exec_seconds = time.time() - start
    logger.info("Phase 9 complete in %.1fs.", exec_seconds)
    return {"summaries": summary, "execution_time_seconds": exec_seconds}


def generate_markdown(configs: dict, summary: list[dict], comparison: list[dict],
                      exec_seconds: float) -> str:
    def sel(**kw):
        return next(m for m in summary if all(m.get(k) == v for k, v in kw.items()))

    md: list[str] = []
    md.append("# LSTM Autoencoder Anomaly Detector — Evaluation: Phase 9")
    md.append("")
    md.append("**Scope**: sequence-aware detector only. No NOAA/spatial, ensemble, "
              "root-cause, SHAP, API, or frontend work.")
    md.append("Fitted ONLY on clean pre-benchmark observations; "
              "synthetic_training_contamination = 0. Threshold frozen on clean "
              "train reconstruction errors (99th percentile); injected benchmark "
              "splits used for evaluation only. Scores are NOT probabilities.")
    md.append("")
    md.append("## Training configuration (per dataset)")
    md.append("")
    for ds in ("jena", "delhi"):
        c = configs[ds]
        md.append(f"- `{ds}`: CLEAN source `{c['training_source']}`, train "
                  f"{c['train_range'][0]} → {c['train_range'][1]}, "
                  f"{c['n_train_sequences']:,} valid {c['lookback']}-step sequences "
                  f"(fit {c['n_fit_sequences']:,}, val {c['n_val_sequences']:,}), "
                  f"epochs {c['epochs_actual']}/{c['epochs_requested']} "
                  f"(early_stopped={c['early_stopped']}), best val_loss "
                  f"{c['best_val_loss']:.6f}, threshold {c['threshold_value']:.6f} "
                  f"({c['threshold_method']}), TF {c['tensorflow_version']}.")
    md.append("")
    md.append("## Architecture and features")
    md.append("")
    md.append(f"LSTM autoencoder: `{configs['jena']['architecture']}`. "
              f"30 temporal features (documented subset of the Phase 7 94-feature "
              "allowlist; full list in `feature_manifest.json`). Scaler: StandardScaler "
              "fit on eligible finite clean rows, frozen for evaluation. Official score: "
              "final-timestep MSE (HIGHER = MORE anomalous); full-sequence MSE diagnostic.")
    md.append("")
    md.append("## Row metrics (frozen threshold)")
    md.append("")
    md.append("| Dataset | Split | Precision | Recall | F1 | FPR | FNR |")
    md.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in ("test_in_distribution", "test_generalization"):
            m = sel(dataset=ds, split=split, method="lstm_ae", scope="overall")
            md.append(f"| {ds} | {split} | {_f(m['precision'])} | {_f(m['recall'])} | {_f(m['f1'])} | "
                      f"{_f(m['fpr'])} | {_f(m['fnr'])} |")
    md.append("")
    md.append("## Event metrics")
    md.append("")
    md.append("| Dataset | Split | Events | Detected | Recall | Lat med | Lat mean |")
    md.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            m = sel(dataset=ds, split=split, method="lstm_ae", scope="event", group="all")
            md.append(f"| {ds} | {split} | {m['events']} | {m['events_detected']} | "
                      f"{_f(m['event_recall'])} | {_f(m['latency_median_min'])} | {_f(m['latency_mean_min'])} |")
    md.append("")
    md.append("## Per-fault row recall")
    md.append("")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            parts = []
            for fault in ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE", "SPIKE_PLUS_DRIFT"):
                matches = [m for m in summary if m["dataset"] == ds and m["split"] == split
                           and m["method"] == "lstm_ae" and m["scope"] == "fault_type"
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
        m = sel(dataset=ds, split="test_generalization", method="lstm_ae",
                scope="event_by_fault", group="SPIKE_PLUS_DRIFT")
        r = sel(dataset=ds, split="test_generalization", method="lstm_ae",
                scope="fault_type", group="SPIKE_PLUS_DRIFT")
        md.append(f"- {ds}: {m['events_detected']}/{m['events']} events "
                  f"(recall {_f(m['event_recall'])}), row recall {_f(r['recall'])}.")
    md.append("")
    md.append("## False positives")
    md.append("")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            m = sel(dataset=ds, split=split, method="lstm_ae", scope="false_positive",
                    group="background")
            md.append(f"- {ds}/{split}: {m['false_positive_count']:,}/{m['background_rows']:,} "
                      f"background flagged (rate {_f(m['background_flag_rate'])}, "
                      f"{_f(m['fp_per_10k'])}/10k). No root-cause inference.")
    md.append("")
    md.append("## Phase 6 / Phase 7 comparison (descriptive; no winner declared)")
    md.append("")
    for c in comparison:
        if c["scope"] != "overall":
            continue
        ref = c["reference_method"]
        prefix = "baseline" if ref in ("zscore", "iqr") else "iforest"
        md.append(f"- {c['dataset']}/{c['split']} row vs {ref}: "
                  f"P {_f(c.get(prefix + '_precision'))} → LSTM {_f(c['lstm_precision'])}; "
                  f"R {_f(c.get(prefix + '_recall'))} → LSTM {_f(c['lstm_recall'])}; "
                  f"F1 {_f(c.get(prefix + '_f1'))} → LSTM {_f(c['lstm_f1'])}.")
    md.append("")
    md.append("Full side-by-side (incl. event recall/latency) in `phase6_phase7_comparison.csv`.")
    md.append(f"Command: `python -m src.lstm_autoencoder.run` (~{exec_seconds:.0f}s). "
              "No tuning on ID/OOD.")
    md.append("")
    return "\n".join(md)


if __name__ == "__main__":
    run_lstm_pipeline()
