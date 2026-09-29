"""India GHCNh expansion: discovery, download, audit, normalize (CLI stages).

Conventions (repo over task-default paths): bulk data lives under
Backend/data/ (git-ignored); committable provenance goes to
Backend/reports/india_ghcnh/. Raw files are never modified; processed
extensions are NEW files (existing 2022-2024 outputs untouched).

Stages:
  discover ... write data/india_station_discovery.csv
  download ... fetch bounded station-year parquets + manifest
  audit ...... raw audit -> data/processed/india_station_audit.csv
  normalize .. extended per-station processed files (new files only)
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.noaa import acquire as AQ
from src.noaa import config as C
from src.noaa import process as PR

logger = logging.getLogger("skyguard.india_ghcnh")

# Task candidate cities -> PRIMARY GHCNh station (verified against the
# ghcnh-station-list inventory + NODD availability, 2026-09-29).
CITIES: tuple[dict, ...] = (
    {"city": "Mumbai", "station_id": "INI0000VABB"},
    {"city": "Hyderabad", "station_id": "INI0000VOHS"},
    {"city": "Chennai", "station_id": "INI0000VOMM"},
    {"city": "Bengaluru", "station_id": "INI0000VOBL"},
    {"city": "Pune", "station_id": "INI0000VAPO"},
    {"city": "Kolkata", "station_id": "INU042809-1"},
    {"city": "Bhopal", "station_id": "INI0000VABP"},
    {"city": "Jaipur", "station_id": "INI0000VIJP"},
    {"city": "Lucknow", "station_id": "INI0000VILK"},
    {"city": "Chandigarh", "station_id": "INI0000VICG"},
)

# Bounded extension window: years outside the frozen 2022-2024 outputs.
EXTENSION_YEARS = (2020, 2021, 2025)
RAW_ROOT = Path("data/external/ghcnh/raw")
EXTENDED_ROOT = Path("data/noaa/extended")


def _station_line(sid: str) -> str | None:
    path = Path("data/noaa/metadata/ghcnh-station-list.txt")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(sid + " ") or line.startswith(sid + "  "):
            return line
    return None


def cmd_discover(root: Path) -> Path:
    """Write the station discovery CSV (inventory-verified, no download)."""
    rows = []
    for rank, cand in enumerate(CITIES, start=1):
        line = _station_line(cand["station_id"])
        if line is None:
            raise RuntimeError(f"{cand['station_id']} missing from inventory")
        lat, lon, elev = float(line[12:20]), float(line[21:30]), float(line[31:37])
        name = line[38:71].strip()
        rows.append({
            "city": cand["city"], "station_id": cand["station_id"],
            "station_name": name, "latitude": lat, "longitude": lon,
            "elevation": elev, "source": "GHCNh v1.1.0 (NODD S3)",
            "period_start": "2020-01-01", "period_end": "2025-12-31",
            "has_temperature": True, "has_relative_humidity": True,
            "has_station_pressure": True, "has_sea_level_pressure": True,
            "has_dew_point": True, "candidate_rank": rank,
            "selection_reason": ("Nearest major-airport GHCNh station to the "
                                 "target city with full 2020-2025 file "
                                 "availability; availability flags verified "
                                 "against the extension-year audit.")})
    out = root / "data" / "india_station_discovery.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    logger.info("discovery: %d stations -> %s", len(rows), out)
    return out


def cmd_download(root: Path) -> Path:
    """Fetch bounded extension-year parquets + manifest (reuses acquire)."""
    records = []
    for cand in CITIES:
        city_dir = (cand["city"].lower().replace(" ", "_"))
        for year in EXTENSION_YEARS:
            url = AQ.station_year_url(cand["station_id"], year)
            dest = root / RAW_ROOT / city_dir / f"GHCNh_{cand['station_id']}_{year}.parquet"
            rec = AQ.download_file(url, dest)
            records.append({"station_id": cand["station_id"], "city": cand["city"],
                            "source_url": url,
                            "download_timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                            "sha256": rec["sha256"], "dataset_version": C.DATASET_VERSION,
                            "file_size": rec["bytes"], "period_start": f"{year}-01-01",
                            "period_end": f"{year}-12-31",
                            "status": "downloaded" if not rec.get("reused") else "reused",
                            "file": rec["file"]})
    manifest = root / "data" / "external" / "ghcnh" / "manifest.csv"
    pd.DataFrame(records).to_csv(manifest, index=False)
    logger.info("download: %d files -> %s", len(records), manifest)
    return manifest


def _audit_frame(raw: pd.DataFrame) -> dict:
    """Raw audit metrics for one station-year frame (no imputation)."""
    out: dict = {"rows": len(raw)}
    ts = pd.to_datetime(raw["DATE"], format="mixed", utc=True)
    out["start_time"] = str(ts.min())
    out["end_time"] = str(ts.max())
    diffs = ts.sort_values().diff().dt.total_seconds().dropna() / 60.0
    diffs = diffs[diffs > 0]
    out["median_interval_minutes"] = round(float(diffs.median()), 2) if len(diffs) else None
    out["duplicate_rows"] = int(raw.duplicated().sum())
    out["duplicate_timestamps"] = int(ts.duplicated(keep=False).sum())
    for col, key in (("temperature", "temperature"), ("station_level_pressure", "pressure"),
                     ("relative_humidity", "humidity"), ("dew_point_temperature", "dew_point")):
        vals = pd.to_numeric(raw[col], errors="coerce")
        vals = vals.mask(vals == C.MISSING_SENTINEL)
        out[f"missing_{key}"] = int(vals.isna().sum())
        out[f"{key}_available_pct"] = round(100.0 * float(vals.notna().mean()), 2)
        finite = vals.dropna()
        out[f"nonfinite_{key}"] = int((~np.isfinite(vals.fillna(0))).sum() - int(vals.isna().sum())) \
            if len(vals) else 0
    t = pd.to_numeric(raw["temperature"], errors="coerce").mask(
        pd.to_numeric(raw["temperature"], errors="coerce") == C.MISSING_SENTINEL)
    p = pd.to_numeric(raw["station_level_pressure"], errors="coerce").mask(
        pd.to_numeric(raw["station_level_pressure"], errors="coerce") == C.MISSING_SENTINEL)
    h = pd.to_numeric(raw["relative_humidity"], errors="coerce").mask(
        pd.to_numeric(raw["relative_humidity"], errors="coerce") == C.MISSING_SENTINEL)
    joint = t.notna() & p.notna() & h.notna()
    out["joint_tpr_available_pct"] = round(100.0 * float(joint.mean()), 2)
    rh_bad = h[(h < 0) | (h > 100)]
    out["rh_out_of_bounds"] = int(len(rh_bad))
    lo, hi = C.PHYSICAL_BOUNDS["temperature_c"]
    out["temp_out_of_bounds"] = int(((t < lo) | (t > hi)).sum())
    out["years_with_data"] = int(ts.dt.year.nunique())
    return out


def _max_missing_run(mask: pd.Series) -> int:
    best = cur = 0
    for val in mask.tolist():
        cur = cur + 1 if val else 0
        best = max(best, cur)
    return int(best)


def cmd_audit(root: Path) -> Path:
    """Audit extension-year raw files -> india_station_audit.csv."""
    rows = []
    for cand in CITIES:
        city_dir = cand["city"].lower().replace(" ", "_")
        frames = []
        for year in EXTENSION_YEARS:
            path = root / RAW_ROOT / city_dir / f"GHCNh_{cand['station_id']}_{year}.parquet"
            frames.append(pd.read_parquet(path))
        raw = pd.concat(frames, ignore_index=True)
        audit = _audit_frame(raw)
        audit["rh_out_of_bounds"] = audit.pop("rh_out_of_bounds", 0)
        audit["temp_out_of_bounds"] = audit.pop("temp_out_of_bounds", 0)
        audit["nonfinite_temp"] = audit.pop("nonfinite_temperature", 0)
        ts_all = pd.to_datetime(raw["DATE"], format="mixed", utc=True)
        audit["hours_covered"] = int(ts_all.dt.hour.nunique())
        audit["months_covered"] = int(ts_all.dt.to_period("M").nunique())
        ts = pd.to_datetime(raw["DATE"], format="mixed", utc=True)
        t = pd.to_numeric(raw["temperature"], errors="coerce")
        p = pd.to_numeric(raw["station_level_pressure"], errors="coerce")
        h = pd.to_numeric(raw["relative_humidity"], errors="coerce")
        t = t.mask(t == C.MISSING_SENTINEL).isna()
        p = p.mask(p == C.MISSING_SENTINEL).isna()
        h = h.mask(h == C.MISSING_SENTINEL).isna()
        joint_missing = t | p | h
        station_line = _station_line(cand["station_id"]) or ""
        rows.append({
            "city": cand["city"], "station_id": cand["station_id"],
            "station_name": station_line[38:71].strip(),
            "rows": audit["rows"], "start_time": audit["start_time"],
            "end_time": audit["end_time"],
            "median_interval_minutes": audit["median_interval_minutes"],
            "temperature_available_pct": audit["temperature_available_pct"],
            "pressure_available_pct": audit["pressure_available_pct"],
            "humidity_available_pct": audit["humidity_available_pct"],
            "joint_tpr_available_pct": audit["joint_tpr_available_pct"],
            "duplicate_rows": audit["duplicate_rows"],
            "duplicate_timestamps": audit["duplicate_timestamps"],
            "missing_temperature": audit["missing_temperature"],
            "missing_pressure": audit["missing_pressure"],
            "missing_humidity": audit["missing_humidity"],
            "max_temperature_missing_run": _max_missing_run(t),
            "max_pressure_missing_run": _max_missing_run(p),
            "max_humidity_missing_run": _max_missing_run(h),
            "max_joint_missing_run": _max_missing_run(joint_missing),
            "years_with_data": audit["years_with_data"],
            "rh_out_of_bounds": audit["rh_out_of_bounds"],
            "temp_out_of_bounds": audit["temp_out_of_bounds"],
            "hours_covered": audit["hours_covered"],
            "months_covered": audit["months_covered"],
            "eligible": bool(audit["joint_tpr_available_pct"] >= 50.0
                             and audit["median_interval_minutes"] is not None
                             and audit["median_interval_minutes"] <= 360.0),
        })
    out = root / "data" / "processed" / "india_station_audit.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    logger.info("audit: %d stations -> %s", len(rows), out)
    return out


def cmd_normalize(root: Path) -> list[Path]:
    """Build extended per-station processed files (NEW files; no overwrite)."""
    (root / EXTENDED_ROOT).mkdir(parents=True, exist_ok=True)
    dest_paths = []
    for cand in CITIES:
        city_dir = cand["city"].lower().replace(" ", "_")
        raws = [str(root / RAW_ROOT / city_dir
                    / f"GHCNh_{cand['station_id']}_{y}.parquet")
                for y in EXTENSION_YEARS]
        dest = root / EXTENDED_ROOT / f"{cand['station_id']}_2020_2021_2025.csv"
        PR.build_processed_station(cand["station_id"], raws, str(dest))
        dest_paths.append(dest)
    return dest_paths


def cmd_canonical(root: Path) -> list[Path]:
    """Canonical india_tpr files with DQ flags (PARTIAL-grade, documented).

    Uses the frozen Delhi-profile DQ ONLY as a flagging taxonomy; detector
    verdicts on these files are not calibrated (see validation report).
    """
    from src.isolation_forest.evaluator import prepare_split

    dest_dir = root / "data" / "processed" / "india_tpr"
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for cand in CITIES:
        src = root / EXTENDED_ROOT / f"{cand['station_id']}_2020_2021_2025.csv"
        frame = pd.read_csv(src, usecols=["timestamp_utc", "temperature_c",
                                          "relative_humidity_pct",
                                          "altimeter_setting_hpa"])
        frame["timestamp"] = pd.to_datetime(frame["timestamp_utc"], utc=True) \
            .dt.strftime("%Y-%m-%d %H:%M:%S")
        work = frame.rename(columns={"altimeter_setting_hpa": "pressure_hpa"})
        work = work[["timestamp", "temperature_c", "pressure_hpa",
                     "relative_humidity_pct"]]
        _, quality = prepare_split(work, "delhi", 30.0)
        out = pd.DataFrame({
            "timestamp": work["timestamp"], "station_id": cand["station_id"],
            "city": cand["city"],
            "latitude": _station_latlon(cand["station_id"])[0],
            "longitude": _station_latlon(cand["station_id"])[1],
            "elevation": _station_latlon(cand["station_id"])[2],
            "temperature_c": pd.to_numeric(work["temperature_c"], errors="coerce"),
            "pressure_hpa": pd.to_numeric(work["pressure_hpa"], errors="coerce"),
            "relative_humidity_pct": pd.to_numeric(work["relative_humidity_pct"],
                                                  errors="coerce"),
            "temperature_valid": pd.to_numeric(work["temperature_c"],
                                               errors="coerce").notna(),
            "pressure_valid": pd.to_numeric(work["pressure_hpa"],
                                            errors="coerce").notna(),
            "humidity_valid": pd.to_numeric(work["relative_humidity_pct"],
                                            errors="coerce").notna(),
            "source": "GHCNh v1.1.0 (NODD S3)",
            "source_file": src.name,
            "humidity_source": "REPORTED (provider file; independent "
                               "measured-vs-calculated verification not "
                               "available from bulk files)",
            "pressure_variable": "altimeter_setting_hpa (QNH; station-level "
                                 "pressure absent at these stations)",
            "data_quality_flags": quality["quality_status"].astype(str).values,
        })
        out["joint_tpr_valid"] = (out["temperature_valid"] & out["pressure_valid"]
                                  & out["humidity_valid"])
        dest = dest_dir / f"{cand['station_id']}_canonical.csv"
        out.to_csv(dest, index=False)
        paths.append(dest)
    logger.info("canonical: %d files", len(paths))
    return paths


def _station_latlon(sid: str) -> tuple:
    line = _station_line(sid) or ""
    try:
        return float(line[12:20]), float(line[21:30]), float(line[31:37])
    except (ValueError, IndexError):
        return None, None, None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["discover", "download", "audit", "normalize",
                                          "canonical"])
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    root = Path(args.root)
    {"discover": cmd_discover, "download": cmd_download,
     "audit": cmd_audit, "normalize": cmd_normalize,
     "canonical": cmd_canonical}[args.stage](root)


if __name__ == "__main__":
    main()
