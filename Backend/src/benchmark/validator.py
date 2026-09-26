"""Benchmark validation: ranges, disjointness, overlap, alignment, integrity."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.benchmark import config as C


def _in(lo: float, v: float, hi: float, eps: float = 1e-9) -> bool:
    return (lo - eps) <= v <= (hi + eps)


def validate_events(events: list, gaps: list, splits: list[dict], dataset: str) -> dict:
    """Validate planned events. Return {'all_passed': bool, 'checks': {...}}."""
    checks: dict[str, bool] = {}
    by_split = {s["name"]: s for s in splits}
    faults = [e for e in events if e.fault_type != "COMMUNICATION_GAP"]
    all_events = list(events) + list(gaps)

    # 1. Parameter ranges per split group.
    range_ok = True
    for e in faults:
        g = C.split_group(e.split)
        p = e.params
        if e.fault_type == "SPIKE":
            lo, hi = C.SPIKE_AMPLITUDE[e.target_variable][g]
            range_ok &= _in(lo, abs(float(p["amplitude"])), hi)
            range_ok &= p["direction"] in (1, -1)
            dlo, dhi = C.SPIKE_DURATION_READINGS
            range_ok &= dlo <= e.duration_rows <= dhi
        elif e.fault_type == "FROZEN":
            dlo, dhi = C.FROZEN_DURATION[g]
            range_ok &= dlo <= e.duration_rows <= dhi
        elif e.fault_type == "DRIFT":
            lo, hi = C.DRIFT_RATE_PER_HOUR[e.target_variable][g]
            range_ok &= _in(lo, abs(float(p["drift_rate_per_hour"])), hi)
        elif e.fault_type == "CROSS_VARIABLE":
            dlo, dhi = C.CROSS_DURATION[g]
            range_ok &= dlo <= e.duration_rows <= dhi
        elif e.fault_type == "SPIKE_PLUS_DRIFT":
            lo, hi = C.DRIFT_RATE_PER_HOUR[p["drift_variable"]]["ood"]
            range_ok &= _in(lo, abs(float(p["drift_rate_per_hour"])), hi)
            slo, shi = C.SPIKE_AMPLITUDE[p["spike_variable"]]["ood"]
            range_ok &= _in(slo, abs(float(p["spike"]["amplitude"])), shi)
    checks["parameter_ranges_match_config"] = bool(range_ok)

    # 2. OOD disjointness from train/ID ranges (temp spike, frozen, drift, cross).
    ood_ok = True
    for e in faults:
        if e.split != "test_generalization":
            continue
        p = e.params
        if e.fault_type == "SPIKE" and e.target_variable == "temperature_c":
            tlo, thi = C.SPIKE_AMPLITUDE["temperature_c"]["train_id"]
            ood_ok &= not _in(tlo, abs(float(p["amplitude"])), thi)
        if e.fault_type == "FROZEN":
            tlo, thi = C.FROZEN_DURATION["train_id"]
            ood_ok &= not (tlo <= e.duration_rows <= thi)
        if e.fault_type == "DRIFT":
            tlo, thi = C.DRIFT_RATE_PER_HOUR[e.target_variable]["train_id"]
            ood_ok &= not _in(tlo, abs(float(p["drift_rate_per_hour"])), thi)
        if e.fault_type == "CROSS_VARIABLE":
            tlo, thi = C.CROSS_DURATION["train_id"]
            ood_ok &= not (tlo <= e.duration_rows <= thi)
    checks["ood_disjoint_from_train_ranges"] = bool(ood_ok)

    # 3. Combinations only in OOD; OOD has at least one.
    checks["combos_only_in_ood"] = all(e.split == "test_generalization" for e in faults
                                       if e.fault_type == "SPIKE_PLUS_DRIFT")
    checks["ood_has_unseen_combination"] = any(e.fault_type == "SPIKE_PLUS_DRIFT" for e in faults
                                               if e.split == "test_generalization")
    checks["train_id_single_faults_only"] = all(e.fault_type in ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE")
                                                for e in faults if e.split != "test_generalization")

    # 4. Events contained in their split.
    contained = True
    for e in all_events:
        s = by_split[e.split]
        contained &= s["start_idx"] <= e.start_idx and e.start_idx + e.duration_rows <= s["end_idx_excl"]
    checks["events_within_split_boundaries"] = bool(contained)

    # 5. Strict non-overlap of event spans (combos are single spans).
    spans = sorted((e.start_idx, e.start_idx + e.duration_rows) for e in all_events)
    checks["no_event_overlap"] = all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))

    # 6. Buffer separation between independent events.
    buf_ok = True
    for split_name in by_split:
        buf = C.buffer_rows(split_name, dataset)
        sp = sorted((e.start_idx, e.start_idx + e.duration_rows)
                    for e in all_events if e.split == split_name)
        buf_ok &= all(a[1] + buf <= b[0] for a, b in zip(sp, sp[1:]))
    checks["buffer_separation_respected"] = bool(buf_ok)

    # 7. Unique injection IDs.
    ids = [e.injection_id for e in all_events]
    checks["injection_ids_unique"] = len(set(ids)) == len(ids)

    return {"all_passed": all(checks.values()), "checks": checks}


def validate_frames(
    split_frames: dict[str, pd.DataFrame],
    source_df: pd.DataFrame,
    faults: list,
    gaps: list,
) -> dict:
    """Validate generated benchmark frames against the source."""
    checks: dict[str, bool] = {}
    src_present = source_df[list(C.CORE_VARS)].notna().all(axis=1).to_numpy()

    # Gap spans genuinely absent.
    gap_ok = True
    for g in gaps:
        span_ts = set(source_df["timestamp"].iloc[g.start_idx : g.start_idx + g.duration_rows].astype(str))
        for name, frame in split_frames.items():
            if name == g.split:
                gap_ok &= len(span_ts & set(frame["timestamp"].astype(str))) == 0
    checks["gap_rows_genuinely_absent"] = bool(gap_ok)

    # Humidity bounds everywhere.
    rh_ok = True
    for frame in split_frames.values():
        rh = pd.to_numeric(frame["relative_humidity_pct"], errors="coerce").dropna()
        rh_ok &= bool(((rh >= 0.0) & (rh <= 100.0)).all())
    checks["humidity_within_bounds"] = bool(rh_ok)

    # No event window covers naturally-missing source rows.
    miss_ok = True
    for e in faults:
        miss_ok &= bool(src_present[e.start_idx : e.start_idx + e.duration_rows].all())
    for g in gaps:
        miss_ok &= bool(src_present[g.start_idx : g.start_idx + g.duration_rows].all())
    checks["no_injection_on_natural_missing"] = bool(miss_ok)

    # Label alignment: every injected position carries anomaly=1 + matching id.
    align_ok = True
    for e in faults:
        frame = split_frames[e.split]
        ts = source_df["timestamp"].iloc[e.start_idx : e.start_idx + e.duration_rows].astype(str).tolist()
        sub = frame[frame["timestamp"].astype(str).isin(ts)]
        align_ok &= len(sub) == e.duration_rows
        align_ok &= bool((sub["ground_truth_anomaly"].to_numpy() == 1).all())
        align_ok &= bool((sub["injection_id"].astype(str) == e.injection_id).all())
    checks["row_labels_align_with_events"] = bool(align_ok)

    return {"all_passed": all(checks.values()), "checks": checks}
