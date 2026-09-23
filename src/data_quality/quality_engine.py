"""Core quality engine: status priority, ML eligibility, streaming interface.

Quality states:
    PASS, DATA_AVAILABILITY_EVENT, COMMUNICATION_GAP,
    DATA_INTEGRITY_FAULT, POSSIBLE_FREEZE, PHYSICAL_SANITY_FAULT

Deterministic priority (highest first):
    1. DATA_INTEGRITY_FAULT
    2. COMMUNICATION_GAP
    3. DATA_AVAILABILITY_EVENT
    4. PHYSICAL_SANITY_FAULT
    5. POSSIBLE_FREEZE
    6. PASS

Levels 2 and 3 together are the "data availability" group: the reading
did not arrive correctly as usable ML input, but nothing is claimed
about the sensor itself. Individual flags are always preserved.

ML eligibility:
    false: integrity fault, gap, availability event, sanity fault
    true:  PASS, unusual-but-possible values, POSSIBLE_FREEZE
"""

from __future__ import annotations

from dataclasses import dataclass, field

PASS = "PASS"
DATA_AVAILABILITY_EVENT = "DATA_AVAILABILITY_EVENT"
COMMUNICATION_GAP = "COMMUNICATION_GAP"
DATA_INTEGRITY_FAULT = "DATA_INTEGRITY_FAULT"
POSSIBLE_FREEZE = "POSSIBLE_FREEZE"
PHYSICAL_SANITY_FAULT = "PHYSICAL_SANITY_FAULT"

QUALITY_STATES = (
    PASS,
    DATA_AVAILABILITY_EVENT,
    COMMUNICATION_GAP,
    DATA_INTEGRITY_FAULT,
    POSSIBLE_FREEZE,
    PHYSICAL_SANITY_FAULT,
)

FREEZE_DURATION_HOURS = 6

from src.data_quality.freeze_checks import freeze_threshold_rows  # noqa: E402
from src.data_quality.physical_checks import is_physical_sanity_fault  # noqa: E402
from src.data_quality.timeline_checks import (  # noqa: E402
    EXPECTED_INTERVAL_MIN,
    gap_threshold_minutes,
    parse_timestamp_strict,
)

FREEZE_THRESHOLD_ROWS = {
    "jena": freeze_threshold_rows("jena"),
    "delhi": freeze_threshold_rows("delhi"),
}


def _is_missing_value(value: object) -> bool:
    if value is None:
        return True
    try:
        import math

        import pandas as pd

        if pd.isna(value):
            return True
        return isinstance(value, float) and math.isnan(value)
    except Exception:
        return False


def classify_quality_status(
    timestamp_integrity_fault: bool,
    communication_gap: bool,
    data_availability_event: bool,
    physical_sanity_fault: bool,
    possible_freeze: bool,
) -> tuple[str, bool]:
    """Apply deterministic priority. Return (quality_status, ml_eligible)."""
    if timestamp_integrity_fault:
        return DATA_INTEGRITY_FAULT, False
    if communication_gap:
        return COMMUNICATION_GAP, False
    if data_availability_event:
        return DATA_AVAILABILITY_EVENT, False
    if physical_sanity_fault:
        return PHYSICAL_SANITY_FAULT, False
    if possible_freeze:
        return POSSIBLE_FREEZE, True
    return PASS, True


