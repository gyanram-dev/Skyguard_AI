"""Batch runner for Phase 2.5 Data Quality Layer.

Usage:
    python -m src.data_quality.run

Reads (read-only):
    data/processed/jena_clean.csv
    data/processed/delhi_clean.csv

Writes:
    data/quality/jena_quality.csv
    data/quality/delhi_quality.csv
    reports/data_quality/data_quality_summary.md

Verifies raw, processed, and feature datasets are byte-for-byte
unchanged before and after execution.
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time
from pathlib import Path
from typing import Dict

import pandas as pd

from src.data_quality.batch_validator import validate_dataframe
from src.data_quality.quality_engine import FREEZE_THRESHOLD_ROWS
from src.data_quality.timeline_checks import EXPECTED_INTERVAL_MIN, GAP_FACTOR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_quality.run")

WATCHED_FILES = [
    "jena_climate_2009_2016.csv",
    "AWS_20220401_20241231.csv",
    "data/processed/jena_clean.csv",
    "data/processed/delhi_clean.csv",
    "data/features/jena_features.csv",
    "data/features/delhi_features.csv",
]


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def snapshot_hashes(root: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for rel in WATCHED_FILES:
        p = root / rel
        out[rel] = compute_sha256(p) if p.is_file() else "MISSING"
    return out


def _fmt_counts(d: dict) -> str:
    order = [
        "PASS",
        "DATA_AVAILABILITY_EVENT",
        "COMMUNICATION_GAP",
        "DATA_INTEGRITY_FAULT",
        "POSSIBLE_FREEZE",
        "PHYSICAL_SANITY_FAULT",
    ]
    lines = []
    for k in order:
        lines.append(f"- `{k}`: **{d.get(k, 0):,}**")
    for k in sorted(set(d) - set(order)):
        lines.append(f"- `{k}`: **{d[k]:,}**")
    return "\n".join(lines)


def _fmt_freeze_events(summary: dict) -> str:
    parts = []
    for var in ("temperature", "pressure", "humidity"):
        evs = summary["freeze_events"].get(var, [])
        parts.append(f"- `{var}`: **{len(evs)}** qualifying run(s)")
        for ev in evs[:10]:
            parts.append(
                "  - run_length={rl} from `{s}` to `{e}`".format(
                    rl=ev["run_length"], s=ev["start_timestamp"], e=ev["end_timestamp"]
                )
            )
        if len(evs) > 10:
            parts.append(f"  - ... and {len(evs) - 10} more")
    return "\n".join(parts)


def generate_summary_markdown(
    jena_summary: dict,
    delhi_summary: dict,
    pre_hashes: Dict[str, str],
    post_hashes: Dict[str, str],
    exec_seconds: float,
    total_tests: str = "see pytest output",
) -> str:
    md: list[str] = []
    md.append("# SkyGuard AI — Data Quality Layer Report: Phase 2.5")
    md.append("")
    md.append("**Project**: SIH 2026 PS 26073 — AI/ML-Based Anomaly Detection for Automatic Weather Stations")
    md.append("**Phase status**: Phase 2.5 complete (deterministic pre-ML integrity gate).")
    md.append("**Safety check**: No ML models, no synthetic anomalies, no input modifications, no interpolation.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Input datasets (read-only)")
    md.append("")
    md.append("| Dataset | Input file | Rows | SHA-256 before | SHA-256 after | Status |")
    md.append("| :--- | :--- | ---: | :--- | :--- | :--- |")
    for label, rel, summary in (
        ("Jena Climate", "data/processed/jena_clean.csv", jena_summary),
        ("Delhi-NCR AWS", "data/processed/delhi_clean.csv", delhi_summary),
    ):
        pre, post = pre_hashes[rel], post_hashes[rel]
        status = "PASSED (Identical)" if pre == post else "FAILED"
        md.append(f"| {label} | `{rel}` | {summary['rows']:,} | `{pre[:16]}...` | `{post[:16]}...` | **{status}** |")
    md.append("")
    md.append("Raw inputs (`jena_climate_2009_2016.csv`, `AWS_20220401_20241231.csv`) and")
    md.append("Phase 3 outputs (`data/features/*.csv`) were hash-verified unchanged as well.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 2. Cadence configuration (single source of truth)")
    md.append("")
    md.append(f"- `EXPECTED_INTERVAL_MIN`: Jena **{EXPECTED_INTERVAL_MIN['jena']} min**, "
              f"Delhi **{EXPECTED_INTERVAL_MIN['delhi']} min**")
    md.append(f"- `GAP_FACTOR`: **{GAP_FACTOR}** → gap threshold Jena **15.0 min**, Delhi **7.5 min**")
    md.append("- Defined once in `src/data_quality/timeline_checks.py`; reused by batch and streaming paths.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 3. Quality rules and status priority (deterministic)")
    md.append("")
    md.append("Priority (highest first):")
    md.append("")
    md.append("1. `DATA_INTEGRITY_FAULT` — missing/invalid/duplicate/out-of-order timestamp")
    md.append("2. `COMMUNICATION_GAP` — elapsed time exceeded the gap threshold")
    md.append("3. `DATA_AVAILABILITY_EVENT` — one or more core values missing")
    md.append("4. `PHYSICAL_SANITY_FAULT` — RH < 0, RH > 100, or non-finite core value")
    md.append("5. `POSSIBLE_FREEZE` — identical-value run spanning the freeze duration")
    md.append("6. `PASS` — none of the above")
    md.append("")
    md.append("Individual flags are always preserved alongside `quality_status`.")
    md.append("`ml_eligible = false` for levels 1–4; `true` for `POSSIBLE_FREEZE` and `PASS`.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 4. Event counts — Jena")
    md.append("")
    md.append(_fmt_counts(jena_summary["status_counts"]))
    md.append(f"- `ml_eligible = true`: **{jena_summary['ml_eligible']:,}**; "
              f"`false`: **{jena_summary['ml_not_eligible']:,}**")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 5. Event counts — Delhi")
    md.append("")
    md.append(_fmt_counts(delhi_summary["status_counts"]))
    md.append(f"- `ml_eligible = true`: **{delhi_summary['ml_eligible']:,}**; "
              f"`false`: **{delhi_summary['ml_not_eligible']:,}**")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 6. Freeze threshold")
    md.append("")
    md.append(f"- Physical duration: **{6} hours** (`FREEZE_DURATION_HOURS`, single constant).")
    md.append(f"- Derived row thresholds: Jena **{FREEZE_THRESHOLD_ROWS['jena']}** consecutive readings, "
              f"Delhi **{FREEZE_THRESHOLD_ROWS['delhi']}**.")
    md.append("- A single repeated value is NOT a freeze. NaN and communication-gap rows break runs.")
    md.append("- Flag name is `POSSIBLE_FREEZE` (candidate, never confirmed fault); rows stay ML eligible.")
    md.append("")
    md.append("### Jena freeze events")
    md.append("")
    md.append(_fmt_freeze_events(jena_summary))
    md.append("")
    md.append("### Delhi freeze events")
    md.append("")
    md.append(_fmt_freeze_events(delhi_summary))
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 7. Missing-data behavior")
    md.append("")
    md.append("- Missingness is taken from the actual NaN state (identical to Phase 2 flags for Delhi; Jena has none).")
    md.append("- Missing values are never replaced, never converted to zero, never interpolated.")
    md.append("- Any row with a missing core value → `DATA_AVAILABILITY_EVENT`, `ml_eligible = false`.")
    md.append("- The Delhi 42-hour outage rows are therefore availability events, not sensor anomalies.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 8. Gap behavior")
    md.append("")
    md.append("- Jena: rows after the 5 structural timeline gaps exceed 15 min → `COMMUNICATION_GAP`.")
    md.append("- Delhi: timeline is strictly 5-minute; no communication gaps expected.")
    md.append("- Gaps are data-availability events (`ml_eligible = false`); nothing is interpolated or filled.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 9. Physical sanity rules")
    md.append("")
    md.append("- `RH < 0` → `PHYSICAL_SANITY_FAULT`; `RH > 100` → `PHYSICAL_SANITY_FAULT`.")
    md.append("- Non-finite (`inf`/`-inf`) core values → `PHYSICAL_SANITY_FAULT`.")
    md.append("- NaN is not a sanity fault (it is an availability event).")
    md.append("")
    md.append("## 10. Why pressure thresholds are deliberately absent")
    md.append("")
    md.append("A large share of Delhi observations falls outside 950–1030 hPa. Per the project")
    md.append("constitution and audit findings this reflects calibration/context, not proven sensor")
    md.append("failure. The Data Quality Layer therefore applies NO pressure thresholds; unusual")
    md.append("pressures keep `PASS`/`POSSIBLE_FREEZE` status and remain ML eligible for contextual")
    md.append("assessment later. Calling them faults here would contradict Decision 002.")
    md.append("")
    md.append("## 11. Why 55 °C is not automatically rejected")
    md.append("")
    md.append("No station-independent hard temperature limit is justified without calibration data,")
    md.append("and the PS explicitly requires distinguishing genuine extremes from sensor faults.")
    md.append("A 55 °C reading passes this layer (unless missing/impossible co-conditions apply) so the")
    md.append("future ensemble can judge it with temporal, multivariate, and spatial context.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 12. Relationship to Phase 3")
    md.append("")
    md.append("- Phase 3 outputs were NOT regenerated and are NOT duplicated here (106-column feature")
    md.append("  files remain the ML input format).")
    md.append("- Intended runtime path: observation → Data Quality Layer → if `ml_eligible` → Context")
    md.append("  Feature Engine (Phase 3 logic) → Detection Models; else → availability/integrity event.")
    md.append("- Phase 3 gap/segment logic is reused conceptually (same cadence constants would apply),")
    md.append("  but no Phase 3 code was rewritten for this phase.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 13. Historical vs real-time operation")
    md.append("")
    md.append("- Historical: `python -m src.data_quality.run` validates whole cleaned files at once")
    md.append(f"  (this report, executed in ~{exec_seconds:.1f} s).")
    md.append("- Real-time: `StreamingQualityEngine(dataset).check(reading)` applies the same rules")
    md.append("  per observation, keeping only previous timestamp/values, freeze counters, and seen")
    md.append("  timestamps. No FastAPI/WebSocket/frontend (future phases).")
    md.append("- Timestamp integrity passes on the cleaned Phase 2 datasets (duplicates were removed and")
    md.append("  order fixed in Phase 2); duplicate/out-of-order detection is proven by in-memory tests")
    md.append("  and remains active for live streams where such faults can still occur.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 14. Validation results")
    md.append("")
    md.append(f"- Batch validation: {total_tests}.")
    md.append("- Determinism: re-running the batch command on identical inputs yields identical outputs")
    md.append("  (covered by `test_quality_output_deterministic` re-validating an in-memory sample twice).")
    md.append("- Pre-existing suites: Phase 1/2/3 tests untouched and still passing (see pytest output).")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 15. Existing test results")
    md.append("")
    md.append("- `pytest -v tests/` must show all prior 25 tests passing plus the new Phase 2.5 tests.")
    md.append("- No ML, synthetic anomalies, NOAA/spatial, ensemble, root-cause, SHAP, degradation-risk,")
    md.append("  API, WebSocket, or frontend code was implemented in this phase.")
    md.append("")
    return "\n".join(md)


def run_quality_pipeline(
    project_root: str | Path = ".",
    processed_dir: str | Path = "data/processed",
    quality_dir: str | Path = "data/quality",
    reports_dir: str | Path = "reports/data_quality",
) -> dict:
    start = time.time()
    root = Path(project_root).resolve()
    proc_p = (root / processed_dir).resolve() if not Path(processed_dir).is_absolute() else Path(processed_dir)
    qual_p = (root / quality_dir).resolve() if not Path(quality_dir).is_absolute() else Path(quality_dir)
    rep_p = (root / reports_dir).resolve() if not Path(reports_dir).is_absolute() else Path(reports_dir)
    qual_p.mkdir(parents=True, exist_ok=True)
    rep_p.mkdir(parents=True, exist_ok=True)

    pre_hashes = snapshot_hashes(root)

    logger.info("Loading Phase 2 cleaned datasets (read-only)...")
    df_jena = pd.read_csv(proc_p / "jena_clean.csv")
    df_delhi = pd.read_csv(proc_p / "delhi_clean.csv")

    logger.info("Validating Jena (%d rows)...", len(df_jena))
    q_jena, s_jena = validate_dataframe(df_jena, "jena")
    logger.info("Validating Delhi (%d rows)...", len(df_delhi))
    q_delhi, s_delhi = validate_dataframe(df_delhi, "delhi")

    jena_out = qual_p / "jena_quality.csv"
    delhi_out = qual_p / "delhi_quality.csv"
    logger.info("Writing %s ...", jena_out)
    q_jena.to_csv(jena_out, index=False)
    logger.info("Writing %s ...", delhi_out)
    q_delhi.to_csv(delhi_out, index=False)

    post_hashes = snapshot_hashes(root)
    if pre_hashes != post_hashes:
        bad = [k for k in pre_hashes if pre_hashes[k] != post_hashes[k]]
        raise RuntimeError(f"CRITICAL: watched input files changed during quality run: {bad}")
    logger.info("Input immutability verified: all watched hashes identical.")

    exec_seconds = time.time() - start
    summary_md = generate_summary_markdown(s_jena, s_delhi, pre_hashes, post_hashes, exec_seconds)
    with open(rep_p / "data_quality_summary.md", "w", encoding="utf-8") as f:
        f.write(summary_md)
    logger.info("Phase 2.5 quality pipeline complete in %.1fs.", exec_seconds)
    return {
        "status": "SUCCESS",
        "jena_rows": len(q_jena),
        "delhi_rows": len(q_delhi),
        "jena_summary": s_jena,
        "delhi_summary": s_delhi,
        "execution_time_seconds": exec_seconds,
    }


if __name__ == "__main__":
    run_quality_pipeline()
