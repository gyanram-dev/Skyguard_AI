"""Mumbai statistical-detector validation (controlled faults, no training).

Uses frozen pipeline pieces only (prepare_split, build_features,
build_statistical_baseline) on real Mumbai 2022-2024 observations with
station-plausible injected faults. No model is trained, no threshold
changed, no frozen artifact touched. Writes metrics JSON for the audit.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.baseline.statistical_baseline import build_statistical_baseline
from src.features.feature_builder import build_features_for_dataset
from src.isolation_forest.evaluator import prepare_split

STATION = "INI0000VABB"
CITY = "Mumbai"
CADENCE = 30.0
SEGMENT_START = "2023-03-01 00:00:00"
SEGMENT_DAYS = 30


def load_segment() -> pd.DataFrame:
    f = pd.read_csv("data/noaa/processed/INI0000VABB_2022_2024.csv",
                    usecols=["timestamp_utc", "temperature_c",
                             "relative_humidity_pct", "altimeter_setting_hpa"])
    f["timestamp"] = pd.to_datetime(f["timestamp_utc"], utc=True).dt.strftime(
        "%Y-%m-%d %H:%M:%S")
    f = f.rename(columns={"altimeter_setting_hpa": "pressure_hpa"})
    frame = f[["timestamp", "temperature_c", "pressure_hpa",
               "relative_humidity_pct"]].reset_index(drop=True)
    start = frame[frame["timestamp"] >= SEGMENT_START].index.min()
    return frame.iloc[start:start + SEGMENT_DAYS * 48].reset_index(drop=True)


def inject(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Station-plausible faults (Mumbai March: 24-32C, RH 50-80%)."""
    out = frame.copy()
    truth = np.zeros(len(out), dtype=int)
    faults: dict[str, list[int]] = {}

    def mark(name: str, idx):
        idx = [i for i in idx if 0 <= i < len(out)]
        faults[name] = idx
        truth[idx] = 1

    mark("spike", [500])
    out.loc[500, "temperature_c"] += 10.0
    mark("frozen", list(range(700, 724)))
    out.loc[700:723, "temperature_c"] = out.loc[699, "temperature_c"]
    drift_idx = list(range(900, 900 + 240))
    out.loc[900:1139, "temperature_c"] += np.arange(240) * 0.03
    mark("drift", drift_idx)
    mark("cross_variable", [1300])
    out.loc[1300, "relative_humidity_pct"] = 5.0
    return out, {"truth": truth, "faults": {k: v for k, v in faults.items()}}


def run_validation(root: str | Path = ".") -> dict:
    root = Path(root)
    base = load_segment()
    injected, meta = inject(base)
    features, quality = prepare_split(injected, "delhi", CADENCE)
    feat = build_features_for_dataset(features, "delhi", cadence_min=CADENCE)
    baseline, _ = build_statistical_baseline(feat, quality, "delhi",
                                             cadence_min=CADENCE)
    flag = (pd.to_numeric(baseline["statistical_baseline_flag"],
                          errors="coerce").fillna(0).astype(int).to_numpy())
    truth = meta["truth"]
    tp = int(((flag == 1) & (truth == 1)).sum())
    fp = int(((flag == 1) & (truth == 0)).sum())
    fn = int(((flag == 0) & (truth == 1)).sum())
    per_fault = {}
    for name, idx in meta["faults"].items():
        hit = int(flag[idx].sum())
        per_fault[name] = {"injected": len(idx), "detected": hit,
                           "recall": round(hit / len(idx), 4) if idx else None}
    payload = {
        "station": STATION, "city": CITY, "cadence_min": CADENCE,
        "segment": {"start": SEGMENT_START, "days": SEGMENT_DAYS,
                    "rows": len(base)},
        "pressure_basis": "altimeter_setting_hpa (validator runs the "
                          "pressure channel on altimeter; detector-ready "
                          "status remains PARTIAL, not FULL_TPR)",
        "overall": {"tp": tp, "fp": fp, "fn": fn,
                    "precision": round(tp / (tp + fp), 4) if tp + fp else None,
                    "recall": round(tp / (tp + fn), 4) if tp + fn else None},
        "per_fault": per_fault,
        "method": "frozen statistical baseline (z=3.0/IQR), no training",
    }
    out_dir = root / "reports" / "india_ghcnh"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mumbai_statistical_validation.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_validation("."), indent=2))
