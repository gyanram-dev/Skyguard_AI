"""Calibrate station-specific statistical detectors (offline, deterministic).

For each configured GHCNh station: load the processed 2022-2024 frame,
build the detector frame (UTC timestamps as naive strings, altimeter as
the pressure channel — recorded explicitly, never relabeled), calibrate
on a fixed clean window, persist the artifact, and regenerate the
detector registry. Delhi artifacts are never touched.

Usage: python -m src.detection.calibrate [--root .]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from src.detection import registry as REG
from src.detection.station_statistical import StationStatisticalDetector

logger = logging.getLogger("skyguard.calibrate")

# backend_id -> frontend/city/cadence/train window. Train windows are
# fixed calendar ranges in a quiet season; the audit recorded no
# structural gaps inside them.
STATIONS: tuple[dict, ...] = (
    {"backend_station_id": "INI0000VABB", "station_id": "MUM-03",
     "city": "Mumbai", "cadence_min": 30.0,
     "train_start": "2023-01-05 00:00:00", "train_end": "2023-02-15 00:00:00"},
    {"backend_station_id": "INI0000VOHS", "station_id": "HYD-07",
     "city": "Hyderabad", "cadence_min": 30.0,
     "train_start": "2023-01-05 00:00:00", "train_end": "2023-02-15 00:00:00"},
    {"backend_station_id": "INI0000VOMM", "station_id": "CHE-03",
     "city": "Chennai", "cadence_min": 30.0,
     "train_start": "2023-01-05 00:00:00", "train_end": "2023-02-15 00:00:00"},
    {"backend_station_id": "INI0000VOBL", "station_id": "BLR-05",
     "city": "Bengaluru", "cadence_min": 30.0,
     "train_start": "2023-01-05 00:00:00", "train_end": "2023-02-15 00:00:00"},
    {"backend_station_id": "INI0000VAPO", "station_id": "PUN-10",
     "city": "Pune", "cadence_min": 30.0,
     "train_start": "2023-06-01 00:00:00", "train_end": "2023-09-01 00:00:00"},
    {"backend_station_id": "INU042809-1", "station_id": "KOL-02",
     "city": "Kolkata", "cadence_min": 30.0,
     "train_start": "2023-01-05 00:00:00", "train_end": "2023-02-15 00:00:00"},
    {"backend_station_id": "INI0000VABP", "station_id": "BHO-08",
     "city": "Bhopal", "cadence_min": 30.0,
     "train_start": "2023-01-05 00:00:00", "train_end": "2023-02-15 00:00:00"},
    {"backend_station_id": "INI0000VIJP", "station_id": "JAI-02",
     "city": "Jaipur", "cadence_min": 30.0,
     "train_start": "2023-01-05 00:00:00", "train_end": "2023-02-15 00:00:00"},
    {"backend_station_id": "INI0000VILK", "station_id": "LUCK-04",
     "city": "Lucknow", "cadence_min": 30.0,
     "train_start": "2023-01-05 00:00:00", "train_end": "2023-02-15 00:00:00"},
    {"backend_station_id": "INI0000VICG", "station_id": "CHD-09",
     "city": "Chandigarh", "cadence_min": 30.0,
     "train_start": "2023-06-01 00:00:00", "train_end": "2023-09-01 00:00:00"},
)

PRESSURE_SEMANTICS = "altimeter_qnh_hpa"
RH_PROVENANCE = "REPORTED (provider file; measured-vs-calculated not verifiable)"


def detector_frame(processed_path: Path) -> pd.DataFrame:
    """Detector input frame from a processed station file."""
    raw = pd.read_csv(processed_path,
                      usecols=["timestamp_utc", "temperature_c",
                               "relative_humidity_pct", "altimeter_setting_hpa"])
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime(raw["timestamp_utc"], utc=True)
                       .dt.strftime("%Y-%m-%d %H:%M:%S"),
        "temperature_c": pd.to_numeric(raw["temperature_c"], errors="coerce"),
        "pressure_hpa": pd.to_numeric(raw["altimeter_setting_hpa"], errors="coerce"),
        "relative_humidity_pct": pd.to_numeric(raw["relative_humidity_pct"],
                                               errors="coerce"),
    })
    return frame.sort_values("timestamp").reset_index(drop=True)


def calibrate_all(root: Path) -> list[dict]:
    """Calibrate every configured station; write artifacts + registry."""
    root = Path(root)
    out_dir = root / "data" / "detectors" / "statistical"
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for cfg in STATIONS:
        src = root / "data" / "noaa" / "processed" / f"{cfg['backend_station_id']}_2022_2024.csv"
        frame = detector_frame(src)
        full_cfg = {**cfg, "pressure_semantics": PRESSURE_SEMANTICS,
                    "pressure_column": "altimeter_setting_hpa",
                    "rh_provenance": RH_PROVENANCE}
        detector = StationStatisticalDetector.calibrate(
            full_cfg, frame, cfg["train_start"], cfg["train_end"])
        dest = out_dir / f"{cfg['backend_station_id']}.json"
        dest.write_text(json.dumps(detector.artifact, indent=2), encoding="utf-8")
        entries.append({**detector.describe(),
                        "backend_station_id": cfg["backend_station_id"],
                        "artifact": f"data/detectors/statistical/{cfg['backend_station_id']}.json"})
        logger.info("%s: artifact -> %s", cfg["station_id"], dest)
    registry = {"version": 1, "detector_family": "station-specific statistical baseline",
                "pressure_semantics": PRESSURE_SEMANTICS,
                "note": "QNH altimeter is the pressure channel; never relabeled "
                        "as station-level pressure. Delhi detector untouched.",
                "detectors": entries}
    (root / "data" / "detectors" / "registry.json").write_text(
        json.dumps(registry, indent=2), encoding="utf-8")
    REG.reset_cache()
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    entries = calibrate_all(Path(args.root))
    print(f"calibrated {len(entries)} station detectors")


if __name__ == "__main__":
    main()