@dataclass
class StreamingQualityEngine:
    """Lightweight per-reading quality gate for future real-time use.

    Keeps only minimum state: previous timestamp, previous values,
    consecutive identical-value counters, and a set of seen timestamps.
    No whole-dataset Pandas operations on the hot path.

    Usage:
        engine = StreamingQualityEngine("delhi")
        result = engine.check({"timestamp": ..., "temperature_c": ...,
                               "pressure_hpa": ..., "relative_humidity_pct": ...})
    """

    dataset: str
    _prev_timestamp: object = field(default=None, init=False, repr=False)
    _prev_values: dict = field(default_factory=dict, init=False, repr=False)
    _freeze_counters: dict = field(default_factory=dict, init=False, repr=False)
    _seen_timestamps: set = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        key = self.dataset.lower()
        if key not in EXPECTED_INTERVAL_MIN:
            raise ValueError(f"Unknown dataset '{self.dataset}'. Must be 'jena' or 'delhi'.")
        self.dataset = key
        self._gap_threshold = gap_threshold_minutes(key)
        self._freeze_threshold = freeze_threshold_rows(key)
        self._freeze_counters = {"temperature_c": 0, "pressure_hpa": 0, "relative_humidity_pct": 0}

    def check(self, reading: dict) -> dict:
        """Classify a single incoming observation. Deterministic."""
        ts_raw = reading.get("timestamp")
        ts = parse_timestamp_strict(ts_raw)

        timestamp_valid = ts is not None
        ts_key = str(ts) if ts is not None else None
        timestamp_duplicate = bool(timestamp_valid and ts_key in self._seen_timestamps)
        timestamp_out_of_order = bool(
            timestamp_valid and self._prev_timestamp is not None and ts < self._prev_timestamp
        )
        integrity_fault = (
            (not timestamp_valid) or timestamp_duplicate or timestamp_out_of_order
        )

        # Cadence / communication gap from previous accepted timestamp.
        elapsed: float | None = None
        communication_gap = False
        gap_duration = 0.0
        if timestamp_valid and self._prev_timestamp is not None and not integrity_fault:
            elapsed = (ts - self._prev_timestamp).total_seconds() / 60.0
            if elapsed > self._gap_threshold:
                communication_gap = True
                gap_duration = float(elapsed)

        temp = reading.get("temperature_c")
        pres = reading.get("pressure_hpa")
        rh = reading.get("relative_humidity_pct")

        t_miss = _is_missing_value(temp)
        h_miss = _is_missing_value(rh)
        p_miss = _is_missing_value(pres)
        any_missing = t_miss or h_miss or p_miss
        missing_count = int(t_miss) + int(h_miss) + int(p_miss)

        sanity_fault, sanity_reason = is_physical_sanity_fault(temp, pres, rh)

        # Consecutive identical-value counters (NaN or gap resets).
        freeze_flags: dict[str, bool] = {}
        for col, val in (
            ("temperature_c", temp),
            ("pressure_hpa", pres),
            ("relative_humidity_pct", rh),
        ):
            if _is_missing_value(val) or communication_gap or integrity_fault:
                if _is_missing_value(val) or communication_gap:
                    self._freeze_counters[col] = 0
                freeze_flags[col] = False
                continue
            prev = self._prev_values.get(col, None)
            if prev is not None and not _is_missing_value(prev) and float(val) == float(prev):  # type: ignore[arg-type]
                self._freeze_counters[col] += 1
            else:
                self._freeze_counters[col] = 1
            freeze_flags[col] = self._freeze_counters[col] >= self._freeze_threshold

        possible_freeze = any(freeze_flags.values())

        status, ml_eligible = classify_quality_status(
            timestamp_integrity_fault=integrity_fault,
            communication_gap=communication_gap,
            data_availability_event=any_missing,
            physical_sanity_fault=sanity_fault,
            possible_freeze=possible_freeze,
        )

        reasons: list[str] = []
        if not timestamp_valid:
            reasons.append("timestamp_invalid_or_missing")
        if timestamp_duplicate:
            reasons.append("timestamp_duplicate")
        if timestamp_out_of_order:
            reasons.append("timestamp_out_of_order")
        if communication_gap:
            reasons.append(f"communication_gap_{gap_duration:.1f}min")
        if any_missing:
            reasons.append(f"missing_core_count_{missing_count}")
        if sanity_fault:
            reasons.append(sanity_reason)
        if possible_freeze:
            frozen_vars = sorted(k for k, v in freeze_flags.items() if v)
            reasons.append("possible_freeze_" + "+".join(frozen_vars))
        if not reasons:
            reasons.append("all_checks_passed")

        # Advance state only on structurally usable timestamps.
        if timestamp_valid and not timestamp_duplicate and not timestamp_out_of_order:
            self._seen_timestamps.add(ts_key)  # type: ignore[arg-type]
            self._prev_timestamp = ts
            self._prev_values = {
                "temperature_c": temp,
                "pressure_hpa": pres,
                "relative_humidity_pct": rh,
            }

        return {
            "timestamp": ts_raw,
            "timestamp_valid": int(timestamp_valid),
            "timestamp_duplicate": int(timestamp_duplicate),
            "timestamp_out_of_order": int(timestamp_out_of_order),
            "elapsed_minutes_since_prev": elapsed,
            "communication_gap": int(communication_gap),
            "gap_duration_minutes": float(gap_duration),
            "temperature_missing": int(t_miss),
            "humidity_missing": int(h_miss),
            "pressure_missing": int(p_miss),
            "any_core_missing": int(any_missing),
            "missing_core_count": int(missing_count),
            "temperature_possible_freeze": int(freeze_flags["temperature_c"]),
            "pressure_possible_freeze": int(freeze_flags["pressure_hpa"]),
            "humidity_possible_freeze": int(freeze_flags["relative_humidity_pct"]),
            "physical_sanity_fault": int(sanity_fault),
            "quality_status": status,
            "quality_reason": ";".join(reasons),
            "ml_eligible": int(ml_eligible),
        }
