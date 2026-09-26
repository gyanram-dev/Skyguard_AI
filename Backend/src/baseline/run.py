"""Batch runner for Phase 4 Traditional Statistical QC Baseline.

Usage:
    python -m src.baseline.run

Reads (read-only):
    data/features/jena_features.csv
    data/features/delhi_features.csv
    data/quality/jena_quality.csv
    data/quality/delhi_quality.csv

Writes:
    data/baseline/jena_statistical_baseline.csv
    data/baseline/delhi_statistical_baseline.csv
    reports/baseline/statistical_baseline_summary.md
    reports/baseline/baseline_schema.json

Verifies all upstream inputs remain byte-for-byte unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from src.baseline.iqr_baseline import IQR_FACTOR
from src.baseline.statistical_baseline import (
    BASELINE_COLUMNS,
    build_statistical_baseline,
)
from src.baseline.validation import validate_baseline_frame
from src.baseline.zscore_baseline import Z_THRESHOLD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_baseline.run")

WATCHED_FILES = [
    "jena_climate_2009_2016.csv",
    "AWS_20220401_20241231.csv",
    "data/processed/jena_clean.csv",
    "data/processed/delhi_clean.csv",
    "data/features/jena_features.csv",
    "data/features/delhi_features.csv",
    "data/quality/jena_quality.csv",
    "data/quality/delhi_quality.csv",
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


def describe_column(col: str) -> tuple[str, str]:
    """Return (category, description) for schema documentation."""
    if col in ("timestamp", "source_dataset"):
        return ("metadata", "Passthrough identifier from Phase 3 features")
    if col in ("temperature_c", "pressure_hpa", "relative_humidity_pct"):
        return ("observation_passthrough", f"Raw physical value, never modified ({col})")
    if col.endswith("_zscore_baseline"):
        return ("zscore_view", "Causal 2h z-score; NaN when history/variance insufficient")
    if col.endswith("_zscore_flag"):
        return ("zscore_view", "1 if |z| > 3.0, 0 if within, NaN if z unavailable")
    if col.endswith("_iqr_flag"):
        return ("iqr_view", "1 if outside causal 2h Tukey bounds, 0 if inside, NaN if history missing")
    if col == "statistical_flags_available":
        return ("combined", "Variables with >= 1 computable baseline view (0-3)")
    if col == "statistical_anomaly_count":
        return ("combined", "Variables with any baseline flag == 1")
    if col == "statistical_baseline_flag":
        return ("combined", "1 if any variable flagged, 0 if all clear, NaN if nothing computable")
    if col == "statistical_baseline_reason":
        return ("combined", "Firing components or insufficient_history/missing_input/data_quality_excluded")
    if col == "baseline_status":
        return ("combined", "COMPUTED, INSUFFICIENT_HISTORY, or DATA_QUALITY_EXCLUDED")
    return ("unknown", "")


def generate_summary_markdown(
    jena_summary: dict,
    delhi_summary: dict,
    pre_hashes: dict[str, str],
    post_hashes: dict[str, str],
    exec_seconds: float,
) -> str:
    md: list[str] = []
    md.append("# SkyGuard AI — Traditional Statistical QC Baseline: Phase 4")
    md.append("")
    md.append("**Project**: SIH 2026 PS 26073 — AI/ML-Based Anomaly Detection for Automatic Weather Stations")
    md.append("**Phase status**: Phase 4 complete (traditional QC comparison baseline; NOT an AI model).")
    md.append("**Safety check**: No ML, no synthetic anomalies, no input modifications, strictly causal.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Objective")
    md.append("")
    md.append("Provide the conventional rolling-statistics reference that answers “would traditional QC")
    md.append("flag this observation?”, so future context-aware detectors can be measured against it")
    md.append("(baseline-vs-system comparison for the PPT). No detection accuracy is claimed here:")
    md.append("no labeled ground truth exists yet.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 2. Why this is a traditional QC baseline (not AI)")
    md.append("")
    md.append("- Fixed rolling moments and Tukey bounds; nothing is learned, fitted, or trained.")
    md.append("- Thresholds (|z| > 3.0, 1.5×IQR) are textbook conventions, documented as configuration.")
    md.append("- It is the comparison point, not the SkyGuard decision.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 3. Datasets used (read-only)")
    md.append("")
    md.append("| Dataset | Feature input | Quality input | Rows | Hash unchanged |")
    md.append("| :--- | :--- | :--- | ---: | :--- |")
    for label, feat_rel, qual_rel, summary in (
        ("Jena", "data/features/jena_features.csv", "data/quality/jena_quality.csv", jena_summary),
        ("Delhi", "data/features/delhi_features.csv", "data/quality/delhi_quality.csv", delhi_summary),
    ):
        ok = all(pre_hashes[r] == post_hashes[r] for r in (feat_rel, qual_rel))
        md.append(f"| {label} | `{feat_rel}` | `{qual_rel}` | {summary['rows']:,} | **{'PASSED' if ok else 'FAILED'}** |")
    md.append("")
    md.append("Raw CSVs, `data/processed/`, and all other watched files were also hash-verified unchanged.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 4. Two-hour causal window")
    md.append("")
    md.append("- Primary baseline horizon: **2 hours** of previous observations (< t), same segment only.")
    md.append(f"- Jena (10-min cadence): **{jena_summary['window_rows_2h']}** previous rows.")
    md.append(f"- Delhi (5-min cadence): **{delhi_summary['window_rows_2h']}** previous rows.")
    md.append("- Window sizes reuse `CADENCE_HORIZONS['2h']` from Phase 3 (no duplicated constants).")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 5. Z-score method")
    md.append("")
    md.append("- Reuses Phase 3 `*_prev_mean_2h` / `*_prev_std_2h` directly (already causal, segment-contained).")
    md.append("- `z = (x - prev_mean_2h) / prev_std_2h`; std ≤ 1e-9 or missing → z = NaN (never forced).")
    md.append(f"- Flag threshold: **|z| > {Z_THRESHOLD}** (conventional configuration, not tuned, not optimal-claimed).")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 6. IQR method")
    md.append("")
    md.append("- Causal rolling Q1/Q3 over the same 2h window (new minimal calculation; Phase 3 has no quartiles).")
    md.append(f"- Tukey bounds with factor **{IQR_FACTOR}**; 1 = outside, 0 = inside, NaN = insufficient history.")
    md.append("- Zero-width IQR still compares honestly (equal → 0, different → 1); NaN only for missing history.")
    md.append("- Both views are preserved side-by-side for future Z-vs-IQR-vs-ML comparisons.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 7. Gap/segment and missing-data handling")
    md.append("")
    md.append("- Windows never cross `segment_id` boundaries; new segments return NaN until history refills.")
    md.append("- Missing current values → NaN scores/flags; missing history → NaN; nothing imputed or zero-filled.")
    md.append("- Observations are never deleted or modified (55 °C stays 55 °C even when flagged).")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 8. Data-quality integration")
    md.append("")
    md.append("- Rows with `ml_eligible = false` → `baseline_status = DATA_QUALITY_EXCLUDED`, all scores/flags NaN.")
    md.append("- Communication gaps therefore never become statistical anomalies in this layer.")
    md.append("- `POSSIBLE_FREEZE` is ML-eligible and processed normally when history allows.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 9. Baseline flag counts")
    md.append("")
    md.append("| Metric | Jena | Delhi |")
    md.append("| :--- | ---: | ---: |")
    for metric in (
        "rows", "usable_rows", "insufficient_history_rows", "excluded_by_data_quality_rows",
        "missing_input_rows", "temperature_zscore_flags", "pressure_zscore_flags",
        "humidity_zscore_flags", "temperature_iqr_flags", "pressure_iqr_flags",
        "humidity_iqr_flags", "zscore_any_flag_rows", "iqr_any_flag_rows",
        "same_variable_both_views_rows", "combined_baseline_flags",
    ):
        md.append(f"| `{metric}` | {jena_summary[metric]:,} | {delhi_summary[metric]:,} |")
    md.append(f"| `combined_flag_rate_usable` | {jena_summary['combined_flag_rate_usable']} | {delhi_summary['combined_flag_rate_usable']} |")
    md.append(f"| `combined_flag_rate_all` | {jena_summary['combined_flag_rate_all']} | {delhi_summary['combined_flag_rate_all']} |")
    md.append("")
    md.append("High flag counts are reported descriptively; they are NOT precision/recall claims.")
    md.append("No 950–1030 hPa rule exists anywhere in this layer: pressure flags come only from")
    md.append("causal statistical context (proven by source-scan test).")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 10. Limitations and no-ground-truth statement")
    md.append("")
    md.append("- No production anomaly labels exist, so accuracy/precision/recall/F1 are NOT reported.")
    md.append("- Thresholds are conventional, not calibrated for AWS faults; calibration is a later phase.")
    md.append("- Point-wise rolling rules have no multivariate/spatial context by design (that is the")
    md.append("  future ML gap this baseline exists to demonstrate).")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 11. Output schema and validation")
    md.append("")
    md.append(f"- Columns ({len(BASELINE_COLUMNS)}): `{'`, `'.join(BASELINE_COLUMNS)}`.")
    md.append("- Schema documented in `reports/baseline/baseline_schema.json`.")
    md.append("- Structural validation (schema, row counts, observation passthrough, exclusion consistency,")
    md.append("  flag/count consistency, segment-start safety) passed for both datasets.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 12. Reproduction")
    md.append("")
    md.append(f"- Command: `python -m src.baseline.run` (executed in ~{exec_seconds:.1f} s).")
    md.append("- Deterministic: identical inputs produce identical outputs (tested).")
    md.append("- No ML, synthetic anomalies, NOAA/spatial, ensemble, root-cause, SHAP, API, or frontend implemented.")
    md.append("")
    return "\n".join(md)


def run_baseline_pipeline(
    project_root: str | Path = ".",
    features_dir: str | Path = "data/features",
    quality_dir: str | Path = "data/quality",
    baseline_dir: str | Path = "data/baseline",
    reports_dir: str | Path = "reports/baseline",
) -> dict:
    start = time.time()
    root = Path(project_root).resolve()

    def _resolve(p: str | Path) -> Path:
        pp = Path(p)
        return (root / pp).resolve() if not pp.is_absolute() else pp

    feat_p, qual_p, base_p, rep_p = (_resolve(features_dir), _resolve(quality_dir),
                                    _resolve(baseline_dir), _resolve(reports_dir))
    base_p.mkdir(parents=True, exist_ok=True)
    rep_p.mkdir(parents=True, exist_ok=True)

    pre_hashes = snapshot_hashes(root)

    logger.info("Loading Phase 3 features + Phase 2.5 quality (read-only)...")
    df_jena_feat = pd.read_csv(feat_p / "jena_features.csv")
    df_delhi_feat = pd.read_csv(feat_p / "delhi_features.csv")
    df_jena_qual = pd.read_csv(qual_p / "jena_quality.csv")
    df_delhi_qual = pd.read_csv(qual_p / "delhi_quality.csv")

    logger.info("Building Jena baseline (%d rows)...", len(df_jena_feat))
    b_jena, s_jena = build_statistical_baseline(df_jena_feat, df_jena_qual, "jena")
    logger.info("Building Delhi baseline (%d rows)...", len(df_delhi_feat))
    b_delhi, s_delhi = build_statistical_baseline(df_delhi_feat, df_delhi_qual, "delhi")

    logger.info("Validating baseline frames...")
    v_jena = validate_baseline_frame(b_jena, df_jena_feat, df_jena_qual)
    v_delhi = validate_baseline_frame(b_delhi, df_delhi_feat, df_delhi_qual)
    if not v_jena["all_passed"]:
        raise RuntimeError(f"Jena baseline validation failed: {v_jena['checks']}")
    if not v_delhi["all_passed"]:
        raise RuntimeError(f"Delhi baseline validation failed: {v_delhi['checks']}")

    jena_out = base_p / "jena_statistical_baseline.csv"
    delhi_out = base_p / "delhi_statistical_baseline.csv"
    logger.info("Writing %s ...", jena_out)
    b_jena.to_csv(jena_out, index=False)
    logger.info("Writing %s ...", delhi_out)
    b_delhi.to_csv(delhi_out, index=False)

    post_hashes = snapshot_hashes(root)
    if pre_hashes != post_hashes:
        bad = [k for k in pre_hashes if pre_hashes[k] != post_hashes[k]]
        raise RuntimeError(f"CRITICAL: watched inputs changed during baseline run: {bad}")
    logger.info("Input immutability verified.")

    schema = [
        {"column": c, "category": cat, "description": desc, "causal": True}
        for c in BASELINE_COLUMNS
        for cat, desc in [describe_column(c)]
    ]
    with open(rep_p / "baseline_schema.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)

    exec_seconds = time.time() - start
    with open(rep_p / "statistical_baseline_summary.md", "w", encoding="utf-8") as f:
        f.write(generate_summary_markdown(s_jena, s_delhi, pre_hashes, post_hashes, exec_seconds))
    logger.info("Phase 4 baseline pipeline complete in %.1fs.", exec_seconds)
    return {"status": "SUCCESS", "jena_rows": len(b_jena), "delhi_rows": len(b_delhi),
            "jena_summary": s_jena, "delhi_summary": s_delhi,
            "execution_time_seconds": exec_seconds}


if __name__ == "__main__":
    run_baseline_pipeline()
