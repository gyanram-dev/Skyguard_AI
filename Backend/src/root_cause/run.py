"""Phase 11 pipeline: train, diagnose, explain, evaluate root causes.

Usage:
    python -m src.root_cause.run

Training labels: benchmark TRAIN fault rows only (supervised fault
classification explicitly allows them). ID/OOD labels are measurement
only. Frozen detectors are scored, never retrained; no threshold is
modified. Writes: models/root_cause/*, data/root_cause/*,
reports/root_cause/*.
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

from src.root_cause import classifier as CL
from src.root_cause import confidence as CF
from src.root_cause import evaluator as E
from src.root_cause import explain as EX
from src.root_cause import unknown_mixed as UM
from src.root_cause.features import (
    DIAGNOSTIC_FEATURES,
    KNOWN_CLASSES,
    TRAIN_CLASS_MAP,
    build_evidence_frame,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_root_cause.run")

SPLITS = ("train", "test_in_distribution", "test_generalization")
EVAL_SPLITS = ("test_in_distribution", "test_generalization")
CLASSES_EVAL = ("SPIKE", "FROZEN", "DRIFT", "CROSS", "MIXED", "UNKNOWN")
SHAP_PER_CLASS = 25
SHAP_SEED = 26073

UPSTREAM_WATCH = [
    "data/benchmark/jena/train.csv",
    "data/benchmark/jena/test_in_distribution.csv",
    "data/benchmark/jena/test_generalization.csv",
    "data/benchmark/delhi/train.csv",
    "data/benchmark/delhi/test_in_distribution.csv",
    "data/benchmark/delhi/test_generalization.csv",
    "data/benchmark/labels/jena_event_labels.csv",
    "data/benchmark/labels/delhi_event_labels.csv",
    "models/ensemble/jena_calibration.joblib",
    "models/ensemble/delhi_calibration.joblib",
    "data/isolation_forest/jena_isolation_forest_predictions.csv",
    "data/isolation_forest/delhi_isolation_forest_predictions.csv",
    "data/lstm_autoencoder/jena_lstm_predictions.csv",
    "data/lstm_autoencoder/delhi_lstm_predictions.csv",
    "data/ensemble/jena_ensemble_predictions.csv",
    "data/ensemble/delhi_ensemble_predictions.csv",
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


def run_root_cause_pipeline(project_root: str | Path = ".") -> dict:
    """Train, diagnose, explain, and evaluate root causes."""
    start = time.time()
    root = Path(project_root).resolve()
    bench_root = root / "data" / "benchmark"
    model_dir = root / "models" / "root_cause"
    pred_dir = root / "data" / "root_cause"
    rep_dir = root / "reports" / "root_cause"
    shap_dir = rep_dir / "shap_examples"
    for d in (model_dir, pred_dir, rep_dir, shap_dir):
        d.mkdir(parents=True, exist_ok=True)

    pre = {rel: _sha(root / rel) for rel in UPSTREAM_WATCH}
    metrics_rows: list[dict] = []
    confusion_rows: list[dict] = []
    unknown_rows: list[dict] = []
    mixed_rows: list[dict] = []
    end_to_end: list[dict] = []
    configs: dict = {}
    noaa_lookup = _noaa_lookup(root)

    for ds in ("jena", "delhi"):
        bench = {sp: pd.read_csv(bench_root / ds / f"{sp}.csv") for sp in SPLITS}
        events = pd.read_csv(bench_root / "labels" / f"{ds}_event_labels.csv")
        logger.info("Building %s train evidence (supervised fault labels)...", ds)
        train_ev = E.build_split_evidence(bench["train"], ds, "train", root)
        model, train_info, train_frame = E.fit_dataset(train_ev)
        CL.save_artifact(model, model_dir / f"{ds}_root_cause.joblib")
        explainer = _build_explainer(model)
        CL.save_artifact(explainer, model_dir / f"{ds}_root_cause_explainer.joblib")

        configs[ds] = {
            "dataset": ds,
            "training_source": f"data/benchmark/{ds}/train.csv",
            "training_period": [str(bench["train"]["timestamp"].iloc[0]),
                                str(bench["train"]["timestamp"].iloc[-1])],
            "training_labels_used": "benchmark TRAIN fault rows only "
                                    "(SPIKE/FROZEN/DRIFT/CROSS_VARIABLE; gaps and normals excluded)",
            "id_labels_used_for_training": False,
            "ood_labels_used_for_training": False,
            "class_mapping": {**TRAIN_CLASS_MAP, "COMMUNICATION_GAP": "excluded", "NONE": "excluded"},
            "n_train_fault_rows": int((train_ev["ground_truth_fault_type"].isin(
                ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE"))).sum()),
            "n_train_complete_rows": train_info["n_complete_rows"],
            "n_train_excluded_incomplete": train_info["n_excluded_incomplete"],
            "feature_list": list(DIAGNOSTIC_FEATURES),
            "n_features": len(DIAGNOSTIC_FEATURES),
            "classifier": "RandomForestClassifier",
            "classifier_params": CL.RF_PARAMS,
            "unknown_rule": f"max proba < {CF.UNKNOWN_PROBA} -> UNKNOWN (frozen on train-validation)",
            "mixed_rule": (f"top >= {CF.UNKNOWN_PROBA} and second >= {CF.MIXED_SECOND_PROBA} "
                           f"and gap <= {CF.MIXED_GAP} -> MIXED (frozen on train-validation)"),
            "validation_stats": train_info["validation_stats"],
            "shap_method": "shap.TreeExplainer (exact) on stratified detected-anomaly sample",
            "shap_sample_per_class": SHAP_PER_CLASS,
            "seed": CL.MODEL_SEED,
            "software_versions": {"pandas": pd.__version__, "numpy": np.__version__,
                                  "sklearn": __import__("sklearn").__version__,
                                  "shap": __import__("shap").__version__},
        }

        pred_frames = []
        for split in SPLITS:
            ev = train_ev if split == "train" else E.build_split_evidence(bench[split], ds, split, root)
            diagnosed = E.diagnose_frame(model, ev)
            diagnosed = _add_explanations(diagnosed, model, explainer, ds, split,
                                          shap_dir, noaa_lookup if ds == "delhi" else {})
            pred_frames.append(diagnosed)
            if split != "train":
                _evaluate_split(diagnosed, ev, events, ds, split, metrics_rows,
                                confusion_rows, unknown_rows, mixed_rows, end_to_end)
            logger.info("%s %s: fault_rows=%d diagnosed=%d detected=%d", ds, split,
                        int((diagnosed["ground_truth_anomaly"] == 1).sum()),
                        int(diagnosed["has_diagnosis"].sum()),
                        int(((diagnosed["ground_truth_anomaly"] == 1)
                             & (diagnosed[E.GATE_FLAG] == 1)).sum()))
        cols = ["timestamp", "split", "temperature_c", "pressure_hpa", "relative_humidity_pct",
                "ground_truth_anomaly", "ground_truth_fault_type", "injection_id",
                "evaluation_eligible", E.GATE_FLAG, "has_diagnosis",
                "predicted_class", "confidence", "runner_up",
                *[f"proba_{c}" for c in model.classes_], "explanation", "shap_top5"]
        faults_only = pd.concat(pred_frames, ignore_index=True)
        faults_only = faults_only[faults_only["ground_truth_anomaly"] == 1]
        faults_only.to_csv(pred_dir / f"{ds}_root_cause_predictions.csv", index=False)

    pd.DataFrame(metrics_rows).to_csv(rep_dir / "root_cause_metrics.csv", index=False)
    pd.DataFrame(confusion_rows).to_csv(rep_dir / "confusion_matrices.csv", index=False)
    pd.DataFrame(unknown_rows).to_csv(rep_dir / "unknown_metrics.csv", index=False)
    pd.DataFrame(mixed_rows).to_csv(rep_dir / "mixed_metrics.csv", index=False)
    pd.DataFrame(end_to_end).to_csv(rep_dir / "end_to_end_diagnosis.csv", index=False)
    with open(rep_dir / "model_config.json", "w", encoding="utf-8") as f:
        json.dump(configs, f, indent=2, default=str)
    with open(rep_dir / "feature_manifest.json", "w", encoding="utf-8") as f:
        json.dump({"n_features": len(DIAGNOSTIC_FEATURES),
                   "features": list(DIAGNOSTIC_FEATURES),
                   "class_mapping": TRAIN_CLASS_MAP,
                   "forbidden_guard": "src.isolation_forest.features.assert_no_forbidden_columns",
                   "training_labels": "benchmark TRAIN fault rows only"}, f, indent=2)
    with open(rep_dir / "root_cause_evaluation.md", "w", encoding="utf-8") as f:
        f.write(generate_markdown(configs, metrics_rows, end_to_end, time.time() - start))
    post = {rel: _sha(root / rel) for rel in UPSTREAM_WATCH}
    if pre != post:
        raise RuntimeError("CRITICAL: upstream inputs changed during root-cause run")
    exec_seconds = time.time() - start
    logger.info("Phase 11 complete in %.1fs.", exec_seconds)
    return {"metrics": metrics_rows, "execution_time_seconds": exec_seconds}


def _build_explainer(model):
    """Fit a TreeExplainer on the frozen classifier (genuine artifact)."""
    import shap

    return shap.TreeExplainer(model)


def _noaa_lookup(root: Path) -> dict:
    """Delhi timestamp -> spatial context (empty when unavailable)."""
    path = root / "reports" / "noaa" / "aws_context_validation.csv"
    if not path.is_file():
        return {}
    ctx = pd.read_csv(path, usecols=["timestamp_ist", "ctx_temp_difference",
                                     "ctx_temp_station_count"])
    out = {}
    for _, row in ctx.iterrows():
        if pd.notna(row["ctx_temp_difference"]) and int(row["ctx_temp_station_count"]) > 0:
            out[str(row["timestamp_ist"])] = {"temp_diff": float(row["ctx_temp_difference"]),
                                              "n": int(row["ctx_temp_station_count"])}
    return out


def _add_explanations(diagnosed: pd.DataFrame, model, explainer, ds: str, split: str,
                      shap_dir: Path, noaa_lookup: dict) -> pd.DataFrame:
    """Template + SHAP explanations for a stratified detected-anomaly sample."""
    import shap

    out = diagnosed.copy()
    out["explanation"] = ""
    out["shap_top5"] = ""
    det = out[(out["has_diagnosis"]) & (out[E.GATE_FLAG] == 1)
              & (out["ground_truth_anomaly"] == 1)]
    rng = np.random.default_rng(SHAP_SEED)
    sample_idx: list = []
    for label in list(model.classes_) + ["MIXED", "UNKNOWN"]:
        pool = det.index[det["predicted_class"] == label].to_numpy()
        if len(pool) == 0:
            continue
        take = rng.choice(pool, size=min(SHAP_PER_CLASS, len(pool)), replace=False)
        sample_idx.extend(take.tolist())
    if not sample_idx:
        return out
    X_sample, _ = build_evidence_frame(out.loc[sample_idx, list(DIAGNOSTIC_FEATURES)])
    feature_names = list(X_sample.columns)
    shap_values = explainer.shap_values(X_sample)
    if isinstance(shap_values, list):
        shap_values = np.stack(shap_values, axis=-1)
    shap_values = np.asarray(shap_values)
    argmax = np.argmax(out.loc[sample_idx, [f"proba_{c}" for c in model.classes_]]
                       .to_numpy(dtype=float), axis=1)
    for pos, idx in enumerate(sample_idx):
        row = out.loc[idx]
        cls_vals = shap_values[pos, :, int(argmax[pos])] if shap_values.ndim == 3 else shap_values[pos]
        top = EX.shap_top_features(cls_vals, feature_names,
                                   X_sample.iloc[pos].to_numpy(dtype=float))
        out.loc[idx, "shap_top5"] = "; ".join(
            f"{t['feature']}={t['shap_value']:+.3f}" for t in top)
        out.loc[idx, "explanation"] = EX.compose_explanation(
            str(row["predicted_class"]), row, top,
            EX.noaa_sentence_for(str(row["timestamp"]), noaa_lookup))
        payload = {"dataset": ds, "split": split, "timestamp": str(row["timestamp"]),
                   "predicted_class": str(row["predicted_class"]),
                   "confidence": float(row["confidence"]),
                   "runner_up": str(row["runner_up"]),
                   "true_class": str(_true_class(row)),
                   "top_features": top,
                   "explanation": str(out.loc[idx, "explanation"])}
        safe_ts = str(row["timestamp"]).replace(":", "-").replace(" ", "_")
        with open(shap_dir / f"{ds}_{split}_{safe_ts}.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    return out


def _true_class(row) -> str:
    """Benchmark fault type mapped to evaluation classes."""
    return {"CROSS_VARIABLE": "CROSS", "SPIKE_PLUS_DRIFT": "MIXED"}.get(
        str(row["ground_truth_fault_type"]), str(row["ground_truth_fault_type"]))


def _evaluate_split(diagnosed: pd.DataFrame, ev: pd.DataFrame, events: pd.DataFrame,
                    ds: str, split: str, metrics_rows: list, confusion_rows: list,
                    unknown_rows: list, mixed_rows: list, end_to_end: list) -> None:
    """Classifier, UNKNOWN/MIXED, per-variable, and end-to-end metrics."""
    faults = diagnosed[diagnosed["ground_truth_anomaly"] == 1].copy()
    faults["true_class"] = faults.apply(_true_class, axis=1)
    oper = faults[faults["has_diagnosis"] & (faults[E.GATE_FLAG] == 1)].copy()
    truth = oper["true_class"].tolist()
    pred = oper["predicted_class"].tolist()
    stats = E.classification_metrics(truth, pred, list(CLASSES_EVAL))
    unknown_rate = float((oper["predicted_class"] == "UNKNOWN").mean()) if len(oper) else float("nan")
    no_unk = [(t, p) for t, p in zip(truth, pred) if p != "UNKNOWN"]
    if no_unk:
        s2 = E.classification_metrics([t for t, _ in no_unk], [p for _, p in no_unk],
                                      list(CLASSES_EVAL))
        acc_excl = s2["accuracy"]
    else:
        acc_excl = float("nan")
    metrics_rows.append({"dataset": ds, "split": split, "scope": "classifier_operating",
                         "n_fault_rows": int(len(faults)),
                         "n_detected": int((faults[E.GATE_FLAG] == 1).sum()),
                         "n_diagnosed": int(len(oper)),
                         "accuracy_incl_unknown": stats["accuracy"],
                         "accuracy_excl_unknown": acc_excl,
                         "unknown_rate": unknown_rate,
                         **{f"{k}": v for k, v in stats.items()
                            if k.startswith("macro_")},
                         "per_class": json.dumps(stats["per_class"])})
    no_unk = [(t, p) for t, p in zip(truth, pred) if p != "UNKNOWN"]
    unknown_rows.append({"dataset": ds, "split": split,
                         "n_diagnosed": int(len(oper)),
                         "n_unknown": int((oper["predicted_class"] == "UNKNOWN").sum()),
                         "unknown_rate": unknown_rate,
                         "accuracy_incl_unknown": stats["accuracy"],
                         "accuracy_excl_unknown": acc_excl})
    for actual, row in stats["confusion"].items():
        for predicted, count in row.items():
            confusion_rows.append({"dataset": ds, "split": split, "actual": actual,
                                   "predicted": predicted, "count": int(count)})
    combos = oper[oper["true_class"] == "MIXED"]
    mixed_rows.append({"dataset": ds, "split": split, "n_combo_rows": int(len(combos)),
                       "n_combo_mixed": int((combos["predicted_class"] == "MIXED").sum()),
                       "combo_mixed_rate": float((combos["predicted_class"] == "MIXED").mean())
                       if len(combos) else float("nan"),
                       "combo_unknown_rate": float((combos["predicted_class"] == "UNKNOWN").mean())
                       if len(combos) else float("nan")})
    var_map = dict(zip(events["injection_id"].astype(str), events["target_variable"].astype(str)))
    oper["event_target"] = oper["injection_id"].map(var_map)
    for var, label in (("temperature_c", "Temperature"), ("pressure_hpa", "Pressure"),
                       ("relative_humidity_pct", "Relative Humidity")):
        sub = oper[oper["event_target"] == var]
        if len(sub):
            s3 = E.classification_metrics(sub["true_class"].tolist(),
                                          sub["predicted_class"].tolist(), list(CLASSES_EVAL))
            metrics_rows.append({"dataset": ds, "split": split, "scope": f"variable_{label}",
                                 "n_diagnosed": int(len(sub)), "accuracy_incl_unknown": s3["accuracy"],
                                 "macro_f1": s3["macro_f1"]})
    for _, event in events[events["fault_type"] != "COMMUNICATION_GAP"].iterrows():
        if event["split"] != split:
            continue
        sub = faults[faults["injection_id"] == event["injection_id"]]
        flagged = sub[sub[E.GATE_FLAG] == 1]
        detected = len(flagged) > 0
        diag = flagged[flagged["has_diagnosis"]]
        expected = {"CROSS_VARIABLE": "CROSS", "SPIKE_PLUS_DRIFT": "MIXED"}.get(
            event["fault_type"], event["fault_type"])
        if len(diag) == 0:
            predicted, correct = ("UNDIAGNOSED" if detected else "MISSED"), False
        else:
            votes = diag["predicted_class"].value_counts()
            top_count = int(votes.max())
            winners = votes[votes == top_count].index.tolist()
            if len(winners) == 1:
                predicted = winners[0]
            else:
                predicted = diag.sort_values("timestamp").iloc[0]["predicted_class"]
            correct = bool(predicted == expected)
        end_to_end.append({"dataset": ds, "split": split, "injection_id": event["injection_id"],
                           "fault_type": event["fault_type"], "expected_class": expected,
                           "detected": int(detected), "n_flagged": int(len(flagged)),
                           "n_diagnosed": int(len(diag)), "predicted_class": str(predicted),
                           "correct": int(correct)})


def generate_markdown(configs: dict, metrics_rows: list[dict], end_to_end: list[dict],
                      exec_seconds: float) -> str:
    def sel(**kw):
        return next(m for m in metrics_rows if all(m.get(k) == v for k, v in kw.items()))

    ee = pd.DataFrame(end_to_end)
    md: list[str] = []
    md.append("# Root-Cause Classification + Explainability — Evaluation: Phase 11")
    md.append("")
    md.append("**Scope**: post-detection diagnosis only. Supervised on benchmark TRAIN "
              "fault rows (explicitly allowed); ID/OOD labels measurement-only. No "
              "detector retraining, no threshold changes, no SHAP causality claims.")
    md.append("")
    md.append("## Training and rules (per dataset)")
    md.append("")
    for ds in ("jena", "delhi"):
        c = configs[ds]
        v = c["validation_stats"]
        md.append(f"- `{ds}`: train {c['training_period'][0]} → {c['training_period'][1]}, "
                  f"{c['n_train_complete_rows']:,} complete fault rows "
                  f"({c['n_train_excluded_incomplete']:,} excluded incomplete), "
                  f"classes {c['classifier_params']}; internal validation accuracy "
                  f"{_f(v['accuracy'])} (correct median confidence "
                  f"{_f(v['correct_median_confidence'])}, wrong "
                  f"{_f(v['wrong_median_confidence'])}); {c['unknown_rule']}; {c['mixed_rule']}.")
    md.append("")
    md.append("## Classifier metrics on detected anomalies (operating set)")
    md.append("")
    md.append("| Dataset | Split | Diagnosed | Acc | Acc excl UNKNOWN | Macro F1 | UNKNOWN rate |")
    md.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            m = sel(dataset=ds, split=split, scope="classifier_operating")
            md.append(f"| {ds} | {split} | {m['n_diagnosed']:,} | {_f(m['accuracy_incl_unknown'])} | "
                      f"{_f(m['accuracy_excl_unknown'])} | {_f(m['macro_f1'])} | {_f(m['unknown_rate'])} |")
    md.append("")
    md.append("UNKNOWN rates and excl-UNKNOWN accuracy live in `unknown_metrics.csv`; "
              "MIXED combo behavior in `mixed_metrics.csv`.")
    md.append("")
    md.append("## End-to-end anomaly → diagnosis (per event)")
    md.append("")
    md.append("| Dataset | Split | Events | Detected | Correct diagnosis | End-to-end rate | "
              "Conditional accuracy |")
    md.append("| :--- | :--- | ---: | ---: | ---: | ---: | ---: |")
    for ds in ("jena", "delhi"):
        for split in EVAL_SPLITS:
            sub = ee[(ee["dataset"] == ds) & (ee["split"] == split)]
            det = int(sub["detected"].sum())
            corr = int(sub["correct"].sum())
            diag = sub[sub["n_diagnosed"] > 0]
            cond = (diag["correct"].sum() / len(diag)) if len(diag) else float("nan")
            md.append(f"| {ds} | {split} | {len(sub)} | {det} | {corr} | {_f(corr / len(sub))} | "
                      f"{_f(cond)} |")
    md.append("")
    md.append("Confusion matrices in `confusion_matrices.csv`; worked SHAP examples in "
              "`shap_examples/` (wording: features contributing to the prediction, not causes).")
    md.append(f"Command: `python -m src.root_cause.run` (~{exec_seconds:.0f}s). No tuning on ID/OOD.")
    md.append("")
    return "\n".join(md)


if __name__ == "__main__":
    run_root_cause_pipeline()
