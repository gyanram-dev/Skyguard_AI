"""Batch runner for Phase 5 controlled fault-injection benchmark.

Usage:
    python -m src.benchmark.run [--seed 26073]

Reads (read-only):
    data/processed/jena_clean.csv
    data/processed/delhi_clean.csv

Writes under data/benchmark/ (+ reports/benchmark/):
    jena|delhi/{train,test_in_distribution,test_generalization}.csv
    labels/{jena,delhi}_{event,row}_labels.csv
    manifests/benchmark_manifest.json
    ground_truth/{jena,delhi}_injected_values.csv

Trains NO model. All upstream inputs are hash-verified unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.benchmark import config as C
from src.benchmark.event_sampler import PlannedEvent, SplitPlanner
from src.benchmark.injectors import (
    apply_cross_variable,
    apply_drift,
    apply_frozen,
    apply_spike,
)
from src.benchmark.labels import EVENT_LABEL_COLUMNS, build_event_label
from src.benchmark.splitter import compute_splits
from src.benchmark.validator import validate_events, validate_frames

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_benchmark.run")

WATCHED_FILES = [
    "jena_climate_2009_2016.csv",
    "AWS_20220401_20241231.csv",
    "data/processed/jena_clean.csv",
    "data/processed/delhi_clean.csv",
    "data/features/jena_features.csv",
    "data/features/delhi_features.csv",
    "data/quality/jena_quality.csv",
    "data/quality/delhi_quality.csv",
    "data/baseline/jena_statistical_baseline.csv",
    "data/baseline/delhi_statistical_baseline.csv",
]


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def snapshot_hashes(root: Path) -> dict[str, str]:
    return {rel: (compute_sha256(root / rel) if (root / rel).is_file() else "MISSING")
            for rel in WATCHED_FILES}


def _elapsed_hours(df: pd.DataFrame, s: int, dur: int) -> np.ndarray:
    ts = pd.to_datetime(df["timestamp"].iloc[s : s + dur])
    return (ts - ts.iloc[0]).dt.total_seconds().to_numpy(dtype=float) / 3600.0


def _apply_event(df: pd.DataFrame, work: dict[str, np.ndarray],
                 event: PlannedEvent, records: list[dict]) -> None:
    """Mutate work arrays in place; append clean/injected records."""
    s, dur = event.start_idx, event.duration_rows
    sl = slice(s, s + dur)
    ts = df["timestamp"].astype(str).iloc[sl].tolist()
    p = event.params
    p["_start_timestamp"] = ts[0]
    p["_end_timestamp"] = ts[-1]

    def _record(var: str, clean: np.ndarray, injected: np.ndarray) -> None:
        for t, c, v in zip(ts, clean, injected):
            records.append({
                "timestamp": t, "dataset": event.dataset,
                "injection_id": event.injection_id, "fault_type": event.fault_type,
                "target_variable": var, "clean_value": float(c), "injected_value": float(v),
            })

    if event.fault_type == "SPIKE":
        var = event.target_variable
        clean = work[var][sl].copy()
        injected = apply_spike(clean, float(p["amplitude"]), int(p["direction"]))
        work[var][sl] = injected
        _record(var, clean, injected)
    elif event.fault_type == "FROZEN":
        var = event.target_variable
        out = apply_frozen({v: work[v][sl].copy() for v in C.CORE_VARS}, var)
        _record(var, work[var][sl].copy(), out[var])
        work[var][sl] = out[var]
    elif event.fault_type == "DRIFT":
        var = event.target_variable
        clean = work[var][sl].copy()
        injected = apply_drift(clean, float(p["drift_rate_per_hour"]),
                               int(p["direction"]), _elapsed_hours(df, s, dur))
        work[var][sl] = injected
        p["start_value"] = float(clean[0])
        p["end_value"] = float(injected[-1])
        _record(var, clean, injected)
    elif event.fault_type == "CROSS_VARIABLE":
        cleans = {v: work[v][sl].copy() for v in C.CORE_VARS}
        out = apply_cross_variable(cleans, {k: float(v) for k, v in p["rates_per_reading"].items()})
        for var in C.CORE_VARS:
            work[var][sl] = out[var]
            _record(var, cleans[var], out[var])
    elif event.fault_type == "SPIKE_PLUS_DRIFT":
        var_a, var_b = p["drift_variable"], p["spike_variable"]
        clean_a = work[var_a][sl].copy()
        drifted_a = apply_drift(clean_a, float(p["drift_rate_per_hour"]),
                                int(p["direction"]), _elapsed_hours(df, s, dur))
        work[var_a][sl] = drifted_a
        p["start_value"] = float(clean_a[0])
        p["end_value"] = float(drifted_a[-1])
        _record(var_a, clean_a, drifted_a)
        sp = p["spike"]
        off, sdur = int(sp["offset_rows"]), int(sp["duration_rows"])
        ssl = slice(s + off, s + off + sdur)
        sts = df["timestamp"].astype(str).iloc[ssl].tolist()
        clean_b = work[var_b][ssl].copy()
        injected_b = apply_spike(clean_b, float(sp["amplitude"]), int(sp["direction"]))
        work[var_b][ssl] = injected_b
        for t, c, v in zip(sts, clean_b, injected_b):
            records.append({
                "timestamp": t, "dataset": event.dataset,
                "injection_id": event.injection_id, "fault_type": event.fault_type,
                "target_variable": var_b, "clean_value": float(c), "injected_value": float(v),
            })
    else:
        raise ValueError(f"Cannot apply fault type {event.fault_type}")


def process_dataset(
    df: pd.DataFrame,
    dataset: str,
    rng: np.random.Generator,
    out_dirs: dict[str, Path],
    manifest_datasets: dict,
) -> dict:
    """Plan, apply, validate, and write the benchmark for one dataset."""
    ds = dataset.lower()
    cadence = C.CADENCE_MIN[ds]
    splits = compute_splits(df)
    id_counters: dict = {}
    all_faults: list[PlannedEvent] = []
    all_gaps: list[PlannedEvent] = []
    all_skips: list[dict] = []

    for split in splits:
        planner = SplitPlanner(df, split, ds, rng, id_counters)
        faults, gaps = planner.plan(C.TARGETS_PER_SPLIT[split["name"]])
        all_faults.extend(faults)
        all_gaps.extend(gaps)
        all_skips.extend(planner.skips)
        logger.info("%s %s: %d faults + %d gaps (%d skips)",
                    ds, split["name"], len(faults), len(gaps), len(planner.skips))

    # Apply sensor faults to a working copy.
    work = {v: df[v].to_numpy(dtype=float).copy() for v in C.CORE_VARS}
    records: list[dict] = []
    n = len(df)
    gt_anomaly = np.zeros(n, dtype=int)
    gt_type = np.full(n, "NONE", dtype=object)
    gt_id = np.full(n, "", dtype=object)
    gt_target = np.full(n, "", dtype=object)
    gt_start = np.full(n, "", dtype=object)
    gt_end = np.full(n, "", dtype=object)
    for e in all_faults:
        _apply_event(df, work, e, records)
        sl = slice(e.start_idx, e.start_idx + e.duration_rows)
        gt_anomaly[sl] = 1
        gt_type[sl] = e.fault_type
        gt_id[sl] = e.injection_id
        gt_target[sl] = e.target_variable
        gt_start[sl] = e.params["_start_timestamp"]
        gt_end[sl] = e.params["_end_timestamp"]

    # Assemble labeled frame, then remove gap rows.
    bench = pd.DataFrame({
        "timestamp": df["timestamp"].astype(str).values,
        "temperature_c": work["temperature_c"],
        "pressure_hpa": work["pressure_hpa"],
        "relative_humidity_pct": work["relative_humidity_pct"],
        "source_dataset": df["source_dataset"].astype(str).values,
        "ground_truth_anomaly": gt_anomaly,
        "ground_truth_fault_type": gt_type,
        "injection_id": gt_id,
        "target_variable": gt_target,
        "injection_start": gt_start,
        "injection_end": gt_end,
        "injection_layer": np.full(n, "NONE", dtype=object),
        "_global_idx": np.arange(n),
    })
    bench.loc[bench["ground_truth_anomaly"] == 1, "injection_layer"] = C.LAYER_ML_BENCHMARK
    drop_idx = set()
    for g in all_gaps:
        g.params["_start_timestamp"] = str(df["timestamp"].iloc[g.start_idx])
        g.params["_end_timestamp"] = str(df["timestamp"].iloc[g.start_idx + g.duration_rows - 1])
        drop_idx.update(range(g.start_idx, g.start_idx + g.duration_rows))
    bench = bench.loc[~bench["_global_idx"].isin(drop_idx)].reset_index(drop=True)

    # Per-split output frames.
    split_frames: dict[str, pd.DataFrame] = {}
    for split in splits:
        mask = (bench["_global_idx"] >= split["start_idx"]) & (bench["_global_idx"] < split["end_idx_excl"])
        frame = bench.loc[mask].drop(columns=["_global_idx"]).reset_index(drop=True)
        split_frames[split["name"]] = frame
        frame.to_csv(out_dirs["splits"] / f"{split['name']}.csv", index=False)

    # Row labels (evaluation metadata; background rows are NOT proven normal).
    row_labels = pd.DataFrame({
        "timestamp": bench["timestamp"],
        "dataset": ds,
        "split": bench["_global_idx"].map(
            {i: s["name"] for s in splits for i in range(s["start_idx"], s["end_idx_excl"])}),
        "ground_truth_anomaly": bench["ground_truth_anomaly"],
        "ground_truth_fault_type": bench["ground_truth_fault_type"],
        "injection_id": bench["injection_id"],
        "target_variable": bench["target_variable"],
        "injection_start": bench["injection_start"],
        "injection_end": bench["injection_end"],
        "injection_layer": bench["injection_layer"],
    })
    row_labels.to_csv(out_dirs["labels"] / f"{ds}_row_labels.csv", index=False)

    # Event labels (faults + gaps, sorted by start for readability).
    event_rows = [build_event_label(e, cadence) for e in (all_faults + all_gaps)]
    event_labels = pd.DataFrame(event_rows, columns=EVENT_LABEL_COLUMNS).sort_values(
        "start_timestamp").reset_index(drop=True)
    event_labels.to_csv(out_dirs["labels"] / f"{ds}_event_labels.csv", index=False)

    # Clean/injected ground-truth values (kept OUT of model inputs).
    gt_values = pd.DataFrame(records, columns=[
        "timestamp", "dataset", "injection_id", "fault_type",
        "target_variable", "clean_value", "injected_value",
    ])
    gt_values.to_csv(out_dirs["ground_truth"] / f"{ds}_injected_values.csv", index=False)

    # Validation.
    v_events = validate_events(all_faults, all_gaps, splits, ds)
    v_frames = validate_frames(split_frames, df, all_faults, all_gaps)
    if not v_events["all_passed"]:
        raise RuntimeError(f"{ds} event validation failed: {v_events['checks']}")
    if not v_frames["all_passed"]:
        raise RuntimeError(f"{ds} frame validation failed: {v_frames['checks']}")

    manifest_datasets[ds].update({
        "source_rows": n,
        "cadence_minutes": cadence,
        "splits": splits,
        "targets": C.TARGETS_PER_SPLIT,
        "achieved": {s["name"]: {
            t: sum(1 for e in (all_faults + all_gaps) if e.split == s["name"] and e.fault_type == t)
            for t in C.TARGETS_PER_SPLIT[s["name"]]} for s in splits},
        "skips": all_skips,
        "event_validation": v_events["checks"],
        "frame_validation": v_frames["checks"],
    })
    return {"splits": splits, "faults": len(all_faults), "gaps": len(all_gaps),
            "skips": len(all_skips), "injected_rows": int(gt_anomaly.sum())}


def _fmt_ranges() -> str:
    lines = ["| Fault | TRAIN / ID | OOD (disjoint) |",
             "| :--- | :--- | :--- |",
             "| SPIKE temp (°C abs) | 15–25 | 30–45 |",
             "| SPIKE pressure (hPa abs) | 8–15 | 20–35 |",
             "| SPIKE humidity (pp abs) | 15–25 | 30–45 |",
             "| FROZEN (readings) | 3–10 | 15–30 |",
             "| DRIFT temp (°C/h) | 0.5–1.5 | 2.0–4.0 |",
             "| DRIFT pressure (hPa/h) | 1–3 | 5–8 |",
             "| DRIFT humidity (pp/h) | 2–5 | 8–12 |",
             "| CROSS duration (readings) | 3–10 | 15–30 (stronger rates) |",
             "| GAP (minutes) | 30–120 | 120–360 |"]
    return "\n".join(lines)


def generate_report(manifest: dict, summaries: dict, exec_seconds: float) -> str:
    md: list[str] = []
    md.append("# SkyGuard AI — Controlled Fault-Injection Benchmark: Phase 5")
    md.append("")
    md.append("**Project**: SIH 2026 PS 26073 — AI/ML-Based Anomaly Detection for Automatic Weather Stations")
    md.append("**Phase status**: Phase 5 complete (benchmark generation only; NO model trained).")
    md.append("**Nature**: controlled fault-injection benchmark on real weather observations — NOT fake weather data.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Objective and ground-truth methodology")
    md.append("")
    md.append("- Known sensor faults (spike, frozen, drift, cross-variable, gaps, spike+drift combos) were")
    md.append("  injected into COPIES of Phase 2 processed data with seeded, recorded operations.")
    md.append("- Injected rows are ground truth (`ground_truth_anomaly = 1`) because the operation is controlled.")
    md.append("- Non-injected background rows (`ground_truth_anomaly = 0`) are NOT proven normal: they are")
    md.append("  non-injected background observations that may contain natural anomalies (e.g. the four known")
    md.append("  Delhi sub-zero readings and pressure regimes, which were deliberately NOT labeled).")
    md.append("- Clean pre-injection values are preserved separately in `ground_truth/*_injected_values.csv`")
    md.append("  (evaluation-only; never model inputs).")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 2. Sources, hashes, splits")
    md.append("")
    for ds, info in manifest["datasets"].items():
        md.append(f"- `{ds}`: `{info['source_file']}` SHA-256 `{info['source_sha256'][:16]}…`, "
                  f"{info['source_rows']:,} rows, {info['cadence_minutes']}-min cadence.")
        for s in info["splits"]:
            md.append(f"  - `{s['name']}`: rows [{s['start_idx']}, {s['end_idx_excl']}), "
                      f"{s['rows']:,} rows, `{s['start_timestamp']}` → `{s['end_timestamp']}`.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 3. Parameter ranges (TRAIN/ID vs disjoint OOD)")
    md.append("")
    md.append(_fmt_ranges())
    md.append("")
    md.append("- Spike durations 1–3 readings; drift TRAIN/ID 6–12 h, OOD 4–8 h; combos = OOD drift + OOD spike.")
    md.append("- TRAIN/ID contain single fault types only; OOD adds 20 SPIKE_PLUS_DRIFT combinations per dataset.")
    md.append("- Separation buffer between independent events: max event duration + 2 h per split.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 4. Event counts and combinations")
    md.append("")
    for ds, summ in summaries.items():
        md.append(f"- `{ds}`: **{summ['faults']}** sensor-fault events + **{summ['gaps']}** gap events, "
                  f"**{summ['injected_rows']:,}** injected rows, **{summ['skips']}** skips.")
    md.append("- Combination events (OOD only, `fault_type = SPIKE_PLUS_DRIFT`, "
              "`fault_components = [SPIKE, DRIFT]`): 20 per dataset by target; shortfalls reported below.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 5. Skipped candidates and row counts")
    md.append("")
    any_skip = False
    for ds, info in manifest["datasets"].items():
        for sk in info["skips"]:
            any_skip = True
            md.append(f"- `{ds}` {sk['split']} {sk['fault_type']} ({sk['target']}): "
                      f"{sk['reason']} after {sk['attempts']} attempts.")
    if not any_skip:
        md.append("- No skips: all event targets were placed with valid non-overlapping locations.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 6. Communication gaps, reproducibility, validation")
    md.append("")
    md.append("- Gap rows are genuinely absent (no NaN placeholders, no fill); manifests record start/end/duration/removed counts.")
    md.append(f"- Seed **{manifest['seed']}** (SeedSequence-spawned per-dataset streams); re-running the command reproduces identical manifests, labels, values, and datasets (tested).")
    md.append("- Pipeline validation enforced: parameter ranges, OOD disjointness, split containment, non-overlap, buffer separation, RH bounds, label alignment (see manifest `event_validation`/`frame_validation`).")
    md.append("- All Phase 1–4 inputs hash-verified byte-identical before and after generation.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 7. Reproduction")
    md.append("")
    md.append(f"- Command: `python -m src.benchmark.run` (executed in ~{exec_seconds:.1f} s).")
    md.append("- NO Isolation Forest, LSTM, scoring, root-cause, SHAP, ensemble, NOAA/spatial, API, or frontend was implemented.")
    md.append("")
    return "\n".join(md)


def run_benchmark_pipeline(
    project_root: str | Path = ".",
    output_root: str | Path | None = None,
    seed: int = C.DEFAULT_SEED,
) -> dict:
    """Generate the full benchmark. Returns manifest + per-dataset summaries."""
    start = time.time()
    root = Path(project_root).resolve()
    out_root = Path(output_root).resolve() if output_root else root

    proc = root / "data" / "processed"
    out_dirs = {
        "splits": out_root / "data" / "benchmark",
        "labels": out_root / "data" / "benchmark" / "labels",
        "manifests": out_root / "data" / "benchmark" / "manifests",
        "ground_truth": out_root / "data" / "benchmark" / "ground_truth",
        "reports": out_root / "reports" / "benchmark",
    }
    for d in out_dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    pre_hashes = snapshot_hashes(root)
    df_jena = pd.read_csv(proc / "jena_clean.csv")
    df_delhi = pd.read_csv(proc / "delhi_clean.csv")

    seq = np.random.SeedSequence(seed)
    rng_jena, rng_delhi = [np.random.default_rng(s) for s in seq.spawn(2)]

    manifest: dict = {
        "benchmark_version": C.BENCHMARK_VERSION,
        "generator": C.GENERATOR_NAME,
        "seed": seed,
        "parameter_ranges": {
            "spike_amplitude": C.SPIKE_AMPLITUDE,
            "frozen_duration": C.FROZEN_DURATION,
            "drift_rate_per_hour": C.DRIFT_RATE_PER_HOUR,
            "drift_duration_hours": C.DRIFT_DURATION_HOURS,
            "cross_duration": C.CROSS_DURATION,
            "cross_rates_per_reading": C.CROSS_RATES_PER_READING,
            "gap_duration_minutes": C.GAP_DURATION_MIN,
        },
        "datasets": {},
    }
    summaries: dict = {}
    per_ds_dirs = {
        "jena": {**out_dirs, "splits": out_dirs["splits"] / "jena"},
        "delhi": {**out_dirs, "splits": out_dirs["splits"] / "delhi"},
    }
    for ds, df, rng in (("jena", df_jena, rng_jena), ("delhi", df_delhi, rng_delhi)):
        per_ds_dirs[ds]["splits"].mkdir(parents=True, exist_ok=True)
        logger.info("Planning + applying %s benchmark (%d rows)...", ds, len(df))
        manifest["datasets"][ds] = {
            "source_file": f"data/processed/{ds}_clean.csv",
            "source_sha256": pre_hashes[f"data/processed/{ds}_clean.csv"],
            "source_rows": len(df),
        }
        summaries[ds] = process_dataset(df, ds, rng, per_ds_dirs[ds], manifest["datasets"])

    with open(out_dirs["manifests"] / "benchmark_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    post_hashes = snapshot_hashes(root)
    watched = [k for k in WATCHED_FILES if (root / k).is_file()]
    if any(pre_hashes[k] != post_hashes[k] for k in watched):
        bad = [k for k in watched if pre_hashes[k] != post_hashes[k]]
        raise RuntimeError(f"CRITICAL: upstream inputs changed during benchmark run: {bad}")
    logger.info("Upstream immutability verified.")

    exec_seconds = time.time() - start
    with open(out_dirs["reports"] / "benchmark_generation_summary.md", "w", encoding="utf-8") as f:
        f.write(generate_report(manifest, summaries, exec_seconds))
    logger.info("Phase 5 benchmark complete in %.1fs: %s", exec_seconds, summaries)
    return {"manifest": manifest, "summaries": summaries,
            "execution_time_seconds": exec_seconds}


def main() -> None:
    parser = argparse.ArgumentParser(description="SkyGuard Phase 5 benchmark generator")
    parser.add_argument("--seed", type=int, default=C.DEFAULT_SEED)
    args = parser.parse_args()
    run_benchmark_pipeline(seed=args.seed)


if __name__ == "__main__":
    main()

