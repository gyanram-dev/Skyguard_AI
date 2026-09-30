"""Build per-station historical timeline artifacts (offline, one-shot).

For every mapped Indian station this writes
``data/showcase/timeline/<FRONTEND_ID>.json`` describing:

- the station's real observation series over its full available period
  (strided for rendering, missing values preserved as null);
- detector events, which are ALWAYS existing detector output:
  * Delhi (backend ``delhi``): the stored frozen ensemble predictions
    (``data/ensemble/delhi_ensemble_predictions.csv``). Rows belonging to
    a controlled benchmark injection are excluded — their sensor values
    are synthetic and must never appear as history;
  * GHCNh stations with a calibrated station-level detector: that exact
    detector (``src.detection.station_statistical``) run over the
    station's own real history;
  * anything else: no events, ``detector.available = false``, so the UI
    can say HISTORICAL DATA — DETECTOR VERDICT UNAVAILABLE.

Run: ``python -m src.showcase.build_timeline`` (writes JSON only).
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.api.dependencies import DataStore
from src.api.services import station_service as SS

logger = logging.getLogger("skyguard.showcase.timeline")

OUT_DIR = Path("data/showcase/timeline")
MAX_SERIES_POINTS = 1100
MAX_EVENTS = 600
DELHI_ENS = Path("data/ensemble/delhi_ensemble_predictions.csv")
DELHI_THRESHOLD_KEY = "ens_median"

# Availability -> confidence, exactly the serving convention
# (scoring.CONFIDENCE_BY_AVAILABILITY): the number is an evidence
# completeness proxy, never a probability.
COMPONENT_CONFIDENCE = {3: ("FULL_EVIDENCE", 1.0),
                        2: ("PARTIAL_EVIDENCE", 0.67),
                        1: ("LOW_CONTEXT", 0.33)}


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _evenly(events: list[dict], max_events: int) -> list[dict]:
    """Take at most ``max_events`` events spread evenly across the period.

    Flag rates on real 30-minute data are high, so a plain head() would
    cluster every marker inside one month. An even stride keeps the
    markers representative of the whole period, and the count is always
    reported separately (nothing is silently truncated).
    """
    events = sorted(events, key=lambda e: str(e.get("timestamp")))
    total = len(events)
    if total <= max_events or max_events <= 0:
        return events
    step = total / float(max_events)
    picked = [events[int(i * step)] for i in range(max_events)]
    return picked


def _stride_frame(frame: pd.DataFrame, value_cols: list[str]) -> dict:
    """Strided series so the chart keeps the full period at bounded size."""
    n = len(frame)
    step = max(1, int(math.ceil(n / MAX_SERIES_POINTS)))
    idx = range(0, n, step)
    ts = frame.iloc[list(idx)]["timestamp_"].astype(str).tolist()
    out = {"timestamps": ts}
    for name, column in zip(("temperature", "humidity", "pressure"), value_cols):
        out[name] = [_finite(v) for v in frame.iloc[list(idx)][column]]
    return out


def _delhi_artifact(store: DataStore) -> dict:
    """Timeline for the Delhi AWS station (frozen ensemble verdicts)."""
    bundle = store.pipeline["delhi"]
    obs = bundle["obs"].copy()
    obs["timestamp_"] = obs["timestamp"]
    series = _stride_frame(obs, ["temperature_c", "relative_humidity_pct",
                                 "pressure_hpa"])
    ens = bundle["ens"]
    stamps = ens["timestamp"].astype(str)
    ens = ens.assign(_ts=stamps)
    threshold = None
    try:  # frozen threshold, read from the calibration artifact
        import joblib

        cal = joblib.load(store.root / "models/ensemble/delhi_calibration.joblib")
        threshold = _finite(cal["thresholds"].get(DELHI_THRESHOLD_KEY))
    except Exception as exc:  # noqa: BLE001 - recorded, not fatal
        logger.warning("delhi threshold unavailable: %s", exc)
    from src.ensemble import severity as ES

    flagged = ens[(ens["ens_median_flag"] == 1) & (ens["evaluation_eligible"] == 1)]
    injected = 0
    if "injection_id" in flagged.columns:
        mask = flagged["injection_id"].notna() & \
            (flagged["injection_id"].astype(str).str.strip() != "")
        injected = int(mask.sum())
        flagged = flagged[~mask]
    # Station baseline for the event evidence panel: the median of the
    # station's own preceding two hours (24 five-minute readings), the same
    # causal definition the frozen 2-hour baseline window uses. Computed from
    # the real record, never invented, and labelled with its definition.
    baseline = (pd.to_numeric(obs["temperature_c"], errors="coerce")
                .rolling(24, min_periods=12).median().shift(1))
    deviation = (pd.to_numeric(obs["temperature_c"], errors="coerce")
                 - baseline)
    pos_by_stamp = {str(stamp): index for index, stamp in
                    enumerate(obs["timestamp"].astype(str))}
    rows = []
    for _, row in flagged.iterrows():
        score = _finite(row.get("ens_median"))
        availability = str(row.get("availability", ""))
        severity = ES.severity_for(score, threshold, True)
        conf = {"FULL_EVIDENCE": 1.0, "PARTIAL_EVIDENCE": 0.67,
                "LOW_CONTEXT": 0.33}.get(availability)
        pos = pos_by_stamp.get(str(row["_ts"]))
        rows.append({
            "timestamp": str(row["_ts"]),
            "variable": "temperature",
            "observed": _finite(row.get("temperature_c")),
            "temperature": _finite(row.get("temperature_c")),
            "humidity": _finite(row.get("relative_humidity_pct")),
            "pressure": _finite(row.get("pressure_hpa")),
            "baseline_median": (_finite(baseline.iloc[pos])
                                if pos is not None else None),
            "deviation": (_finite(deviation.iloc[pos])
                          if pos is not None else None),
            "baseline_basis": "median of the station's own preceding 2 hours "
                              "(24 five-minute readings)",
            "z": _finite(row.get("z_raw")),
            "score": score,
            "threshold": threshold,
            "severity": severity,
            "confidence": conf,
            "confidence_basis": f"evidence availability {availability} "
                                "(availability proxy, not a probability)",
            "pattern": "ENSEMBLE",
            "trigger": "ensemble",
            "detector": "Frozen ensemble (statistical + Isolation Forest + LSTM)",
            "data_quality": str(row.get("data_quality_status", "")),
            "reason": "Ensemble anomaly score at or above the frozen "
                      "station threshold (99th percentile of clean training).",
            "evidence": {
                "z_raw": _finite(row.get("z_raw")),
                "if_raw": _finite(row.get("if_raw")),
                "lstm_raw": _finite(row.get("lstm_raw")),
                "components_available": int(row.get("n_components_available", 0))
                if str(row.get("n_components_available", "")).strip() != "" else None,
            },
        })
    total = len(rows)
    coverage = (str(ens["_ts"].iloc[0]), str(ens["_ts"].iloc[-1]))
    return {
        "station_id": "DEL-01",
        "city": "Delhi",
        "pressure_basis": "station_level_hpa",
        "cadence_min": 5.0,
        "period": {"start": str(obs["timestamp_"].iloc[0]),
                   "end": str(obs["timestamp_"].iloc[-1])},
        "observations": int(len(obs)),
        "detector": {
            "available": True,
            "coverage": "FROZEN_ENSEMBLE",
            "detector_type": "Frozen ensemble (statistical + Isolation Forest + LSTM)",
            "threshold": threshold,
            "note": "Frozen ensemble verdicts exist for the held-out "
                    "evaluation window only; observations outside it carry "
                    "no detector verdict.",
            "coverage_window": {"start": coverage[0], "end": coverage[1]},
            "flags_total": total + injected,
            "flags_scored": total,
            "excluded_injection_rows": injected,
        },
        "series": series,
        "events": _evenly(rows, MAX_EVENTS),
    }


def _ghcnh_artifact(store: DataStore, entry: dict) -> dict:
    """Timeline for a GHCNh station (calibrated detector where present)."""
    from src.detection.station_statistical import load_detector
    from src.detection import freeze as FE

    backend_id = entry["backend_station_id"]
    frame = store.noaa_obs[backend_id]
    data = pd.DataFrame({
        "timestamp": pd.to_datetime(frame["timestamp_utc"], utc=True)
                       .dt.strftime("%Y-%m-%d %H:%M:%S"),
        "temperature_c": pd.to_numeric(frame["temperature_c"], errors="coerce"),
        "pressure_hpa": pd.to_numeric(frame["altimeter_setting_hpa"],
                                      errors="coerce"),
        "relative_humidity_pct": pd.to_numeric(
            frame["relative_humidity_pct"], errors="coerce"),
    })
    data["timestamp_"] = frame["timestamp_utc"].astype(str)
    series = _stride_frame(data, ["temperature_c", "relative_humidity_pct",
                                  "pressure_hpa"])
    detector = load_detector(store.root, backend_id)
    cadence = float(detector.cadence_min) if detector is not None else 30.0
    artifact = {
        "station_id": entry["frontend_station_id"],
        "city": entry["city"],
        "pressure_basis": "altimeter_qnh_hpa",
        "cadence_min": cadence,
        "period": {"start": str(data["timestamp_"].iloc[0]),
                   "end": str(data["timestamp_"].iloc[-1])},
        "observations": int(len(data)),
        "series": series,
        "events": [],
    }
    if detector is None:
        artifact["detector"] = {
            "available": False,
            "coverage": "UNAVAILABLE",
            "detector_type": None,
            "note": "No detector model covers this station: real historical "
                    "observations only, with no anomaly verdict.",
            "flags_total": 0,
        }
        return artifact

    from src.isolation_forest.evaluator import prepare_split
    from src.baseline.statistical_baseline import build_statistical_baseline

    features, quality = prepare_split(data, "delhi", cadence)
    baseline, _ = build_statistical_baseline(features, quality, "delhi",
                                             cadence_min=cadence)
    gap = (quality["communication_gap"].to_numpy()
           if "communication_gap" in quality.columns else None)
    if FE.applicable(cadence):
        run_rows, var_code = FE.scan_frame(data, gap_rows=gap)
    else:
        run_rows = np.zeros(len(data), dtype=int)
        var_code = np.zeros(len(data), dtype=np.int8)
    eligible = quality["ml_eligible"].to_numpy()
    stat_flag = pd.to_numeric(baseline["statistical_baseline_flag"],
                              errors="coerce").to_numpy() == 1.0
    freeze_rows = pd.Series(var_code).to_numpy() > 0
    mask = (stat_flag | freeze_rows) & eligible
    z_cols = ["temperature_zscore_baseline", "pressure_zscore_baseline",
              "humidity_zscore_baseline"]
    z_mat = np.stack([pd.to_numeric(baseline[c], errors="coerce")
                      .to_numpy(dtype=float) for c in z_cols], axis=1)
    positions = np.flatnonzero(mask)
    scored = [(int(pos), detector._score_row(data, features, quality, baseline,
                                             z_mat[pos], int(pos), run_rows,
                                             var_code, None))
              for pos in positions]
    # Station baseline for the evidence panel: the frozen feature layer's own
    # causal 2-hour median and deviation (the exact statistic the z-rule is
    # computed against), plus the per-variable |z| that fired.
    var_columns = {"temperature": "temperature", "pressure": "pressure",
                   "humidity": "humidity"}
    rows = []
    for pos, row in scored:
        finite = [(name, abs(value)) for name, value in
                  zip(var_columns, z_mat[pos]) if np.isfinite(value)]
        fired = max(finite, key=lambda pair: pair[1])[0] if finite else \
            var_columns.get(str(row.get("variable")) or "temperature",
                            "temperature")
        row["baseline_median"] = _finite(
            features[f"{fired}_prev_median_2h"].iloc[pos])
        row["deviation"] = _finite(
            features[f"{fired}_deviation_from_median_2h"].iloc[pos])
        row["baseline_variable"] = fired
        row["z_fired"] = _finite(z_mat[pos][list(var_columns).index(fired)])
        row["baseline_basis"] = \
            "frozen causal 2-hour rolling median over this station's own record"
        rows.append(row)
    rows.sort(key=lambda r: r.get("anomaly_score") or 0.0, reverse=True)
    total = len(rows)
    compact = []
    for row in _evenly(rows, MAX_EVENTS):
        # The parameter that actually fired: the frozen variable when the
        # freeze rule confirmed, otherwise the variable with the largest |z|.
        if row["freeze"].get("confirmed"):
            variable = row["freeze"].get("column") or "temperature"
        else:
            variable = row.get("baseline_variable") or "temperature"
        channels = {"temperature": row["temperature"],
                    "humidity": row["relative_humidity"],
                    "pressure": row["pressure"]}
        compact.append({
            "timestamp": row["timestamp"],
            "baseline_median": (row.get("baseline_median")
                                if variable == row.get("baseline_variable")
                                else None),
            "deviation": (row.get("deviation")
                          if variable == row.get("baseline_variable") else None),
            "baseline_variable": variable,
            "baseline_basis": row.get("baseline_basis"),
            "z": (row.get("z_fired")
                  if variable == row.get("baseline_variable") else None),
            "variable": variable,
            "observed": channels.get(variable),
            "temperature": row["temperature"],
            "humidity": row["relative_humidity"],
            "pressure": row["pressure"],
            "score": row["anomaly_score"],
            "severity": row["severity"],
            "confidence": row["confidence"],
            "confidence_basis": row["confidence_basis"],
            "pattern": row["pattern_estimate"],
            "trigger": row["trigger"],
            "detector": row["detector"],
            "threshold": detector.artifact.get("z_threshold"),
            "data_quality": row["data_quality"]["status"],
            "reason": row["primary_reason"],
            "contributing_factors": row["contributing_factors"],
            "evidence": {"z_max_abs": row["anomaly_score"],
                         "trigger": row["trigger"],
                         "frozen_variable": (row["freeze"].get("variable")
                                             if row["freeze"].get("confirmed")
                                             else None)},
        })
    artifact["events"] = compact
    artifact["detector"] = {
        "available": True,
        "coverage": "CALIBRATED_STATISTICAL",
        "detector_type": detector.artifact.get("detector_type"),
        "threshold": detector.artifact.get("z_threshold"),
        "iqr_factor": detector.artifact.get("iqr_factor"),
        "note": "Calibrated station-specific statistical detector (frozen "
                "z=3.0 / Tukey IQR=1.5 on this station's own causal rolling "
                "context). Flag rate on real 30-minute data is high; the "
                "frozen rule is unchanged.",
        "coverage_window": {"start": str(data["timestamp_"].iloc[0]),
                            "end": str(data["timestamp_"].iloc[-1])},
        "flags_total": total,
        "flags_scored": total,
        "flag_rate": round(total / max(1, len(data)), 6),
    }
    return artifact


def build(root: str | Path = ".", only: str | None = None) -> list[dict]:
    """Write timeline artifacts for every mapped station; return summaries."""
    store = DataStore.load(root)
    Path("data/showcase/timeline").mkdir(parents=True, exist_ok=True)
    summaries = []
    for entry in store.mapping:
        frontend = entry["frontend_station_id"]
        if only and frontend != only:
            continue
        started = time.time()
        if entry["source_dataset"] == "delhi_clean":
            artifact = _delhi_artifact(store)
        elif entry["source_dataset"] == "noaa_ghcnh":
            artifact = _ghcnh_artifact(store, entry)
        else:
            continue
        out = Path("data/showcase/timeline") / f"{frontend}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(artifact), encoding="utf-8")
        summary = {"station_id": frontend, "city": entry["city"],
                   "events": len(artifact["events"]),
                   "flags_total": artifact["detector"].get("flags_total"),
                   "detector_available": artifact["detector"]["available"],
                   "observations": artifact["observations"],
                   "seconds": round(time.time() - started, 2)}
        summaries.append(summary)
        logger.info("timeline built: %s", summary)
    return summaries


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else None
    for item in build(".", target):
        print(item)
