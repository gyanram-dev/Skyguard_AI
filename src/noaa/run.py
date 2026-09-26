"""Phase 8A pipeline: acquire, standardize, audit, report.

Usage:
    python -m src.noaa.run

Reads (read-only, network): NCEI GHCNh inventory/PDF/parquet files.
Writes ONLY under data/noaa/ and reports/noaa/. No Phase 1-7 artifact
is touched. No modeling, no anomaly scoring.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.noaa import acquire as A
from src.noaa import audit as AU
from src.noaa import config as C
from src.noaa import process as P

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aws_noaa.run")


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def run_noaa_pipeline(project_root: str | Path = ".") -> dict:
    """Acquire and audit the NOAA multi-station dataset."""
    root = Path(project_root).resolve()
    raw_dir = root / "data" / "noaa" / "raw"
    proc_dir = root / "data" / "noaa" / "processed"
    meta_dir = root / "data" / "noaa" / "metadata"
    rep_dir = root / "reports" / "noaa"
    for d in (raw_dir, proc_dir, meta_dir, rep_dir):
        d.mkdir(parents=True, exist_ok=True)

    access_date = datetime.now(timezone.utc).date().isoformat()

    logger.info("Downloading GHCNh inventory + documentation...")
    inventory_recs = A.acquire_inventory(meta_dir)

    logger.info("Downloading %d station-years...", len(C.STATIONS) * len(C.YEARS))
    download_recs = A.acquire_station_years(raw_dir)

    logger.info("Standardizing stations...")
    frames: dict[str, pd.DataFrame] = {}
    processed_files = []
    for station in C.STATIONS:
        sid = station["ghcnh_id"]
        raws = [str(raw_dir / "by-year" / str(y) / f"GHCNh_{sid}_{y}.parquet")
                for y in C.YEARS]
        dest = proc_dir / f"{sid}_2022_2024.csv"
        frames[sid] = P.build_processed_station(sid, raws, str(dest))
        processed_files.append(dest)

    logger.info("Auditing stations + overlap...")
    audits = [AU.audit_station(frames[s["ghcnh_id"]], s) for s in C.STATIONS]
    overlap = AU.overlap_analysis(frames)

    manifest = {
        "phase": "8A (acquisition + audit only)",
        "source_dataset": C.DATASET_NAME,
        "source_version": C.DATASET_VERSION,
        "source_doi": C.DATASET_DOI,
        "source_pages": C.DATASET_PAGES,
        "access_method": C.ACCESS_METHOD,
        "access_date": access_date,
        "inventory": inventory_recs,
        "acquisition_years": list(C.YEARS),
        "stations": [
            {**{k: s[k] for k in ("ghcnh_id", "name", "region", "lat", "lon", "elev_m", "note")},
             "observation_period": [a["first_timestamp"], a["last_timestamp"]],
             "rows": a["rows"],
             "median_cadence_minutes": a["median_cadence_minutes"],
             "processed_file": _rel(proc_dir / f"{s['ghcnh_id']}_2022_2024.csv", root),
             "processed_sha256": A.sha256_file(proc_dir / f"{s['ghcnh_id']}_2022_2024.csv")}
            for s, a in zip(C.STATIONS, audits)
        ],
        "variables": [
            {**m, "skyguard_unit": m["unit"]} for m in C.VARIABLE_MAPPING
        ],
        "common_overlap": {k: v for k, v in overlap.items() if k != "per_station"},
        "raw_files": [
            {"station_id": r["station_id"], "year": r["year"],
             "path": _rel(Path(r["path"]), root),
             "bytes": r["bytes"], "sha256": r["sha256"]}
            for r in download_recs
        ],
        "software": {"pandas": pd.__version__,
                     "pyarrow": __import__("pyarrow").__version__},
    }
    with open(meta_dir / "station_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    _write_reports(root, rep_dir, audits, overlap, manifest, access_date)
    logger.info("Phase 8A complete.")
    return {"manifest": manifest, "audits": audits, "overlap": overlap}


def _available_vars(audit: dict) -> str:
    present = [c for c in AU.MAPPED_VALUE_COLUMNS
               if audit["rows"] - audit[f"{c}_missing"] > 0]
    return ";".join(present)


def _write_reports(root: Path, rep_dir: Path, audits: list[dict],
                   overlap: dict, manifest: dict, access_date: str) -> None:
    station_rows = []
    for station, audit in zip(C.STATIONS, audits):
        station_rows.append({
            "station_id": station["ghcnh_id"],
            "station_name": station["name"],
            "latitude": station["lat"],
            "longitude": station["lon"],
            "elevation_m": station["elev_m"],
            "region": station["region"],
            "observation_period": f"{audit['first_timestamp']} -> {audit['last_timestamp']}",
            "available_variables": _available_vars(audit),
            "observation_frequency": f"median {audit['median_cadence_minutes']} min",
            "usable_records": audit["rows"],
            "selection_note": station["note"],
        })
    pd.DataFrame(station_rows).to_csv(rep_dir / "station_selection.csv", index=False)
    pd.DataFrame(audits).to_csv(rep_dir / "station_quality_summary.csv", index=False)

    overlap_rows = [{
        "scope": "station", "station_id": sid,
        "first_timestamp": info["first"], "last_timestamp": info["last"],
        "rows": info["rows"], "metric": "", "value": "",
    } for sid, info in overlap["per_station"].items()]
    overlap_rows.append({
        "scope": "common", "station_id": "ALL",
        "first_timestamp": overlap["common_start"], "last_timestamp": overlap["common_end"],
        "rows": overlap["common_hours"], "metric": "common_hours", "value": overlap["common_hours"],
    })
    for key in ("hours_with_ge2_stations_temp", "hours_with_ge5_stations_temp",
                "hours_with_all_stations_temp", "fraction_ge2", "fraction_ge5",
                "fraction_all"):
        overlap_rows.append({"scope": "common", "station_id": "ALL",
                             "first_timestamp": overlap["common_start"],
                             "last_timestamp": overlap["common_end"],
                             "rows": overlap["common_hours"], "metric": key,
                             "value": overlap[key]})
    pd.DataFrame(overlap_rows).to_csv(rep_dir / "overlap_summary.csv", index=False)

    with open(rep_dir / "variable_mapping.md", "w", encoding="utf-8") as f:
        f.write("# NOAA → SkyGuard Variable Mapping (Phase 8A)\n\n")
        f.write(f"Source: {C.DATASET_NAME} {C.DATASET_VERSION}.\n")
        f.write("Timestamps are UTC (`timestamp_utc`). Missing values are empty "
                "(NaN); the provider -9999 sentinel is mapped to NaN, never imputed.\n\n")
        f.write("| SkyGuard field | GHCNh source field | Unit | Role | Note |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for m in C.VARIABLE_MAPPING:
            f.write(f"| {m['skyguard']} | {m['source_field']} | {m['unit']} | "
                    f"{m['role']} | {m['note']} |\n")
        f.write("\nPressure discipline: `station_level_pressure` is the true "
                "barometric pressure at station elevation; `sea_level_pressure` "
                "is a reduction estimate, never substituted for station "
                "pressure; `altimeter_setting_hpa` (QNH, hPa) is auxiliary. "
                "The Phase 8B common-pressure basis is undecided in this phase.\n")
        f.write("\nPer-station variable availability is recorded in "
                "`station_selection.csv` (`available_variables`).\n")

    with open(rep_dir / "acquisition_report.md", "w", encoding="utf-8") as f:
        f.write("# NOAA Multi-Station Acquisition + Audit (Phase 8A)\n\n")
        f.write(f"Dataset: **{C.DATASET_NAME} {C.DATASET_VERSION}** "
                f"(DOI {C.DATASET_DOI}).\n\n")
        f.write(f"Access: {C.ACCESS_METHOD}\n\nAccess date: {access_date}.\n\n")
        f.write("## Why GHCNh and not ISD\n\n")
        f.write("The blueprint names NOAA ISD, but NCEI has superseded ISD with "
                "GHCNh: the GHCNh v1.1.0 documentation states it replaces the "
                "legacy Global Hourly (ISD) product, and NCEI ended ISD online "
                "service with no updates beyond 2025-08-24. GHCNh additionally "
                "reports station-level pressure and relative humidity natively. "
                "This switch is explicit, not silent.\n\n")
        f.write("## Stations\n\n")
        for r in station_rows:
            f.write(f"- `{r['station_id']}` {r['station_name']} ({r['region']}) "
                    f"{r['latitude']}, {r['longitude']}, {r['observation_frequency']}, "
                    f"{r['usable_records']:,} rows.\n")
        f.write(f"\nCommon overlap: {overlap['common_start']} → {overlap['common_end']} "
                f"({overlap['common_hours']:,} hours).\n")
        f.write(f"Hourly temperature coverage: ≥2 stations {overlap['fraction_ge2']:.1%}, "
                f"≥5 stations {overlap['fraction_ge5']:.1%}, "
                f"all stations {overlap['fraction_all']:.1%} of common hours.\n\n")
        f.write("## Quality notes (audit, not faults)\n\n")
        for a in audits:
            issues = []
            if a["duplicate_timestamps"]:
                issues.append(f"{a['duplicate_timestamps']} duplicate timestamps (flagged, kept)")
            if a["out_of_order_rows"]:
                issues.append(f"{a['out_of_order_rows']} out-of-order rows")
            for col in ("temperature_c", "sea_level_pressure_hpa", "relative_humidity_pct"):
                if a[f"{col}_outside_physical_bounds"]:
                    issues.append(f"{col}: {a[f'{col}_outside_physical_bounds']} outside physical bounds")
            if a["dewpoint_above_temperature"]:
                issues.append(f"{a['dewpoint_above_temperature']} dewpoint>temperature rows")
            if a["temperature_jumps_gt_15C_per_step"]:
                issues.append(f"{a['temperature_jumps_gt_15C_per_step']} candidate "
                              "temperature discontinuities (>15C per step, for review)")
            line = "; ".join(issues) if issues else "no integrity issues"
            f.write(f"- `{a['station_id']}`: {line}.\n")
        f.write("\nNo meteorological extremes were deleted; all rows are preserved. "
                "No spatial score, neighbor claim, or capability claim is made here.\n\n")
        f.write("## Artifacts\n\n")
        for s in manifest["stations"]:
            f.write(f"- `{s['processed_file']}` sha256 `{s['processed_sha256'][:16]}…`\n")
        f.write(f"\nManifest: `data/noaa/metadata/station_manifest.json`. "
                f"Reproduce: `python -m src.noaa.run`.\n")


if __name__ == "__main__":
    run_noaa_pipeline()
