"""Deterministic event placement with eligibility, buffers, and rejection sampling.

Eligibility for a sensor-fault event starting at row s with duration d:
- all core variables present on [s, s+d)  (never touch natural missingness)
- all core variables present on history [s-H, s)  (later Phase 3 features)
- no timestamp discontinuity on [s-H, s+d)  (never cross structural gaps)
- expanded window [s-buf, s+d+buf) free of other events (buffer rule)

Humidity validity uses rejection sampling (flip direction once, else new
location). After MAX_PLACEMENT_ATTEMPTS the target count shortfall is
recorded as a skip — never forced.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.benchmark import config as C
from src.benchmark.injectors import humidity_valid


@dataclass
class PlannedEvent:
    injection_id: str
    dataset: str
    split: str
    fault_type: str
    target_variable: str  # '+'-joined for multivariate
    start_idx: int  # global row position in the processed dataset
    duration_rows: int
    params: dict = field(default_factory=dict)


def _prefix_sums(mask: np.ndarray) -> np.ndarray:
    return np.concatenate([[0], np.cumsum(mask.astype(int))])


def _window_sum(prefix: np.ndarray, a: int, b: int) -> int:
    return int(prefix[b] - prefix[a])


class SplitPlanner:
    """Plans non-overlapping events inside one chronological split."""

    def __init__(
        self,
        df: pd.DataFrame,
        split: dict,
        dataset: str,
        rng: np.random.Generator,
        id_counters: dict,
    ):
        self.df = df
        self.split = split
        self.dataset = dataset.lower()
        self.rng = rng
        self.id_counters = id_counters
        self.cadence = C.CADENCE_MIN[self.dataset]
        self.history = C.HISTORY_ROWS[self.dataset]
        self.buffer = C.buffer_rows(split["name"], self.dataset)
        self.group = C.split_group(split["name"])

        self.s0 = split["start_idx"]
        self.s1 = split["end_idx_excl"]
        n = len(df)
        present = df[list(C.CORE_VARS)].notna().all(axis=1).to_numpy()
        self.present_prefix = _prefix_sums(present)
        ts = pd.to_datetime(df["timestamp"])
        diffs_min = ts.diff().dt.total_seconds().to_numpy() / 60.0
        expected = float(self.cadence)
        broken = np.zeros(n, dtype=bool)
        broken[1:] = np.abs(diffs_min[1:] - expected) > 1e-6
        broken[0] = True  # no history before row 0
        self.break_prefix = _prefix_sums(~broken)
        self.blocked: list[tuple[int, int]] = []
        self.skips: list[dict] = []

    # -- helpers ---------------------------------------------------------
    def _new_id(self, fault_type: str) -> str:
        key = (self.dataset, self.split["name"], fault_type)
        self.id_counters[key] = self.id_counters.get(key, 0) + 1
        return f"{self.dataset.upper()}-{self.split['name']}-{fault_type}-{self.id_counters[key]:04d}"

    def _window_clean(self, a: int, b: int) -> bool:
        return _window_sum(self.present_prefix, a, b) == (b - a)

    def _history_clean(self, s: int) -> bool:
        a = s - self.history
        return a >= 0 and _window_sum(self.present_prefix, a, s) == self.history

    def _no_break(self, a: int, b: int) -> bool:
        # Every link into rows (a, b) must be exactly one cadence step.
        return _window_sum(self.break_prefix, a + 1, b) == (b - a - 1)

    def _overlaps_blocked(self, a: int, b: int) -> bool:
        ea, eb = a - self.buffer, b + self.buffer
        for x, y in self.blocked:
            if ea < y and x < eb:
                return True
        return False

    def _eligible(self, s: int, dur: int) -> bool:
        e = s + dur
        if s < self.s0 + self.history or e > self.s1:
            return False
        return (
            self._window_clean(s, e)
            and self._window_clean(s - self.history, s)
            and self._no_break(s - self.history, e)
            and not self._overlaps_blocked(s, e)
        )

    # -- duration samplers (rows) ----------------------------------------
    def _sample_duration(self, fault_type: str) -> int:
        if fault_type == "SPIKE":
            lo, hi = C.SPIKE_DURATION_READINGS
            return int(self.rng.integers(lo, hi + 1))
        if fault_type == "FROZEN":
            lo, hi = C.FROZEN_DURATION[self.group]
            return int(self.rng.integers(lo, hi + 1))
        if fault_type == "DRIFT":
            lo, hi = C.DRIFT_DURATION_HOURS[self.group]
            hours = float(self.rng.uniform(lo, hi))
            return max(2, int(round(hours * 60.0 / self.cadence)))
        if fault_type == "CROSS_VARIABLE":
            lo, hi = C.CROSS_DURATION[self.group]
            return int(self.rng.integers(lo, hi + 1))
        if fault_type == "SPIKE_PLUS_DRIFT":
            lo, hi = C.DRIFT_DURATION_HOURS["ood"]
            hours = float(self.rng.uniform(lo, hi))
            return max(2, int(round(hours * 60.0 / self.cadence)))
        if fault_type == "COMMUNICATION_GAP":
            lo, hi = C.GAP_DURATION_MIN[self.group]
            minutes = float(self.rng.uniform(lo, hi))
            return max(1, int(round(minutes / self.cadence)))
        raise ValueError(f"Unknown fault type {fault_type}")

    # -- per-type parameter samplers (kept minimal; RH validated by caller) ------
    def _directions(self) -> list[int]:
        first = int(self.rng.integers(0, 2) * 2 - 1)
        return [first, -first]

    # -- placement ---------------------------------------------------------
    def _try_place(self, fault_type: str, target: str, params_fn) -> PlannedEvent | None:
        span_lo, span_hi = self.s0 + self.history, self.s1
        for _ in range(C.MAX_PLACEMENT_ATTEMPTS):
            dur = self._sample_duration(fault_type)
            if span_hi - dur < span_lo:
                continue
            s = int(self.rng.integers(span_lo, span_hi - dur + 1))
            if not self._eligible(s, dur):
                continue
            params = params_fn(s, dur)
            if params is None:  # humidity-validity rejection
                continue
            event = PlannedEvent(
                injection_id=self._new_id(fault_type),
                dataset=self.dataset,
                split=self.split["name"],
                fault_type=fault_type,
                target_variable=target,
                start_idx=s,
                duration_rows=dur,
                params=params,
            )
            self.blocked.append((s, s + dur))
            return event
        self.skips.append({"split": self.split["name"], "fault_type": fault_type,
                           "target": target, "reason": "no_eligible_location_after_attempts",
                           "attempts": C.MAX_PLACEMENT_ATTEMPTS})
        return None

    # Params functions close over (target) and check RH validity.
    def _spike_params_fn(self, target: str):
        def fn(s: int, dur: int) -> dict | None:
            base = self.df[target].to_numpy(dtype=float)[s : s + dur]
            for direction in self._directions():
                amp_lo, amp_hi = C.SPIKE_AMPLITUDE[target][self.group]
                amp = float(self.rng.uniform(amp_lo, amp_hi))
                cand = base + direction * amp
                if target == "relative_humidity_pct" and not humidity_valid(cand):
                    continue
                return {"amplitude": amp, "direction": direction}
            return None
        return fn

    def _drift_params_fn(self, target: str):
        def fn(s: int, dur: int) -> dict | None:
            group = "ood" if self.split["name"] == "test_generalization" else "train_id"
            lo, hi = C.DRIFT_RATE_PER_HOUR[target][group]
            ts = pd.to_datetime(self.df["timestamp"].iloc[s : s + dur])
            elapsed_h = (ts - ts.iloc[0]).dt.total_seconds().to_numpy() / 3600.0
            base = self.df[target].to_numpy(dtype=float)[s : s + dur]
            for direction in self._directions():
                rate = float(self.rng.uniform(lo, hi))
                cand = base + rate * elapsed_h * direction
                if target == "relative_humidity_pct" and not humidity_valid(cand):
                    continue
                return {"drift_rate_per_hour": rate, "direction": direction}
            return None
        return fn

    def _cross_params_fn(self):
        def fn(s: int, dur: int) -> dict | None:
            ranges = C.CROSS_RATES_PER_READING[self.group]
            rates = {v: float(self.rng.uniform(*ranges[v])) for v in C.CORE_VARS}
            steps = np.arange(1, dur + 1, dtype=float)
            hum = self.df["relative_humidity_pct"].to_numpy(dtype=float)[s : s + dur]
            if not humidity_valid(hum + rates["relative_humidity_pct"] * steps):
                return None
            return {"rates_per_reading": rates}
        return fn

    def plan(self, targets: dict[str, int]) -> tuple[list[PlannedEvent], list[PlannedEvent]]:
        """Plan sensor-fault events and gap events. Returns (faults, gaps)."""
        faults: list[PlannedEvent] = []
        gaps: list[PlannedEvent] = []
        order = ["DRIFT", "SPIKE_PLUS_DRIFT", "FROZEN", "CROSS_VARIABLE", "SPIKE"]
        counters = {t: 0 for t in order}
        for fault_type in order:
            for _ in range(targets.get(fault_type, 0)):
                i = counters[fault_type]
                counters[fault_type] += 1
                if fault_type == "SPIKE_PLUS_DRIFT":
                    ev = self._plan_combo(i)
                elif fault_type == "DRIFT":
                    target = C.CORE_VARS[i % 3]
                    ev = self._try_place(fault_type, target, self._drift_params_fn(target))
                elif fault_type == "FROZEN":
                    target = C.CORE_VARS[i % 3]
                    dur_lo, dur_hi = C.FROZEN_DURATION[self.group]
                    ev = self._try_place(
                        fault_type, target,
                        lambda s, dur, _t=target: {"run_length": dur, "anchor_value": float(self.df[_t].iloc[s])},
                    )
                    # frozen needs no RH check: values already in range
                elif fault_type == "CROSS_VARIABLE":
                    ev = self._try_place(fault_type, "+".join(C.CORE_VARS), self._cross_params_fn())
                else:  # SPIKE
                    target = C.CORE_VARS[i % 3]
                    ev = self._try_place(fault_type, target, self._spike_params_fn(target))
                if ev is not None:
                    faults.append(ev)
        for _ in range(targets.get("COMMUNICATION_GAP", 0)):
            ev = self._try_place("COMMUNICATION_GAP", "all_core",
                                 lambda s, dur: {"removed_row_count": dur})
            if ev is not None:
                gaps.append(ev)
        return faults, gaps

    def _plan_combo(self, i: int) -> PlannedEvent | None:
        var_a = C.CORE_VARS[i % 3]
        var_b = C.CORE_VARS[(i + 1) % 3]
        group = "ood"
        lo, hi = C.DRIFT_RATE_PER_HOUR[var_a][group]
        s_lo, s_hi = C.SPIKE_AMPLITUDE[var_b][group]

        def fn(s: int, dur: int) -> dict | None:
            ts = pd.to_datetime(self.df["timestamp"].iloc[s : s + dur])
            elapsed_h = (ts - ts.iloc[0]).dt.total_seconds().to_numpy() / 3600.0
            for direction in self._directions():
                rate = float(self.rng.uniform(lo, hi))
                drift_vals = self.df[var_a].to_numpy(dtype=float)[s : s + dur] + rate * elapsed_h * direction
                if var_a == "relative_humidity_pct" and not humidity_valid(drift_vals):
                    continue
                spike_dur = int(self.rng.integers(C.SPIKE_DURATION_READINGS[0],
                                                      C.SPIKE_DURATION_READINGS[1] + 1))
                spike_offset = min(max(1, dur // 2), max(1, dur - spike_dur))
                spike_base = self.df[var_b].to_numpy(dtype=float)[s + spike_offset : s + spike_offset + spike_dur]
                placed_spike = None
                for sdir in self._directions():
                    samp = float(self.rng.uniform(s_lo, s_hi))
                    cand = spike_base + sdir * samp
                    vars_involved = {var_a, var_b}
                    ok = True
                    if "relative_humidity_pct" in vars_involved:
                        check = cand if var_b == "relative_humidity_pct" else drift_vals
                        if not humidity_valid(check):
                            ok = False
                    if ok:
                        placed_spike = {"amplitude": samp, "direction": sdir,
                                        "duration_rows": spike_dur, "offset_rows": spike_offset}
                        break
                if placed_spike is None:
                    continue
                return {"drift_rate_per_hour": rate, "direction": direction,
                        "drift_variable": var_a, "spike": placed_spike, "spike_variable": var_b}
            return None

        return self._try_place("SPIKE_PLUS_DRIFT", f"{var_a}+{var_b}", fn)
