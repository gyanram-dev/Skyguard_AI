"""Master CLI runner for Phase 2 data preprocessing and standardization.

Usage:
    python -m src.preprocessing.run
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.preprocessing.preprocess_delhi import preprocess_delhi
from src.preprocessing.preprocess_jena import preprocess_jena
from src.preprocessing.validation import (
    validate_delhi_preprocessing,
    validate_global_invariants,
    validate_jena_preprocessing,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_preprocessing.run")


def compute_sha256(file_path: Path | str) -> str:
    """Calculate SHA-256 hash in 64KB chunks."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path.resolve()}")
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_raw_file(filename: str, candidate_dirs: List[Path]) -> Path:
    """Locate raw file across search paths."""
    for d in candidate_dirs:
        p = d / filename
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"Raw file '{filename}' could not be located in any of {[str(d.resolve()) for d in candidate_dirs]}"
    )


def generate_preprocessing_summary_markdown(
    jena_report: Dict[str, Any],
    delhi_report: Dict[str, Any],
    jena_val: Dict[str, Any],
    delhi_val: Dict[str, Any],
    pre_hashes: Dict[str, str],
    post_hashes: Dict[str, str],
    raw_paths: Dict[str, Path],
    out_paths: Dict[str, Path],
) -> str:
    """Generate comprehensive Phase 2 preprocessing_summary.md markdown report."""
    md = []
    md.append("# AWS Data Preprocessing & Standardization Report: Phase 2")
    md.append("\n**Project**: SIH PS 26073 — AI/ML-Based Anomaly Detection for Automatic Weather Stations")
    md.append("**Phase Status**: Phase 2 Complete (Standardization & Preprocessing Only).")
    md.append("**Safety Check**: No ML models, no synthetic anomalies, no normalization/scaling, no raw file modifications.")
    md.append("\n---\n")

    # A & B: Input files and pre-processing hashes
    md.append("## 1. Input Files & Raw Data Immutability")
    md.append("\n| Dataset | Input File Path | Size (Bytes) | SHA-256 Pre-Processing | SHA-256 Post-Processing | Immutability Status |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for name in ["Jena Climate", "Delhi-NCR AWS"]:
        p = raw_paths[name]
        pre_h = pre_hashes[name]
        post_h = post_hashes[name]
        status = "PASSED (Identical)" if pre_h == post_h else "FAILED (Modified)"
        size = p.stat().st_size
        md.append(f"| {name} | `{p.resolve()}` | {size:,} | `{pre_h}` | `{post_h}` | **{status}** |")

    # Standardized Schema
    md.append("\n---\n")
    md.append("## 2. Standardized Core Output Schema")
    md.append("Both datasets were standardized into the project-wide core schema without mixing or resampling:")
    md.append("\n| Standard Column | Semantic Role | Physical Unit | Present in Jena | Present in Delhi | Notes |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    md.append("| `timestamp` | Datetime identifier | ISO-8601 (`YYYY-MM-DD HH:MM:SS`) | Yes | Yes | Parsed strictly without silent coercion |")
    md.append("| `temperature_c` | Surface Air Temperature | °C (Celsius) | Yes | Yes | Original physical values preserved without clipping |")
    md.append("| `pressure_hpa` | Atmospheric Barometric Pressure | hPa / mbar | Yes | Yes | 1 mbar = 1 hPa; numeric values untouched |")
    md.append("| `relative_humidity_pct` | Relative Humidity | % [0-100] | Yes | Yes | Original physical values preserved |")
    md.append("| `source_dataset` | Station/Dataset origin | string metadata | Yes (`jena`) | Yes (`delhi`) | Retains dataset provenance |")

    # C: Jena Processing Details
    md.append("\n---\n")
    md.append("## 3. Jena Climate Preprocessing Summary")
    md.append(f"- **Raw Row Count**: **{jena_report['raw_rows']:,}**")
    md.append(f"- **Processed Row Count**: **{jena_report['processed_rows']:,}**")
    md.append(f"- **Duplicate Records Handled**: Detected **{jena_report['duplicates_detected']}** redundant exact duplicate copies (from historical re-appended blocks); removed exactly **{jena_report['duplicates_removed']}** rows, retaining exactly one valid copy of each timestamp.")
    md.append("- **Chronological Sorting**: Sorted ascending by `timestamp`. Output timeline is strictly unique and monotonic increasing.")
    md.append("- **Genuine Timestamp Gaps**: Preserved exactly as absent observations without interpolation, forward-filling, or synthetic creation. All 5 known gaps (>10 min) remain intact (maximum gap: 3 days 2 hours 20 minutes).")
    md.append(f"- **Missing Value Preservation**: Remains **0 missing cells** across all core variables.")
    md.append("- **Extreme Observations Preserved**:")
    md.append(f"  - Temperature range: `[{jena_report['temperature_c_stats']['min']:.2f}°C, {jena_report['temperature_c_stats']['max']:.2f}°C]` (mean: {jena_report['temperature_c_stats']['mean']:.2f}°C)")
    md.append(f"  - Pressure range: `[{jena_report['pressure_hpa_stats']['min']:.2f} hPa, {jena_report['pressure_hpa_stats']['max']:.2f} hPa]` (mean: {jena_report['pressure_hpa_stats']['mean']:.2f} hPa)")
    md.append(f"  - Humidity range: `[{jena_report['relative_humidity_pct_stats']['min']:.2f}%, {jena_report['relative_humidity_pct_stats']['max']:.2f}%]` (mean: {jena_report['relative_humidity_pct_stats']['mean']:.2f}%)")
    md.append(f"- **Validation Suite Result**: **{sum(jena_val['checks'].values())}/11 tests passed (100% PASSED)**.")

    # D: Delhi Processing Details
    md.append("\n---\n")
    md.append("## 4. Delhi-NCR AWS Preprocessing Summary")
    md.append(f"- **Raw Row Count**: **{delhi_report['raw_rows']:,}**")
    md.append(f"- **Processed Row Count**: **{delhi_report['processed_rows']:,}** (0 rows dropped).")
    md.append("- **Sampling Cadence**: Strictly uniform 5-minute intervals across all 289,728 rows.")
    md.append("- **Missing Value & Quality Metadata Flags Added**:")
    md.append(f"  - `temperature_missing`: **{delhi_report['missing_counts']['temperature_missing']}** missing observations flagged")
    md.append(f"  - `humidity_missing`: **{delhi_report['missing_counts']['humidity_missing']}** missing observations flagged")
    md.append(f"  - `pressure_missing`: **{delhi_report['missing_counts']['pressure_missing']}** missing observations flagged")
    md.append(f"  - `any_core_missing`: **{delhi_report['missing_counts']['any_core_missing']}** timestamps with $\\ge 1$ missing core variable")
    md.append(f"  - `missing_core_count`: Exactly **{delhi_report['missing_counts']['all_three_missing']}** timestamps with all 3 missing, **{delhi_report['missing_counts']['exactly_one_missing']}** with exactly 1 missing, and **{delhi_report['missing_counts']['zero_missing']:,}** fully complete timestamps.")
    md.append("- **Complete Outage Preservation**: The known 42-hour continuous outage (504 consecutive intervals from `2022-04-05 17:45:00` to `2022-04-07 11:40:00`) remains completely preserved as NaNs with quality flags.")
    md.append(f"- **Candidate Suspicious Temperatures Preserved**: All **{delhi_report['temperature_c_stats']['negative_temperatures_preserved_count']} candidate negative temperature observations** (down to -37.89°C on April 5, 2022) were preserved unchanged for subsequent anomaly detection phases.")
    md.append(f"- **Pressure Regimes Preserved**: All **{delhi_report['pressure_hpa_stats']['low_pressure_below_950_count']:,} observations < 950 hPa** and **{delhi_report['pressure_hpa_stats']['high_pressure_above_1030_count']:,} observations > 1030 hPa** were preserved completely unaltered without artificial clipping or thresholding.")
    md.append(f"- **Validation Suite Result**: **{sum(delhi_val['checks'].values())}/14 tests passed (100% PASSED)**.")

    # E: Output files
    md.append("\n---\n")
    md.append("## 5. Output Processed Files & Schemas")
    md.append("\n| Dataset | Output CSV Path | Row Count | Column Count | File Size (Bytes) |")
    md.append("| :--- | :--- | :--- | :--- | :--- |")
    for name, p in out_paths.items():
        size = p.stat().st_size
        rows = jena_report["processed_rows"] if "jena" in p.name else delhi_report["processed_rows"]
        cols = 5 if "jena" in p.name else 10
        md.append(f"| {name} | `{p.resolve()}` | {rows:,} | {cols} | {size:,} |")

    # Transformation Log
    md.append("\n---\n")
    md.append("## 6. Raw → Processed Transformation Traceability Matrix")
    md.append("\n| Dataset | Transformation Step | Rationale | Expected Row Impact | Numerical Modification |")
    md.append("| :--- | :--- | :--- | :--- | :--- |")
    md.append("| Jena | Timestamp Parsing (`%d.%m.%Y %H:%M:%S`) | Standardize to ISO-8601 representation | None | None |")
    md.append("| Jena | Core Column Standardization | Match unified project schema | None | None |")
    md.append("| Jena | Deduplicate Exact Copies (327 rows) | Remove historical block re-appending error | 420,551 → 420,224 (-327) | None |")
    md.append("| Jena | Chronological Ascending Sort | Establish strictly monotonic timeline | None | None |")
    md.append("| Jena | Preserve Genuine Gaps | Retain physical logger downtime information | None | None (no interpolation) |")
    md.append("| Delhi | Timestamp Parsing (`%d-%m-%Y %H:%M`) | Standardize to ISO-8601 representation | None | None |")
    md.append("| Delhi | Core Column Standardization | Match unified project schema | None | None |")
    md.append("| Delhi | Preserve Full Timeline | Retain continuous 5-minute sampling structure | None (289,728 → 289,728) | None |")
    md.append("| Delhi | Add Missing Quality Flags | Explicit metadata for communication/sensor outages | None | None (no NaN imputation) |")
    md.append("| Delhi | Preserve Candidate Anomalies | Preserve sub-zero temps and pressure regimes for ML | None | None (no clipping/filtering) |")

    # Warnings / Unexpected Observations
    md.append("\n---\n")
    md.append("## 7. Observations, Warnings & Candidate Anomalies Status")
    md.append("1. **Candidate Anomaly Classification**: In strict compliance with scientific guidelines, the 4 negative temperature readings in Delhi (around -37.9°C) and the 171,597 observations outside the 950–1030 hPa range are classified strictly as **candidate anomalies** and baseline drift regimes, **not** confirmed faults. They were neither dropped nor altered.")
    md.append("2. **Zero Numerical Normalization**: Neither dataset was subjected to standard scaling, min-max scaling, winsorization, or clipping. The data retains its physical meteorological meaning.")
    md.append("3. **Station Separation Maintained**: Datasets remain separate in `data/processed/jena_clean.csv` and `data/processed/delhi_clean.csv` to account for their distinct temporal cadences (10-min vs 5-min) and regional climatology.")

    return "\n".join(md)


def run_preprocessing(
    project_root: Path | str = ".",
    processed_dir: Path | str = "data/processed",
    reports_dir: Path | str = "reports/preprocessing",
) -> Dict[str, Any]:
    """Execute the complete Phase 2 preprocessing and standardization pipeline."""
    root = Path(project_root).resolve()
    p_dir = Path(processed_dir).resolve()
    r_dir = Path(reports_dir).resolve()

    p_dir.mkdir(parents=True, exist_ok=True)
    r_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting Phase 2 Data Preprocessing & Standardization...")
    candidate_dirs = [root, root / "data" / "raw"]

    jena_raw_file = find_raw_file("jena_climate_2009_2016.csv", candidate_dirs)
    delhi_raw_file = find_raw_file("AWS_20220401_20241231.csv", candidate_dirs)

    raw_paths = {
        "Jena Climate": jena_raw_file,
        "Delhi-NCR AWS": delhi_raw_file,
    }

    # Record Pre-Processing SHA-256 Hashes
    pre_hashes = {
        "Jena Climate": compute_sha256(jena_raw_file),
        "Delhi-NCR AWS": compute_sha256(delhi_raw_file),
    }
    logger.info(f"Pre-processing Jena SHA-256: {pre_hashes['Jena Climate']}")
    logger.info(f"Pre-processing Delhi SHA-256: {pre_hashes['Delhi-NCR AWS']}")

    # Load Raw DataFrames
    df_raw_jena = pd.read_csv(jena_raw_file)
    df_raw_delhi = pd.read_csv(delhi_raw_file)

    # Process Jena
    logger.info("Executing Jena standardization pipeline...")
    df_clean_jena, jena_report = preprocess_jena(df_raw_jena)
    jena_out_path = p_dir / "jena_clean.csv"
    df_clean_jena.to_csv(jena_out_path, index=False)
    logger.info(f"Saved processed Jena dataset to: {jena_out_path}")

    # Process Delhi
    logger.info("Executing Delhi standardization pipeline...")
    df_clean_delhi, delhi_report = preprocess_delhi(df_raw_delhi)
    delhi_out_path = p_dir / "delhi_clean.csv"
    df_clean_delhi.to_csv(delhi_out_path, index=False)
    logger.info(f"Saved processed Delhi dataset to: {delhi_out_path}")

    out_paths = {
        "Jena Climate (Processed)": jena_out_path,
        "Delhi-NCR AWS (Processed)": delhi_out_path,
    }

    # Run Automated Validations
    logger.info("Executing automated validation checks...")
    jena_val = validate_jena_preprocessing(df_raw_jena, df_clean_jena)
    delhi_val = validate_delhi_preprocessing(df_raw_delhi, df_clean_delhi)

    if not jena_val["all_passed"]:
        raise RuntimeError(f"Jena preprocessing validation failed: {jena_val['checks']}")
    if not delhi_val["all_passed"]:
        raise RuntimeError(f"Delhi preprocessing validation failed: {delhi_val['checks']}")

    # Verify Post-Processing Hashes
    post_hashes = {
        "Jena Climate": compute_sha256(jena_raw_file),
        "Delhi-NCR AWS": compute_sha256(delhi_raw_file),
    }
    global_val = validate_global_invariants(pre_hashes, post_hashes)
    if not global_val["all_passed"]:
        raise RuntimeError("CRITICAL: Raw file hashes changed during preprocessing!")

    logger.info("Raw file immutability verified: 100% identical pre- and post-processing hashes.")

    # Save JSON Reports
    with open(r_dir / "jena_preprocessing_report.json", "w", encoding="utf-8") as f:
        json.dump({"report": jena_report, "validation": jena_val}, f, indent=2)

    with open(r_dir / "delhi_preprocessing_report.json", "w", encoding="utf-8") as f:
        json.dump({"report": delhi_report, "validation": delhi_val}, f, indent=2)

    # Save Markdown Summary
    summary_md = generate_preprocessing_summary_markdown(
        jena_report=jena_report,
        delhi_report=delhi_report,
        jena_val=jena_val,
        delhi_val=delhi_val,
        pre_hashes=pre_hashes,
        post_hashes=post_hashes,
        raw_paths=raw_paths,
        out_paths=out_paths,
    )
    with open(r_dir / "preprocessing_summary.md", "w", encoding="utf-8") as f:
        f.write(summary_md)

    logger.info("All preprocessing reports successfully generated in reports/preprocessing/")
    return {
        "status": "SUCCESS",
        "jena_rows": len(df_clean_jena),
        "delhi_rows": len(df_clean_delhi),
        "pre_hashes": pre_hashes,
        "post_hashes": post_hashes,
        "reports_dir": str(r_dir),
    }


if __name__ == "__main__":
    run_preprocessing()
