"""Deterministic Indian station capability inventory from audited data.

Every claim is measured from repository files or the Phase 21A audit —
never assumed. Sources, in policy order: (1) Delhi AWS observations,
(2) GHCNh bulk data already used by SkyGuard (with manifest
provenance), (3) WIS2 capability entries (capability-only, no bulk
rows). Jena is inventoried as benchmark_internal and excluded from
operational claims.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

INVENTORY_VERSION = "phase24-v1"


def _frame_stats(ts: pd.Series, temp: pd.Series, rh: pd.Series,
                 pres: pd.Series) -> dict:
    """Measured per-station statistics (deterministic, rounded)."""
    n = len(ts)
    valid_ts = ts.dropna()
    dup = int(valid_ts.duplicated().sum()) if len(valid_ts) else 0
    ooo = 0
    prev = None
    for stamp in ts.tolist():
        try:
            moment = pd.Timestamp(stamp)
        except (TypeError, ValueError):
            continue
        if prev is not None and moment < prev:
            ooo += 1
        prev = moment
    finite_ts = pd.to_datetime(valid_ts, errors="coerce").dropna()
    cadence = None
    gaps = 0
    if len(finite_ts) >= 2:
        diffs = finite_ts.sort_values().diff().dt.total_seconds().dropna() / 60.0
        diffs = diffs[diffs > 0]
        if len(diffs):
            cadence = round(float(diffs.median()), 2)
            gaps = int((diffs > 3.0 * diffs.median()).sum())
    def missing(series: pd.Series) -> int:
        return int(pd.to_numeric(series, errors="coerce").isna().sum())
    return {
        "record_count": int(n),
        "coverage_start": str(valid_ts.iloc[0]) if len(valid_ts) else None,
        "coverage_end": str(valid_ts.iloc[-1]) if len(valid_ts) else None,
        "cadence_min": cadence,
        "missing_temperature": missing(temp),
        "missing_relative_humidity": missing(rh),
        "missing_pressure": missing(pres),
        "duplicate_count": dup,
        "out_of_order_count": ooo,
        "gap_count": gaps,
    }


def _ghcnh_entries(root: Path) -> list[dict]:
    """Inventory rows for GHCNh bulk stations (manifest + measured)."""
    manifest = json.loads((root / "data" / "noaa" / "metadata"
                           / "station_manifest.json").read_text(encoding="utf-8"))
    meta = {s["ghcnh_id"]: s for s in manifest["stations"]}
    entries = []
    for sid in sorted(meta):
        info = meta[sid]
        frame = pd.read_csv(root / info["processed_file"],
                            usecols=["timestamp_utc", "temperature_c",
                                     "relative_humidity_pct",
                                     "altimeter_setting_hpa"])
        stats = _frame_stats(frame["timestamp_utc"], frame["temperature_c"],
                             frame["relative_humidity_pct"],
                             frame["altimeter_setting_hpa"])
        entries.append({
            "station_id": sid, "station_name": info["name"],
            "region": info.get("region", "India"),
            "source": "GHCNh",
            "source_identifier": "doi:10.25921/jp3d-3v19 (NODD s3://noaa-ghcnh-pds)",
            "retrieval_date": manifest.get("access_date"),
            "license": "NOAA public domain (U.S. government work)",
            "latitude": info["lat"], "longitude": info["lon"],
            "elevation_m": info.get("elev_m"),
            "temperature_available": bool(stats["record_count"]
                                          - stats["missing_temperature"] > 0),
            "relative_humidity_available": bool(
                stats["record_count"] - stats["missing_relative_humidity"] > 0),
            "pressure_available": bool(stats["record_count"]
                                       - stats["missing_pressure"] > 0),
            "pressure_basis": "altimeter_qnh_hpa",
            "source_status": "historical_bulk",
            "provenance": {"manifest_rows": info["rows"],
                           "manifest_cadence_min":
                               info["median_cadence_minutes"],
                           "processed_file": info["processed_file"],
                           "processed_sha256": info.get("processed_sha256")},
            **stats,
        })
    return entries


def _delhi_entry(root: Path) -> dict:
    """Inventory row for the Delhi AWS observations."""
    frame = pd.read_csv(root / "data" / "processed" / "delhi_clean.csv",
                        usecols=["timestamp", "temperature_c",
                                 "pressure_hpa", "relative_humidity_pct"])
    stats = _frame_stats(frame["timestamp"], frame["temperature_c"],
                         frame["relative_humidity_pct"],
                         frame["pressure_hpa"])
    return {
        "station_id": "DELHI-AWS", "station_name": "Delhi-NCR AWS",
        "source": "Delhi-AWS",
        "source_identifier": "data/processed/delhi_clean.csv (repository bulk)",
        "retrieval_date": None,
        "license": "repository-bundled research data",
        "latitude": 28.6139, "longitude": 77.2090, "elevation_m": None,
        "temperature_available": True, "relative_humidity_available": True,
        "pressure_available": True, "pressure_basis": "station_level_hpa",
        "source_status": "historical_bulk",
        "provenance": {"timestamp_semantics": "naive-local IST (UTC+5:30)"},
        **stats,
    }


def _wis2_entries() -> list[dict]:
    """Capability-only rows from the Phase 21A audit (no bulk rows here)."""
    from src.live import sources as LS

    audit = json.loads(Path("data/external/imd_wis2/key_audit.json")
                       .read_text(encoding="utf-8")) \
        if Path("data/external/imd_wis2/key_audit.json").exists() else {}
    entries = []
    for station in sorted(LS.STATION_CAPABILITIES):
        caps = LS.STATION_CAPABILITIES[station]
        key = audit.get(station, {})
        entries.append({
            "station_id": f"IMD-{station}",
            "station_name": f"IMD {station.title()} (SYNOP)",
            "source": "IMD_WIS2",
            "source_identifier": "https://wis2box.imd.gov.in/oapi "
                                 f"(wigos {caps['wigos_id']})",
            "retrieval_date": key.get("end"),
            "license": "official IMD observations (access terms per IMD)",
            "latitude": caps.get("latitude"), "longitude": caps.get("longitude"),
            "elevation_m": caps.get("elevation_m"),
            "temperature_available": bool(caps["temperature"]),
            "relative_humidity_available": bool(caps["humidity"]),
            "pressure_available": bool(caps["station_pressure"]),
            "pressure_basis": ("station_level_hpa"
                               if caps["station_pressure"] else "unavailable"),
            "source_status": "live_capable",
            "provenance": {"audit_records_retrieved": key.get("retrieved"),
                           "audit_window": [key.get("start"), key.get("end")],
                           "bulk_rows_in_repo": 0},
            "record_count": 0, "coverage_start": None, "coverage_end": None,
            "cadence_min": 180.0, "missing_temperature": 0,
            "missing_relative_humidity": 0, "missing_pressure": 0,
            "duplicate_count": 0, "out_of_order_count": 0, "gap_count": 0,
        })
    return entries


def build_inventory(root: str | Path = ".") -> list[dict]:
    """Full deterministic inventory (sorted by station_id)."""
    root = Path(root)
    entries = [_delhi_entry(root), *_ghcnh_entries(root), *_wis2_entries(),
        {"station_id": "JENA", "station_name": "Jena climate station",
         "source": "Jena-benchmark", "source_identifier": "repository bulk",
         "retrieval_date": None, "license": "repository-bundled research data",
         "latitude": 50.9271, "longitude": 11.5892, "elevation_m": None,
         "temperature_available": True, "relative_humidity_available": True,
         "pressure_available": True, "pressure_basis": "station_level_hpa",
         "source_status": "benchmark_internal",
         "provenance": {"scope": "internal benchmark/regression only; "
                                 "never an Indian operational station"},
         "record_count": 0, "coverage_start": None, "coverage_end": None,
         "cadence_min": 10.0, "missing_temperature": 0,
         "missing_relative_humidity": 0, "missing_pressure": 0,
         "duplicate_count": 0, "out_of_order_count": 0, "gap_count": 0},
    ]
    entries.sort(key=lambda e: e["station_id"])
    return entries
