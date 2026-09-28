"""Phase 8B pipeline: neighbors, consistency, AWS validation, reports.

Usage:
    python -m src.spatial.run

Reads (read-only): data/noaa/metadata/station_manifest.json,
data/noaa/processed/*.csv, data/processed/delhi_clean.csv.
Writes: data/noaa/metadata/neighbor_graph.csv,
data/noaa/metadata/spatial_config.json,
data/noaa/processed/spatial_consistency.csv,
reports/noaa/{spatial_consistency_report.md,neighbor_coverage.csv,
spatial_context_metrics.csv,aws_context_validation.csv}.
No Phase 1-7 artifact is touched. No scoring beyond evidence signals.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.spatial import evaluator as E
from src.spatial import neighbors as N
from src.spatial.alignment import TIME_TOLERANCE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_spatial.run")

DELHI_NOAA_ID = "INI0000VIDD"
PRESSURE_BASIS = "altimeter_setting_hpa"


def run_spatial_pipeline(project_root: str | Path = ".") -> dict:
    """Build the spatial-consistency evidence layer."""
    root = Path(project_root).resolve()
    meta_dir = root / "data" / "noaa" / "metadata"
    proc_dir = root / "data" / "noaa" / "processed"
    rep_dir = root / "reports" / "noaa"

    manifest = json.loads((meta_dir / "station_manifest.json").read_text(encoding="utf-8"))
    stations = manifest["stations"]

    pairs = N.pairwise_distances(stations)
    selected = N.select_neighbors(pairs)
    graph = pairs.merge(selected[["target_station", "neighbor_station", "selected"]],
                        on=["target_station", "neighbor_station"], how="left")
    graph["selected"] = graph["selected"].fillna(False).astype(bool)
    graph.to_csv(meta_dir / "neighbor_graph.csv", index=False)
    logger.info("Neighbor graph: %d pairs, %d selected edges",
                len(graph), int(graph["selected"].sum()))

    frames = {}
    for station in stations:
        sid = station["ghcnh_id"]
        frame = pd.read_csv(proc_dir / f"{sid}_2022_2024.csv",
                            usecols=["timestamp_utc", "temperature_c",
                                     "relative_humidity_pct", "altimeter_setting_hpa"])
        frames[sid] = frame

    sel_by_target = {sid: selected[selected["target_station"] == sid]
                     .sort_values("rank")["neighbor_station"].tolist()
                     for sid in frames}
    consistency = pd.concat(
        [E.build_consistency_frame(sid, frames[sid], frames, sel_by_target[sid])
         for sid in frames], ignore_index=True)
    consistency.to_csv(proc_dir / "spatial_consistency.csv", index=False)
    logger.info("Consistency frame: %d rows", len(consistency))

    coverage_rows = []
    for sid in frames:
        tgt_n = len(frames[sid])
        for _, edge in selected[selected["target_station"] == sid].iterrows():
            nid = edge["neighbor_station"]
            aligned = int((consistency[consistency["station_id"] == sid]
                           .pipe(lambda f: _pair_aligned(f, frames, sid, nid))).sum())
            coverage_rows.append({
                "target_station": sid, "neighbor_station": nid,
                "distance_km": edge["distance_km"], "rank": int(edge["rank"]),
                "target_observations": tgt_n,
                "aligned_comparisons": aligned,
                "coverage_fraction": round(aligned / tgt_n, 4) if tgt_n else float("nan"),
            })
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(rep_dir / "neighbor_coverage.csv", index=False)

    metrics = _context_metrics(consistency)
    metrics.to_csv(rep_dir / "spatial_context_metrics.csv", index=False)

    context_ids = [DELHI_NOAA_ID] + sel_by_target[DELHI_NOAA_ID]
    aws = E.build_aws_validation(str(root / "data" / "processed" / "delhi_clean.csv"),
                                 frames, context_ids)
    aws.to_csv(rep_dir / "aws_context_validation.csv", index=False)
    logger.info("AWS validation: %d rows, context stations %s", len(aws), context_ids)

    config = {
        "k_maximum": N.MAX_NEIGHBORS,
        "radius_km": N.MAX_RADIUS_KM,
        "temporal_tolerance": "30 minutes back from target (latest real observation at/before target; future records never selected; no interpolation)",
        "timestamp_basis": "UTC (Delhi AWS IST converted IST-5:30)",
        "variables": {prefix: column for prefix, column in E.VARIABLES},
        "pressure_basis": PRESSURE_BASIS,
        "pressure_basis_note": "Altimeter (QNH, hPa) is the only pressure field with "
                               "universal coverage; station-level and sea-level pressures "
                               "are never mixed into it.",
        "reference_formula": "neighbor_median = median of available neighbor observations (>= 1)",
        "dispersion_formula": "MAD = median(|neighbor_i - median(neighbors)|), needs >= 2",
        "score_formula": "spatial_robust_score = |target - neighbor_median| / MAD; "
                         "NaN when < 2 neighbors or MAD == 0; higher = stronger inconsistency, "
                         "NOT a probability",
        "minimum_neighbor_rule": "reference needs >= 1; score needs >= 2 with MAD > 0",
        "confidence_rule": {
            "UNAVAILABLE": "no target value or 0 available neighbors",
            "LOW_CONTEXT": "1 available neighbor, or degenerate (MAD == 0) dispersion",
            "MEDIUM_CONTEXT": ">= 2 available neighbors but fewer than expected",
            "HIGH_CONTEXT": "all expected neighbors available with a valid score",
        },
        "delhi_context_stations": context_ids,
    }
    with open(meta_dir / "spatial_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    _write_report(rep_dir, consistency, coverage, metrics, aws, config, sel_by_target)
    return {"consistency_rows": len(consistency), "aws_rows": len(aws)}


def _pair_aligned(target_frame: pd.DataFrame, frames: dict, sid: str, nid: str) -> np.ndarray:
    """Whether neighbor nid had any variable available per target row."""
    from src.spatial.evaluator import _neighbor_value_matrix

    times = pd.to_datetime(target_frame["timestamp_utc"], utc=True)
    mats = [_neighbor_value_matrix(times, frames, [nid], col).ravel()
            for _, col in E.VARIABLES]
    return np.isfinite(np.stack(mats, axis=1)).any(axis=1)


def _context_metrics(consistency: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for prefix in ("temp", "rh", "pres"):
        diff = pd.to_numeric(consistency[f"{prefix}_abs_difference"], errors="coerce")
        score = pd.to_numeric(consistency[f"{prefix}_robust_score"], errors="coerce")
        ctx = consistency[f"{prefix}_context"].value_counts()
        rows.append({
            "variable": prefix,
            "n_observations": int(len(consistency)),
            "n_with_reference": int(diff.notna().sum()),
            "n_with_score": int(score.notna().sum()),
            "abs_diff_p50": round(float(diff.quantile(0.50)), 3),
            "abs_diff_p90": round(float(diff.quantile(0.90)), 3),
            "abs_diff_p99": round(float(diff.quantile(0.99)), 3),
            "abs_diff_max": round(float(diff.max()), 3),
            "score_p50": round(float(score.quantile(0.50)), 3),
            "score_p90": round(float(score.quantile(0.90)), 3),
            "score_p99": round(float(score.quantile(0.99)), 3),
            "score_max": round(float(score.max()), 3),
            "n_HIGH_CONTEXT": int(ctx.get("HIGH_CONTEXT", 0)),
            "n_MEDIUM_CONTEXT": int(ctx.get("MEDIUM_CONTEXT", 0)),
            "n_LOW_CONTEXT": int(ctx.get("LOW_CONTEXT", 0)),
            "n_UNAVAILABLE": int(ctx.get("UNAVAILABLE", 0)),
        })
    status = consistency["temporal_alignment_status"].value_counts()
    rows.append({"variable": "alignment", "n_observations": int(len(consistency)),
                 "n_FULL_ALIGNMENT": int(status.get("FULL_ALIGNMENT", 0)),
                 "n_PARTIAL_ALIGNMENT": int(status.get("PARTIAL_ALIGNMENT", 0)),
                 "n_NO_ALIGNMENT": int(status.get("NO_ALIGNMENT", 0))})
    return pd.DataFrame(rows)


def _write_report(rep_dir: Path, consistency: pd.DataFrame, coverage: pd.DataFrame,
                  metrics: pd.DataFrame, aws: pd.DataFrame, config: dict,
                  sel_by_target: dict) -> None:
    with open(rep_dir / "spatial_consistency_report.md", "w", encoding="utf-8") as f:
        f.write("# Spatial Consistency Evidence Layer (Phase 8B)\n\n")
        f.write("Evidence signals only: per-variable spatial inconsistency versus "
                "nearby stations. NOT a fault classifier; signals are never combined "
                "here and no probability is claimed.\n\n")
        f.write("## Neighbor rule\n\n")
        f.write(f"Up to {config['k_maximum']} nearest stations within "
                f"{config['radius_km']} km (haversine), target excluded, deterministic "
                "rank by (distance, station ID). Fixed constants, tuned against nothing.\n\n")
        for sid, nids in sel_by_target.items():
            edges = coverage[coverage["target_station"] == sid]
            desc = "; ".join(f"{r['neighbor_station']} ({r['distance_km']} km, "
                             f"coverage {r['coverage_fraction']:.1%})"
                             for _, r in edges.iterrows())
            f.write(f"- `{sid}`: {desc if desc else 'no neighbors within radius'}.\n")
        f.write(f"\nTemporal alignment: {config['temporal_tolerance']}; "
                f"{config['timestamp_basis']}.\n\n")
        f.write("## Variables and pressure decision\n\n")
        f.write("Temperature (`temperature_c`) and relative humidity "
                "(`relative_humidity_pct`) scored separately. Pressure uses ONLY "
                f"`{config['pressure_basis']}`: {config['pressure_basis_note']}\n\n")
        f.write("## Formulas\n\n")
        f.write(f"- Reference: {config['reference_formula']}.\n")
        f.write(f"- Dispersion: {config['dispersion_formula']}.\n")
        f.write(f"- Score: {config['score_formula']}.\n")
        f.write(f"- Minimum neighbors: {config['minimum_neighbor_rule']}.\n")
        f.write(f"- Confidence: {config['confidence_rule']}.\n\n")
        f.write("## Coverage\n\n")
        for _, row in metrics.iterrows():
            if row["variable"] == "alignment":
                f.write(f"- alignment: FULL {row['n_FULL_ALIGNMENT']:,}, PARTIAL "
                        f"{row['n_PARTIAL_ALIGNMENT']:,}, NONE {row['n_NO_ALIGNMENT']:,}.\n")
            else:
                f.write(f"- {row['variable']}: {row['n_with_score']:,}/{row['n_observations']:,} "
                        f"scored; HIGH {row['n_HIGH_CONTEXT']:,}, MEDIUM "
                        f"{row['n_MEDIUM_CONTEXT']:,}, LOW {row['n_LOW_CONTEXT']:,}, "
                        f"UNAVAILABLE {row['n_UNAVAILABLE']:,}; abs-diff p50/p90/p99 "
                        f"{row['abs_diff_p50']}/{row['abs_diff_p90']}/{row['abs_diff_p99']}; "
                        f"score p50/p90/p99 "
                        f"{row['score_p50']}/{row['score_p90']}/{row['score_p99']}.\n")
        n_ctx = int((aws["ctx_temp_station_count"] > 0).sum())
        f.write(f"\nDelhi AWS contextual coverage: {n_ctx:,}/{len(aws):,} AWS rows "
                f"({n_ctx / len(aws):.1%}) have >= 1 NOAA context station; context = "
                f"{', '.join(config['delhi_context_stations'])} (NOAA Delhi/Safdarjung "
                "plus its geographic neighbors; different sensors, not ground truth, "
                "no labels derived; AWS pressure never differenced against altimeter).\n\n")
        f.write("## Limitations\n\n")
        f.write("- Mumbai (`INI0000VABB`) has no station within 600 km (nearest, "
                "Bhopal, is ~655 km away), so all of its rows are UNAVAILABLE / "
                "NO_ALIGNMENT. The fixed radius was not adjusted to force a "
                "connection; the 8A station set was kept authoritative.\n")
        f.write("- Delhi/Safdarjung is 3-hourly: its own comparisons and AWS context "
                "are sparse in time.\n- Altimeter (QNH) is a standard-atmosphere reduction, "
                "not a station-pressure comparison.\n- High spatial difference is reported "
                "as inconsistency evidence, never as a sensor fault.\n- Distances are "
                "geographic only; terrain and microclimate are not modeled.\n")


if __name__ == "__main__":
    run_spatial_pipeline()
