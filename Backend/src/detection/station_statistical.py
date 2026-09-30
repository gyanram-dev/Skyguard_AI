"""Station-specific statistical detectors for GHCNh Indian stations.

Thin wrapper over the exact frozen machinery used by the upload path
(prepare_split with cadence override + build_statistical_baseline with
cadence override + causal DQ taxonomy + multivariate features +
heuristic pattern estimates). No new thresholds: z=3.0 / IQR=1.5 are the
frozen conventional rules; "station-specific calibration" means the
clean-train reference distribution recorded per station (used for
severity scaling and reporting), never Delhi thresholds.

Severity bands are presentation-only (documented here, not detection
thresholds). Confidence is derived from this detector's own statistic
(see :func:`confidence_for`) and is explicitly NOT a calibrated
probability — never a fabricated number.

Known limitation (reported, not hidden): at 30-minute GHCNh cadence the
frozen 2-hour causal IQR window spans only 4 rows, so a zero-width IQR
turns any deviation into an IQR flag. Background flag rates on real
Indian stations are therefore high; the frozen rule is left unchanged.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.api.services.upload_analysis import _estimate_pattern
from src.baseline.iqr_baseline import IQR_FACTOR
from src.detection import freeze as FE
from src.detection import registry as REG
from src.baseline.statistical_baseline import build_statistical_baseline
from src.baseline.zscore_baseline import Z_THRESHOLD
from src.isolation_forest.evaluator import prepare_split
from src.spatial import decision as SD

logger = logging.getLogger("skyguard.station_detector")

DETECTOR_TYPE = "Statistical Baseline"
DETECTOR_METHOD = "statistical"

# Presentation-only severity bands on max|z| (detection itself is the
# frozen |z|>3 / IQR rule). Documented, not tuned.
SEVERITY_BANDS = (
    (20.0, "CRITICAL"),
    (10.0, "HIGH"),
    (6.0, "MEDIUM"),
    (3.0, "LOW"),
)

CONFIDENCE_BASIS = (
    "z/(z+z_threshold) over this detector's own max|z| margin past the "
    "frozen z=3.0 rule; an uncalibrated evidence-strength score, not a "
    "probability")
CONFIDENCE_NOTE = ("Statistical-only detector; confidence is an "
                   "evidence-strength margin from the frozen rule, never a "
                   "calibrated probability and never fabricated.")


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


_SEVERITY_RANK = {"NORMAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3,
                 "CRITICAL": 4}


def _severity_rank(value: str | None) -> int:
    """Rank helper for combining statistical and freeze severity bands."""
    return _SEVERITY_RANK.get(str(value).upper(), -1)


def severity_for(zmax: float | None, flagged: bool) -> str:
    """Human-readable severity (presentation band, not a threshold).

    NORMAL only when nothing was detected. A detected row always reports an
    anomaly band; when no magnitude is computable the weakest band is used
    instead of claiming NORMAL for a flagged observation.
    """
    if not flagged:
        return "NORMAL"
    if zmax is None:
        return "LOW"
    for edge, label in SEVERITY_BANDS:
        if zmax >= edge:
            return label
    return "LOW"


def confidence_for(zmax: float | None, flagged: bool) -> float | None:
    """Evidence strength from the detector's own statistic (not a probability).

    Monotone, bounded, and fully determined by the frozen decision rule:
    ``z / (z + Z_THRESHOLD)`` where ``z`` is the detector's max|z|. At the
    frozen threshold this is 0.5 and it rises with the margin. Returns None
    when nothing was detected (no verdict to be confident about) or when no
    z magnitude was computable (IQR-only flag) — a number is never invented.
    """
    if not flagged or zmax is None or zmax <= 0.0:
        return None
    return round(float(zmax) / (float(zmax) + Z_THRESHOLD), 4)


def load_detector(root: str | Path, backend_id: str,
                  ) -> "StationStatisticalDetector | None":
    """Calibrated detector for a backend station ID, or None when absent.

    Single loader for every caller (replay, demo, tests): registry lookup ->
    artifact read -> detector. A missing registry or artifact means "no
    statistical coverage", never an exception.
    """
    try:
        entry = REG.get(root, backend_id)
        if entry is None:
            return None
        path = REG.artifact_path(root, entry)
        if not path.is_file():
            logger.warning("registry entry without artifact: %s", path)
            return None
        return StationStatisticalDetector(
            json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001 - absence is not an error
        logger.warning("detector load failed for %s: %s", backend_id, exc)
        return None


class StationStatisticalDetector:
    """Calibrated statistical detector bound to one GHCNh station."""

    def __init__(self, artifact: dict) -> None:
        self.artifact = artifact
        self.station_id: str = artifact["station_id"]
        self.backend_id: str = artifact["backend_station_id"]
        self.cadence_min: float = float(artifact["cadence_min"])

    @classmethod
    def calibrate(cls, station_cfg: dict, frame: pd.DataFrame,
                  train_start: str, train_end: str) -> "StationStatisticalDetector":
        """Record station-specific calibration from a clean history window.

        No fitting in the ML sense: the rolling z/IQR rules are
        self-calibrating per row. Calibration persists the operating
        context (cadence, pressure semantics, RH provenance, clean-train
        reference distribution, DQ profile) so replay reuses the exact
        same detector. Raises loudly on insufficient clean data.
        """
        mask = (frame["timestamp"].astype(str) >= train_start) & \
               (frame["timestamp"].astype(str) <= train_end)
        train = frame.loc[mask].reset_index(drop=True)
        if len(train) < 48:
            raise ValueError(
                f"{station_cfg['station_id']}: only {len(train)} clean rows; "
                "need >= 48 for calibration.")
        reference = {}
        for col in ("temperature_c", "pressure_hpa", "relative_humidity_pct"):
            vals = pd.to_numeric(train[col], errors="coerce").dropna().to_numpy(dtype=float)
            if len(vals) == 0:
                raise ValueError(
                    f"{station_cfg['station_id']}: no valid {col} in train window.")
            median = float(np.median(vals))
            mad = float(np.median(np.abs(vals - median)))
            reference[col] = {"median": median, "mad": mad, "n": int(len(vals)),
                              "min": float(vals.min()), "max": float(vals.max())}
        quality_counts: dict[str, int] = {}
        try:
            _, quality = prepare_split(train, "delhi", float(station_cfg["cadence_min"]))
            quality_counts = {str(k): int(v) for k, v in
                              quality["quality_status"].value_counts().items()}
        except Exception as exc:  # noqa: BLE001 - recorded, calibration continues
            logger.warning("%s: DQ profile failed: %s", station_cfg["station_id"], exc)
        artifact = {
            "detector_type": DETECTOR_TYPE,
            "detector_method": DETECTOR_METHOD,
            "station_id": station_cfg["station_id"],
            "backend_station_id": station_cfg["backend_station_id"],
            "city": station_cfg["city"],
            "cadence_min": float(station_cfg["cadence_min"]),
            "pressure_semantics": station_cfg["pressure_semantics"],
            "pressure_column": station_cfg["pressure_column"],
            "rh_provenance": station_cfg["rh_provenance"],
            "data_mode": "HISTORICAL",
            "train_start": train_start,
            "train_end": train_end,
            "train_rows": int(len(train)),
            "z_threshold": Z_THRESHOLD,
            "iqr_factor": IQR_FACTOR,
            "reference_distribution": reference,
            "dq_profile": quality_counts,
            "rules": "frozen z=3.0 / Tukey IQR=1.5 on causal station-specific "
                     "rolling context; thresholds unchanged from Delhi baseline",
        }
        logger.info("%s: calibrated on %d rows", artifact["station_id"], len(train))
        return cls(artifact)

    def score_frame(self, frame: pd.DataFrame,
                    neighbor_rows: list[dict] | None = None) -> list[dict]:
        """Score every row -> unified detection results (chronological).

        neighbor_rows[pos] optionally carries {"temperature": {id: value},
        "humidity": {id: value}} for the shared spatial policy.
        """
        features, quality = prepare_split(frame, "delhi", self.cadence_min)
        baseline, _ = build_statistical_baseline(features, quality, "delhi",
                                                 cadence_min=self.cadence_min)
        gap_arr = (quality["communication_gap"].to_numpy()
                   if "communication_gap" in quality.columns else None)
        if FE.applicable(self.cadence_min):
            freeze_run_rows, freeze_var_code = FE.scan_frame(frame, gap_rows=gap_arr)
        else:
            # Coarsely quantized cadence: repeated values are reporting
            # resolution; the DQ 6-hour gate remains the evidence level.
            freeze_run_rows = np.zeros(len(frame), dtype=int)
            freeze_var_code = np.zeros(len(frame), dtype=np.int8)
        z_cols = ["temperature_zscore_baseline", "pressure_zscore_baseline",
                  "humidity_zscore_baseline"]
        z_mat = np.stack([pd.to_numeric(baseline[c], errors="coerce").to_numpy(dtype=float)
                          for c in z_cols], axis=1)
        results = []
        for pos in range(len(frame)):
            neighbors = neighbor_rows[pos] if neighbor_rows else None
            results.append(self._score_row(frame, features, quality, baseline,
                                           z_mat[pos], pos, freeze_run_rows,
                                           freeze_var_code, neighbors))
        return results

    def _score_row(self, frame, features, quality, baseline, z_row, pos,
                   freeze_run_rows, freeze_var_code, neighbors) -> dict:
        dq_status = str(quality["quality_status"].iloc[pos])
        eligible = bool(int(quality["ml_eligible"].iloc[pos]))
        flag = baseline["statistical_baseline_flag"].iloc[pos]
        flagged_stat = bool(eligible and pd.notna(flag) and float(flag) == 1.0)
        freeze = FE.row_evidence(freeze_run_rows, freeze_var_code, pos,
                                 self.cadence_min)
        freeze_confirmed = bool(eligible and freeze["confirmed"])
        flagged = flagged_stat or freeze_confirmed
        finite_z = z_row[np.isfinite(z_row)]
        zmax = float(np.nanmax(np.abs(finite_z))) if len(finite_z) else None
        feat = features.iloc[pos]
        freeze_flag = "possible_freeze" in str(quality["quality_reason"].iloc[pos])
        estimate, reason = _estimate_pattern(feat, freeze_flag)
        temp = _num(frame["temperature_c"].iloc[pos])
        pres = _num(frame["pressure_hpa"].iloc[pos])
        hum = _num(frame["relative_humidity_pct"].iloc[pos])
        multi = _num(feat.get("multivariate_max_abs_robust_deviation_2h"))
        contributing = []
        reason_text = str(baseline["statistical_baseline_reason"].iloc[pos])
        if flagged_stat:
            contributing.append(f"statistical flag ({reason_text})")
            contributing.append(f"{estimate} pattern: {reason}")
            if multi is not None and multi >= 3.0:
                contributing.append(
                    f"multivariate inconsistency ({multi:.2f} robust deviations)")
            if freeze_flag:
                contributing.append("frozen-sensor evidence in data quality")
        freeze_text = ""
        if freeze_confirmed:
            freeze_text = FE.reason_text(freeze, self.cadence_min)
            contributing.insert(
                0, f"frozen-sensor confirmation ({freeze['variable']} "
                   f"unchanged for {freeze['run_hours']:.1f} h)")
        spatial = self._spatial_context(temp, hum, pos, neighbors, flagged)
        stat_severity = severity_for(zmax, flagged_stat)
        stat_confidence = confidence_for(zmax, flagged_stat)
        if freeze_confirmed and not flagged_stat:
            severity = freeze["severity"]
            confidence = freeze["confidence"]
            confidence_basis = freeze["confidence_basis"]
        elif freeze_confirmed and flagged_stat:
            severity = max((stat_severity, freeze["severity"]), key=_severity_rank)
            confidence = max(stat_confidence or 0.0,
                             freeze["confidence"] or 0.0) or None
            confidence_basis = ("max of statistical z-margin and freeze-run "
                                "margin; neither is a probability")
        else:
            severity = stat_severity
            confidence = stat_confidence
            confidence_basis = (CONFIDENCE_BASIS if confidence is not None
                                else "no detector magnitude available")
        if freeze_confirmed:
            primary = freeze_text
            if flagged_stat:
                primary += f" Statistical evidence also flagged ({reason_text})."
        else:
            primary = "within station baseline bounds" if not flagged else (
                f"{estimate}: {reason}; max|z|="
                f"{zmax:.2f}" if zmax is not None else f"{estimate}: {reason}")
        trigger = ("statistical+freeze" if flagged_stat and freeze_confirmed
                   else "freeze" if freeze_confirmed
                   else "statistical" if flagged_stat else None)
        return {
            "station_id": self.station_id,
            "timestamp": str(frame["timestamp"].iloc[pos]),
            "temperature": temp,
            "relative_humidity": hum,
            "pressure": pres,
            "anomaly": bool(flagged),
            "anomaly_score": round(zmax, 4) if zmax is not None else None,
            "severity": severity,
            "confidence": confidence,
            "confidence_basis": confidence_basis,
            "confidence_note": CONFIDENCE_NOTE,
            "detector": DETECTOR_TYPE,
            "detector_method": DETECTOR_METHOD,
            "trigger": trigger,
            "freeze": freeze,
            "primary_reason": primary,
            "contributing_factors": contributing,
            "data_quality": {"status": dq_status, "ml_eligible": eligible,
                             "reason": str(quality["quality_reason"].iloc[pos])},
            "pattern_estimate": "FROZEN" if freeze_confirmed else estimate,
            "spatial_context": spatial,
        }

    def _spatial_context(self, temp, hum, pos, neighbors,
                           flagged: bool) -> dict:
        """Shared Go-2 spatial policy over supplied neighbor values."""
        base = SD.BASE_ANOMALOUS if flagged else SD.BASE_NORMAL
        temp_vals = (neighbors or {}).get("temperature") or {}
        rh_vals = (neighbors or {}).get("humidity") or {}
        if not temp_vals:
            empty = SD.variable_evidence(None, {}, 0)
            decision = SD.decide_context(base, empty)
            decision["description"] = SD.describe(decision)
            return {"available": False, "decision": decision,
                    "reason": "No compatible neighbor context for this row."}
        expected = len(temp_vals)
        temp_ev = SD.variable_evidence(temp, temp_vals, expected)
        rh_ev = SD.variable_evidence(hum, rh_vals, expected) \
            if hum is not None else SD.variable_evidence(None, {}, expected)
        decision = SD.decide_context(base, temp_ev, rh_ev)
        decision["description"] = SD.describe(decision)
        return {"available": True, "decision": decision,
                "temperature": temp_ev, "humidity": rh_ev,
                "expected_neighbors": expected}

    def describe(self) -> dict:
        """Registry entry: the declared serving contract for this station.

        ``cadence`` is minutes between observations. Every new station stays
        PARTIAL: T/RH are reported and the pressure channel is QNH altimeter
        (never station pressure), so FULL_TPR is not proven by the audit.
        """
        art = self.artifact
        return {"station_id": art["station_id"], "city": art["city"],
                "capability": "PARTIAL", "detector_available": True,
                "detector_type": art["detector_type"],
                "detector_method": art["detector_method"],
                "cadence": art["cadence_min"],
                "pressure_semantics": art["pressure_semantics"],
                "rh_provenance": art["rh_provenance"],
                "data_mode": art["data_mode"]}
