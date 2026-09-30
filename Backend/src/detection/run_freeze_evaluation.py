"""Freeze-detector benchmark evaluation over the frozen artifacts.

Reproducible, read-only measurement of the freeze rule shipped in
``src.detection.freeze`` against the frozen benchmark labels. It never
re-runs ensemble inference: the frozen per-row predictions
(``data/ensemble/{ds}_ensemble_predictions.csv``) are the record of the
published run, and the freeze rule is applied on top exactly as the
serving paths do.

Measured per dataset/split (eligible rows only, mirroring the published
metric definitions):

- baseline ``ens_median`` FROZEN event recall,
- combined recall (ensemble verdict OR freeze confirmation),
- FROZEN events recovered by the freeze rule alone,
- background rows added by the freeze rule and the resulting FP/10k,
- the 4/5/6-reading threshold sweep that documents the chosen rule.

Writes ``reports/detection/freeze_evaluation.json`` and
``reports/detection/freeze_evaluation.md`` under ``Backend/`` and mirrors
both into the repository-root ``reports/`` tree.

Usage (from ``Backend/``):

    python -m src.detection.run_freeze_evaluation
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.detection import freeze as FE

SPLITS = ("test_in_distribution", "test_generalization")
DATASETS = ("delhi", "jena")
SWEEP = (4, 5, 6)
CHOSEN = FE.MIN_RUN_ROWS

FAULT_TYPES = ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE", "SPIKE_PLUS_DRIFT")


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load(ds: str, split: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Benchmark frame + frozen predictions for one dataset/split, aligned."""
    root = _backend_root()
    frame = pd.read_csv(root / "data" / "benchmark" / ds / f"{split}.csv")
    preds = pd.read_csv(root / "data" / "ensemble" / f"{ds}_ensemble_predictions.csv")
    preds = preds[preds["split"] == split].reset_index(drop=True)
    if len(preds) != len(frame):
        raise RuntimeError(
            f"{ds}/{split}: {len(preds)} predictions vs {len(frame)} benchmark rows")
    if not (preds["timestamp"].astype(str).to_numpy()
            == frame["timestamp"].astype(str).to_numpy()).all():
        raise RuntimeError(f"{ds}/{split}: prediction/benchmark timestamps differ")
    return frame, preds


def _split_metrics(ds: str, split: str, min_run_rows: int) -> dict:
    frame, preds = _load(ds, split)
    eligible = preds["evaluation_eligible"].to_numpy(dtype=int) == 1
    base = preds["ens_median_flag"].to_numpy(dtype=int) == 1
    run_rows, _ = FE.scan_frame(frame, min_run_rows=int(min_run_rows))
    freeze = run_rows > 0
    combined = base | freeze
    truth = frame["ground_truth_anomaly"].to_numpy(dtype=int) == 1
    used = eligible
    bg = used & ~truth
    tp = int((used & truth & combined).sum())
    fp = int((used & ~truth & combined).sum())
    fn = int((used & truth & ~combined).sum())
    tn = int((used & ~truth & ~combined).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else None)

    def _events(mask: np.ndarray) -> dict:
        out: dict = {}
        for fault in FAULT_TYPES:
            pos = np.where((frame["ground_truth_fault_type"] == fault).to_numpy())[0]
            pos = pos[eligible[pos]]
            if not len(pos):
                continue
            ids = frame["injection_id"].iloc[pos].dropna().unique()
            base_hits = freeze_hits = comb_hits = 0
            for inj in ids:
                members = pos[frame["injection_id"].iloc[pos].to_numpy() == inj]
                base_hits += int(base[members].any())
                freeze_hits += int(freeze[members].any())
                comb_hits += int(combined[members].any())
            out[fault] = {"events": int(len(ids)),
                          "ens_median_detected": int(base_hits),
                          "freeze_rule_detected": int(freeze_hits),
                          "combined_detected": int(comb_hits)}
        return out

    base_tp = int((used & truth & base).sum())
    base_fp = int((used & ~truth & base).sum())
    base_precision = base_tp / (base_tp + base_fp) if base_tp + base_fp else None
    base_recall = (base_tp / int((used & truth).sum())
                   if int((used & truth).sum()) else None)
    return {
        "dataset": ds,
        "split": split,
        "min_run_rows": int(min_run_rows),
        "eligible_rows": int(used.sum()),
        "background_rows": int(bg.sum()),
        "baseline": {
            "tp": base_tp,
            "fp": base_fp,
            "precision": round(base_precision, 6) if base_precision is not None else None,
            "recall": round(base_recall, 6) if base_recall is not None else None,
            "background_flags": int((bg & base).sum()),
            "fp_per_10k": round(float((bg & base).sum()) / max(1, int(bg.sum())) * 10000, 2),
        },
        "combined": {
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 6) if precision is not None else None,
            "recall": round(recall, 6) if recall is not None else None,
            "f1": round(f1, 6) if f1 is not None else None,
            "background_flags": int((bg & combined).sum()),
            "added_background_flags": int((bg & combined).sum()) - int((bg & base).sum()),
            "fp_per_10k": round(float((bg & combined).sum()) / max(1, int(bg.sum())) * 10000, 2),
        },
        "events": _events(combined),
    }


