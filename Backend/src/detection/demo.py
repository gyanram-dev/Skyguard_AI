"""Deterministic CONTROLLED_DEMO for calibrated station detectors.

A copy of real GHCNh observations gets four controlled faults applied with
the existing benchmark injectors (`src.benchmark.injectors`) at parameter
values taken from the existing benchmark configuration
(`src.benchmark.config`). Injected rows are labeled CONTROLLED_DEMO /
BENCHMARK: they are synthetic by construction and must never be presented
as genuine historical observations. The injected frame is built in memory
and never written back to `data/noaa/processed/`; only a small evidence
JSON (per-fault counts, metrics, and the injected rows' clean/injected
values) is written under `reports/`.

Scored through the SAME detector replay uses
(`StationStatisticalDetector.score_frame`), so the demo measures the
shipping path, not a parallel implementation.

Usage:
    python -m src.detection.demo [--backend-id INI0000VABB] [--days 30]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.benchmark import config as C
from src.benchmark.injectors import (
    apply_cross_variable,
    apply_drift,
    apply_frozen,
    apply_spike,
    humidity_valid,
)
from src.detection.station_statistical import load_detector

logger = logging.getLogger("skyguard.detection_demo")

LABEL = "CONTROLLED_DEMO"
LAYER = "BENCHMARK"
CADENCE_MIN = 30.0
ROWS_PER_DAY = int(24 * 60 / CADENCE_MIN)

# backend_id -> frontend id + city + demo window (all real GHCNh stations).
STATIONS: dict[str, dict] = {
    "INI0000VABB": {"station_id": "MUM-03", "city": "Mumbai"},
    "INI0000VOBL": {"station_id": "BLR-05", "city": "Bengaluru"},
    "INI0000VOHS": {"station_id": "HYD-07", "city": "Hyderabad"},
    "INI0000VOMM": {"station_id": "CHE-03", "city": "Chennai"},
}

SEGMENT_START = "2023-03-01 00:00:00"

# Fault slots inside the 30-day window (well separated, never overlapping).
SPIKE_AT = 500
FROZEN_AT = 700
DRIFT_AT = 800
CROSS_SEARCH_FROM = 950
CROSS_SEARCH_TO = 1250


def load_segment(root: Path, backend_id: str, days: int) -> pd.DataFrame:
    """Real observations for one station window (read-only, chronological)."""
    path = root / "data" / "noaa" / "processed" / f"{backend_id}_2022_2024.csv"
    raw = pd.read_csv(path, usecols=["timestamp_utc", "temperature_c",
                                     "relative_humidity_pct",
                                     "altimeter_setting_hpa"])
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime(raw["timestamp_utc"], utc=True)
                       .dt.strftime("%Y-%m-%d %H:%M:%S"),
        "temperature_c": pd.to_numeric(raw["temperature_c"], errors="coerce"),
        # QNH altimeter is the pressure channel; never relabelled.
        "pressure_hpa": pd.to_numeric(raw["altimeter_setting_hpa"],
                                      errors="coerce"),
        "relative_humidity_pct": pd.to_numeric(raw["relative_humidity_pct"],
                                               errors="coerce"),
    }).sort_values("timestamp").reset_index(drop=True)
    start = frame.index[frame["timestamp"] >= SEGMENT_START].min()
    if pd.isna(start):
        raise ValueError(f"{backend_id}: no rows at/after {SEGMENT_START}")
    return frame.iloc[int(start):int(start) + days * ROWS_PER_DAY].reset_index(drop=True)


def _cross_start(frame: pd.DataFrame, duration: int) -> int:
    """First slot in the search range whose humidity ramp stays in [0, 100]."""
    rates = C.CROSS_RATES_PER_READING["train_id"]
    for start in range(CROSS_SEARCH_FROM,
                       min(CROSS_SEARCH_TO, len(frame) - duration)):
        window = frame["relative_humidity_pct"].iloc[start:start + duration]
        ramped = window.to_numpy(dtype=float) + \
            float(rates["relative_humidity_pct"][1]) * np.arange(1, duration + 1)
        if humidity_valid(ramped):
            return start
    raise ValueError("no humidity-safe cross-variable slot in the demo window")


def inject(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict, list[dict]]:
    """Apply the four controlled faults; return (marked frame, plan, values).

    Parameters come from the existing benchmark configuration, so the demo
    stays inside the already-validated fault envelope for a single fault
    type. No random draw: reruns are identical.
    """
    out = frame.copy()
    truth = np.zeros(len(out), dtype=int)
    values: list[dict] = []
    plan: dict[str, dict] = {}

    def record(name: str, target: str, idx: list[int],
               clean: dict[str, np.ndarray], injected: dict[str, np.ndarray]) -> None:
        for offset, i in enumerate(idx):
            truth[i] = 1
            for var in injected:
                values.append({
                    "label": LABEL, "layer": LAYER, "fault_type": name,
                    "timestamp": str(out["timestamp"].iloc[i]),
                    "target_variable": var,
                    "clean_value": float(clean[var][offset]),
                    "injected_value": float(injected[var][offset]),
                })
        plan[name] = {**plan.get(name, {}), "target_variable": target,
                      "rows": len(idx), "start_index": idx[0],
                      "end_index": idx[-1],
                      "start_timestamp": str(out["timestamp"].iloc[idx[0]]),
                      "end_timestamp": str(out["timestamp"].iloc[idx[-1]])}

    # 1. Temperature spike (benchmark ID amplitude, single reading).
    amplitude = float(C.SPIKE_AMPLITUDE["temperature_c"]["train_id"][1])
    idx = [SPIKE_AT]
    clean = {"temperature_c": out.loc[idx, "temperature_c"].to_numpy(dtype=float)}
    injected = {"temperature_c": apply_spike(clean["temperature_c"], amplitude, 1)}
    out.loc[idx, "temperature_c"] = injected["temperature_c"]
    plan["spike"] = {"fault_type": "SPIKE", "target_variable": "temperature_c",
                     "amplitude_c": amplitude, "direction": 1,
                     "parameter_source": "benchmark config (train_id range)"}
    record("spike", "temperature_c", idx, clean, injected)

    # 2. Frozen temperature sensor (benchmark ID run length).
    run = int(C.FROZEN_DURATION["train_id"][1])
    idx = list(range(FROZEN_AT, FROZEN_AT + run))
    cleans = {v: out.loc[idx, v].to_numpy(dtype=float) for v in C.CORE_VARS}
    frozen = apply_frozen(cleans, "temperature_c")
    out.loc[idx, "temperature_c"] = frozen["temperature_c"]
    plan["frozen"] = {"fault_type": "FROZEN", "target_variable": "temperature_c",
                      "run_length": run,
                      "parameter_source": "benchmark config (train_id range)"}
    record("frozen", "temperature_c", idx,
           {"temperature_c": cleans["temperature_c"]},
           {"temperature_c": frozen["temperature_c"]})

    # 3. Progressive drift (benchmark ID rate + duration).
    rate = float(C.DRIFT_RATE_PER_HOUR["temperature_c"]["train_id"][1])
    hours = float(C.DRIFT_DURATION_HOURS["train_id"][1])
    span = int(hours * 60 / CADENCE_MIN)
    idx = list(range(DRIFT_AT, DRIFT_AT + span))
    elapsed = np.arange(span, dtype=float) * (CADENCE_MIN / 60.0)
    drift_clean = {"temperature_c": out.loc[idx, "temperature_c"].to_numpy(dtype=float)}
    drifted = {"temperature_c": apply_drift(drift_clean["temperature_c"], rate, 1,
                                            elapsed)}
    out.loc[idx, "temperature_c"] = drifted["temperature_c"]
    plan["drift"] = {"fault_type": "DRIFT", "target_variable": "temperature_c",
                     "rate_per_hour": rate, "duration_hours": hours,
                     "parameter_source": "benchmark config (train_id range)"}
    record("drift", "temperature_c", idx, drift_clean, drifted)

    # 4. Cross-variable inconsistency (T/RH ramp together, pressure held).
    span = int(C.CROSS_DURATION["train_id"][1])
    start = _cross_start(out, span)
    idx = list(range(start, start + span))
    rates = {k: float(v[1]) for k, v in C.CROSS_RATES_PER_READING["train_id"].items()}
    clean_vars = {v: out.loc[idx, v].to_numpy(dtype=float) for v in C.CORE_VARS}
    crossed = apply_cross_variable(clean_vars, rates)
    for var in C.CORE_VARS:
        out.loc[idx, var] = crossed[var]
    plan["cross_variable"] = {"fault_type": "CROSS_VARIABLE",
                              "target_variable": "all_core",
                              "rates_per_reading": rates,
                              "parameter_source": "benchmark config (train_id range)"}
    record("cross_variable", "all_core", idx, clean_vars, crossed)

    meta = {"label": LABEL, "layer": LAYER, "truth": truth, "plan": plan}
    return out, meta, values


def _dq_excluded(result: dict) -> bool:
    """True when the data-quality layer withheld the row from the detector."""
    return not bool((result.get("data_quality") or {}).get("ml_eligible", True))


def _metrics(results: list[dict], truth: np.ndarray) -> dict:
    """Row-level confusion matrix + honest background flag rate.

    Rows the data-quality layer withheld are counted separately: they can
    never be flagged, so they appear as misses and must be visible as such
    instead of being silently folded into recall.
    """
    flagged = np.array([bool(r["anomaly"]) for r in results], dtype=bool)
    injected = truth.astype(bool)
    excluded = np.array([_dq_excluded(r) for r in results], dtype=bool)
    tp = int((flagged & injected).sum())
    fp = int((flagged & ~injected).sum())
    fn = int((~flagged & injected).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else None)
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "injected_rows": int(injected.sum()),
        "background_rows": int((~injected).sum()),
        "background_flagged": fp,
        "background_flag_rate": round(fp / int((~injected).sum()), 4)
        if (~injected).sum() else None,
        "data_quality_excluded_rows": int(excluded.sum()),
        "injected_rows_withheld_by_dq": int((excluded & injected).sum()),
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
    }


def _quiet_window_flag_rate(results: list[dict], rows: int) -> dict:
    """Flag rate on the untouched real window before the first injection."""
    window = results[:min(SPIKE_AT, rows)]
    flagged = sum(1 for r in window if r["anomaly"])
    return {"rows": len(window), "flagged": flagged,
            "flag_rate": round(flagged / len(window), 4) if window else None,
            "note": ("Background rows are NOT proven normal; this measures the "
                     "detector's flag rate on untouched real observations.")}


def run_demo(root: str | Path = ".", backend_id: str = "INI0000VABB",
             days: int = 30) -> dict:
    """Run the controlled demo end-to-end and return the evidence payload."""
    root = Path(root)
    cfg = STATIONS.get(backend_id)
    if cfg is None:
        raise ValueError(f"no demo configuration for '{backend_id}'")
    detector = load_detector(root, backend_id)
    if detector is None:
        raise ValueError(f"{backend_id}: no calibrated detector (run "
                         "`python -m src.detection.calibrate`)")
    base = load_segment(root, backend_id, days)
    injected, meta, values = inject(base)
    # Detector scores the injected copy only; `base` is never mutated.
    assert not base.equals(injected), "demo must inject faults before scoring"
    results = detector.score_frame(injected, None)
    metrics = _metrics(results, meta["truth"])
    per_fault = {}
    for name, spec in meta["plan"].items():
        start, end = spec.get("start_index"), spec.get("end_index")
        if start is None:
            per_fault[name] = {"injected": spec["rows"], "detected": None,
                               "recall": None}
            continue
        window = results[start:end + 1]
        detected = sum(1 for r in window if r["anomaly"])
        per_fault[name] = {
            "injected": len(window), "detected": detected,
            "recall": round(detected / len(window), 4) if window else None,
            "withheld_by_data_quality": sum(1 for r in window
                                            if _dq_excluded(r)),
            "fault_type": spec["fault_type"],
            "target_variable": spec["target_variable"],
            "start_timestamp": spec.get("start_timestamp"),
            "end_timestamp": spec.get("end_timestamp"),
        }
    severities: dict[str, int] = {}
    for result in results:
        severities[result["severity"]] = severities.get(result["severity"], 0) + 1
    payload = {
        "label": LABEL,
        "layer": LAYER,
        "city": cfg["city"],
        "station_id": cfg["station_id"],
        "backend_station_id": backend_id,
        "detector": detector.artifact["detector_type"],
        "detector_method": detector.artifact["detector_method"],
        "cadence_min": detector.cadence_min,
        "pressure_semantics": detector.artifact["pressure_semantics"],
        "pressure_note": ("QNH altimeter is the pressure channel; it is never "
                          "relabelled as station pressure."),
        "window": {"start": str(base["timestamp"].iloc[0]),
                   "end": str(base["timestamp"].iloc[-1]), "rows": len(base)},
        "isolation": ("Injected rows exist only in memory for this run; the "
                      "processed historical dataset on disk is untouched."),
        "plan": meta["plan"],
        "overall": metrics,
        "per_fault": per_fault,
        "quiet_window": _quiet_window_flag_rate(results, len(base)),
        "severity_counts": severities,
        "injected_rows_detail": values,
        "method": ("frozen statistical baseline (z=3.0 / Tukey IQR=1.5) on "
                   "real GHCNh observations with controlled fault injection; "
                   "no model trained, no threshold changed"),
    }
    out_dir = root / "reports" / "india_ghcnh"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = "mumbai_controlled_demo.json" if backend_id == "INI0000VABB" else \
        f"{cfg['city'].lower()}_controlled_demo.json"
    (out_dir / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("%s: %s -> %s", cfg["city"], metrics, out_dir / name)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--backend-id", default="INI0000VABB")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    payload = run_demo(Path(args.root), args.backend_id, args.days)
    print(json.dumps({k: payload[k] for k in
                      ("city", "station_id", "overall", "per_fault",
                       "quiet_window")}, indent=2))


if __name__ == "__main__":
    main()
