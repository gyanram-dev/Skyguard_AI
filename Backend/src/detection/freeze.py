"""Fast freeze (stuck-signal) detector — deterministic, causal, measured.

The data-quality layer (``data_quality.freeze_checks``) requires **6 hours**
of identical readings before ``POSSIBLE_FREEZE``. Benchmark FROZEN fault
injections run only 1-5 hours, so they never reach that gate; consequently
the frozen ensemble and the root-cause classifier miss most frozen
episodes (root-cause FROZEN recall was 0.0 in every split).

This detector confirms a stuck signal from ``MIN_RUN_ROWS = 6``
*consecutive identical readings observed causally at the row itself*
(30 min at Delhi's 5-min cadence, 1 h at Jena's 10-min, 3 h at the 30-min
GHCNh stations), with one physical exclusion:

    relative humidity at the saturation bounds 0 % / 100 % is never a
    freeze confirmation — real clean data contains multi-hour saturated
    runs (longest observed: 50.5 h) that are not sensor evidence.

Measured on the frozen benchmark (reproduces via
``python -m src.detection.run_freeze_evaluation``; artifacts under
``reports/detection/``): adding the rule to the frozen ``ens_median``
verdict changes FROZEN event recall 5/30 -> 29/30 (Delhi generalisation,
0 added background flags) and 11/30 -> 30/30 (Jena generalisation,
+102 background rows, 168 -> 181 per 10k).

Severity and confidence are presentation/evidence-strength values,
documented here, never calibrated probabilities.

Applicability gate: the fast rule is validated at benchmark cadences
(5 and 10 min). The 30-min GHCNh stations report coarsely quantized
values (e.g. 14 unique temperatures in a 2,000-row sample), so short
identical runs are normal reporting resolution, not stuck sensors; for
cadences above ``FREEZE_MAX_CADENCE_MIN`` the detector reports itself
not applicable and the data-quality 6-hour candidate gate remains the
freeze evidence level (``summarise`` uses it for signal health).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Fast-rule applicability: benchmark cadences only (Delhi 5-min, Jena
# 10-min). Slower stations keep the DQ 6-hour gate (see module docstring).
FREEZE_MAX_CADENCE_MIN = 15.0

# Consecutive identical readings required to confirm a frozen signal.
# Chosen from the frozen benchmark sweep (thresholds 4/5/6 in
# reports/detection/freeze_evaluation.json): 6 is the largest threshold
# that still recovers every >=6-reading injection on both datasets, and it
# adds ZERO background flags on Delhi (its T/P/RH non-saturated flat runs
# never reach 6 rows in the clean test split).
MIN_RUN_ROWS = 6

# (raw column, display variable, is_relative_humidity)
VARIABLES: tuple[tuple[str, str, bool], ...] = (
    ("temperature_c", "temperature", False),
    ("pressure_hpa", "pressure", False),
    ("relative_humidity_pct", "relative humidity", True),
)

RH_SATURATION_BOUNDS = (0.0, 100.0)

CONFIDENCE_BASIS = (
    "run length versus the 6-reading freeze confirmation rule "
    "(run/(run+6)); an uncalibrated evidence-strength margin, not a "
    "probability")
SEVERITY_NOTE = ("Presentation bands on the confirmed run length; the DQ "
                 "6-hour rule marks the strongest band. Not detection "
                 "thresholds.")

_RUN_CODE = {column: index + 1 for index, (column, _, _) in enumerate(VARIABLES)}


def freeze_threshold_rows(cadence_min: float) -> int:
    """The data-quality 6-hour candidate threshold in rows (shared rule)."""
    from src.data_quality.freeze_checks import freeze_threshold_rows as rows

    return rows("delhi", float(cadence_min))


def applicable(cadence_min: float) -> bool:
    """True when the fast rule is inside its validated cadence range."""
    try:
        return float(cadence_min) <= FREEZE_MAX_CADENCE_MIN
    except (TypeError, ValueError):
        return False


def _gap_array(gap_rows, n: int) -> np.ndarray:
    if gap_rows is None:
        return np.zeros(n, dtype=bool)
    arr = np.asarray(gap_rows, dtype=bool)
    if len(arr) != n:
        return np.zeros(n, dtype=bool)
    return arr


def _confirmed_runs(values: np.ndarray, is_rh: bool, gap: np.ndarray,
                    min_run_rows: int = MIN_RUN_ROWS,
                    ) -> list[tuple[int, int, int]]:
    """Confirmed runs as (start_pos, end_pos, length), causal and gap-safe."""
    runs: list[tuple[int, int, int]] = []
    n = len(values)
    cur_len = 0
    cur_start = 0
    prev: float | None = None
    for i in range(n):
        v = values[i]
        if math.isnan(v) or gap[i]:
            if cur_len >= min_run_rows:
                runs.append((cur_start, i - 1, cur_len))
            cur_len = 0
            prev = None
            continue
        if cur_len and prev is not None and v == prev:
            cur_len += 1
        else:
            if cur_len >= min_run_rows:
                runs.append((cur_start, i - 1, cur_len))
            cur_len = 1
            cur_start = i
        prev = float(v)
    if cur_len >= min_run_rows:
        runs.append((cur_start, n - 1, cur_len))
    if is_rh:
        runs = [r for r in runs if values[r[0]] not in RH_SATURATION_BOUNDS]
    return runs


def scan_frame(frame: pd.DataFrame, gap_rows=None,
               min_run_rows: int = MIN_RUN_ROWS,
               ) -> tuple[np.ndarray, np.ndarray]:
    """Causal per-row freeze confirmation over a sensor frame.

    Returns ``(run_rows, var_code)`` aligned to ``frame`` rows.
    ``run_rows[i]`` is the longest confirmed identical-run length observed
    *at or before* row ``i`` (0 = not confirmed); ``var_code[i]`` is the
    variable that produced it (1..len(VARIABLES), 0 = none). A row is only
    ever flagged by evidence it has personally observed; NaN and
    communication-gap rows terminate runs.
    """
    n = len(frame)
    run_rows = np.zeros(n, dtype=int)
    var_code = np.zeros(n, dtype=np.int8)
    if n == 0:
        return run_rows, var_code
    gap = _gap_array(gap_rows, n)
    for column, _, is_rh in VARIABLES:
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        code = _RUN_CODE[column]
        cur_len = 0
        prev: float | None = None
        for i in range(n):
            v = values[i]
            if math.isnan(v) or gap[i]:
                cur_len = 0
                prev = None
                continue
            if cur_len and prev is not None and v == prev:
                cur_len += 1
            else:
                cur_len = 1
            prev = float(v)
            if cur_len >= min_run_rows and not (
                    is_rh and v in RH_SATURATION_BOUNDS):
                if cur_len > run_rows[i]:
                    run_rows[i] = cur_len
                    var_code[i] = code
    return run_rows, var_code


def confidence_for(run_rows: int) -> float | None:
    """Evidence-strength margin from the confirmed run length (not a maybe)."""
    if run_rows < MIN_RUN_ROWS:
        return None
    return round(float(run_rows) / (float(run_rows) + MIN_RUN_ROWS), 4)


def severity_for(run_rows: int, cadence_min: float) -> str | None:
    """Presentation band from the confirmed run length (documented, not tuned)."""
    if run_rows < MIN_RUN_ROWS:
        return None
    candidate_6h = freeze_threshold_rows(cadence_min)
    if run_rows >= candidate_6h:
        return "HIGH"
    if run_rows >= 2 * MIN_RUN_ROWS:
        return "MEDIUM"
    return "LOW"


def row_evidence(run_rows: np.ndarray, var_code: np.ndarray, pos: int,
                 cadence_min: float) -> dict:
    """Freeze evidence for one row (empty confirmation when not frozen)."""
    if not applicable(cadence_min):
        return {"confirmed": False, "applicable": False,
                "min_run_rows": MIN_RUN_ROWS,
                "reason": ("fast freeze rule validated at 5-10 min cadence; "
                           "the 6-hour data-quality gate applies at this "
                           "cadence")}
    length = int(run_rows[pos]) if 0 <= pos < len(run_rows) else 0
    if length < MIN_RUN_ROWS:
        return {"confirmed": False, "applicable": True,
                "min_run_rows": MIN_RUN_ROWS}
    column, display, _ = VARIABLES[int(var_code[pos]) - 1]
    return {
        "confirmed": True,
        "applicable": True,
        "column": column,
        "variable": display,
        "run_rows": length,
        "run_hours": round(length * float(cadence_min) / 60.0, 2),
        "severity": severity_for(length, cadence_min),
        "confidence": confidence_for(length),
        "confidence_basis": CONFIDENCE_BASIS,
        "severity_note": SEVERITY_NOTE,
    }


def reason_text(evidence: dict, cadence_min: float) -> str:
    """Plain-language freeze reason with measured values, or empty."""
    if not evidence.get("confirmed"):
        return ""
    return (
        f"FROZEN: {evidence['variable']} unchanged for "
        f"{evidence['run_hours']:.1f} h ({evidence['run_rows']} consecutive "
        f"identical readings at {float(cadence_min):g}-min cadence); "
        "deterministic stuck-signal rule, not a trained-model diagnosis.")


def summarise(frame: pd.DataFrame, cadence_min: float,
              gap_rows=None) -> dict:
    """Longitudinal signal-health summary for one station's loaded history.

    Uses the fast rule inside its validated cadence range; at slower
    cadences (coarsely quantized reports) it reports the data-quality
    6-hour candidate gate instead of pretending the fast rule applies.
    Descriptive facts plus a documented watch level; explicitly not a
    failure prediction, RUL, or degradation model. Timestamps are read
    from ``frame["timestamp"]``/``frame["timestamp_utc"]`` when present.
    """
    n = len(frame)
    fast = applicable(cadence_min)
    min_rows = MIN_RUN_ROWS if fast else freeze_threshold_rows(cadence_min)
    out: dict = {
        "state": "INSUFFICIENT_HISTORY",
        "freeze_runs": 0,
        "affected_variables": [],
        "longest_run_hours": None,
        "last_freeze_at": None,
        "rows_scanned": int(n),
        "min_run_rows": int(min_rows),
        "fast_rule_applicable": fast,
        "rule": ("fast_flatline_rule" if fast else "dq_6h_candidate_gate"),
        "rules": ("confirmed = >=%d consecutive identical readings, causal; "
                  "RH at 0/100 excluded; 6-hour DQ level = strongest band"
                  % min_rows),
        "note": ("Descriptive indicator from recorded history; not a "
                 "failure prediction, remaining-useful-life estimate, or "
                 "calibrated probability."),
    }
    if n < 96:
        return out
    gap = _gap_array(gap_rows, n)
    stamps = None
    for key in ("timestamp", "timestamp_utc"):
        if key in frame.columns:
            stamps = frame[key].astype(str).to_numpy()
            break
    runs_by_var: dict[str, list[tuple[int, int, int]]] = {}
    longest = 0
    affected: list[str] = []
    last_ts: str | None = None
    total = 0
    for column, display, is_rh in VARIABLES:
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        runs = _confirmed_runs(values, is_rh, gap, min_rows)
        if not runs:
            continue
        runs_by_var[display] = runs
        total += len(runs)
        affected.append(display)
        for start, end, length in runs:
            if length > longest:
                longest = length
            if stamps is not None:
                stamp = str(stamps[end])
                if last_ts is None or stamp > last_ts:
                    last_ts = stamp
    if total == 0:
        out["state"] = "NO_FLATLINE_EVIDENCE"
        return out
    out["freeze_runs"] = int(total)
    out["affected_variables"] = affected
    out["longest_run_hours"] = round(longest * float(cadence_min) / 60.0, 2)
    out["last_freeze_at"] = last_ts
    if longest >= freeze_threshold_rows(cadence_min):
        out["state"] = "PROLONGED_FLATLINE"
    elif total >= 2:
        out["state"] = "REPEATED_FLATLINES"
    else:
        out["state"] = "ISOLATED_FLATLINE"
    return out