def build_report() -> dict:
    """Full sweep + chosen-threshold report over both datasets."""
    sweep: dict = {}
    for threshold in SWEEP:
        rows = []
        for ds in DATASETS:
            for split in SPLITS:
                m = _split_metrics(ds, split, threshold)
                froz = m["events"].get("FROZEN", {})
                rows.append({
                    "dataset": ds, "split": split,
                    "frozen_events": froz.get("events"),
                    "baseline_detected": froz.get("ens_median_detected"),
                    "combined_detected": froz.get("combined_detected"),
                    "added_background_flags": m["combined"]["added_background_flags"],
                    "baseline_fp_per_10k": m["baseline"]["fp_per_10k"],
                    "combined_fp_per_10k": m["combined"]["fp_per_10k"],
                })
        sweep[str(threshold)] = rows
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "rule": {
            "min_run_rows": CHOSEN,
            "variables": [name for _, name, _ in FE.VARIABLES],
            "exclusion": "relative humidity at 0/100 (saturation) is never a freeze",
            "causal": "a row is flagged only when its own observed run reaches the threshold",
            "gap_semantics": "NaN and communication-gap rows terminate runs",
            "severity": "LOW (>=6) < MEDIUM (>=12) < HIGH (>= 6-hour DQ row count)",
            "confidence": "run/(run+6) evidence-strength margin, not a probability",
        },
        "threshold_sweep": sweep,
        "chosen": {
            f"{ds}/{split}": _split_metrics(ds, split, CHOSEN)
            for ds in DATASETS for split in SPLITS
        },
    }


def _md(report: dict) -> str:
    lines = [
        "# Freeze detector — frozen benchmark evaluation",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "Rule: " + "; ".join(f"{k}={v}" for k, v in report["rule"].items()),
        "",
        f"Chosen threshold: **{CHOSEN} consecutive identical readings**.",
        "",
        "## Threshold sweep (FROZEN event recall vs added background flags)",
        "",
        "| reads | dataset | split | FROZEN events | ens_median | + freeze | added bg rows | bg FP/10k |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for threshold, rows in report["threshold_sweep"].items():
        for r in rows:
            lines.append(
                f"| {threshold} | {r['dataset']} | {r['split']} | "
                f"{r['frozen_events']} | {r['baseline_detected']} | "
                f"{r['combined_detected']} | {r['added_background_flags']} | "
                f"{r['baseline_fp_per_10k']} -> {r['combined_fp_per_10k']} |")
    lines += ["", f"## Chosen threshold ({CHOSEN}) details", ""]
    for key, m in report["chosen"].items():
        lines += [
            f"### {key}",
            "",
            f"- eligible rows: {m['eligible_rows']}, background rows: {m['background_rows']}",
            f"- baseline: {m['baseline']['background_flags']} background flags"
            f" ({m['baseline']['fp_per_10k']}/10k)",
            f"- combined: {m['combined']['background_flags']} background flags"
            f" ({m['combined']['fp_per_10k']}/10k),"
            f" added {m['combined']['added_background_flags']} rows",
            "",
            "| fault | events | ens_median detected | freeze rule detected | combined |",
            "|---|---|---|---|---|",
        ]
        for fault, ev in m["events"].items():
            lines.append(f"| {fault} | {ev['events']} | {ev['ens_median_detected']} |"
                         f" {ev['freeze_rule_detected']} | {ev['combined_detected']} |")
        lines.append("")
    lines += [
        "Notes: predictions are the frozen record of the published benchmark run;"
        " the freeze rule is applied post hoc exactly as in serving."
        " Events count an injection as detected when any eligible row inside its"
        " window is flagged. Controlled injections are synthetic labels, not real"
        " sensor faults.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    report = build_report()
    root = _backend_root()
    body = json.dumps(report, indent=2)
    md = _md(report)
    targets = [root / "reports" / "detection"]
    repo_reports = root.parent / "reports" / "detection"
    if (root.parent / "reports").is_dir():
        targets.append(repo_reports)
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
        (target / "freeze_evaluation.json").write_text(body, encoding="utf-8")
        (target / "freeze_evaluation.md").write_text(md, encoding="utf-8")
        print(f"wrote {target / 'freeze_evaluation.json'}")


if __name__ == "__main__":
    main()
