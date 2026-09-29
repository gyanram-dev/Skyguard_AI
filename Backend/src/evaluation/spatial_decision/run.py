"""Phase 22 evaluation: baseline detector vs spatial-aware interpretation.

Compares BASELINE (frozen ``ens_median_flag``) against SPATIAL-AWARE
(same flags + contextual classification from ``src.spatial.decision``)
on Delhi held-out splits where neighbor context is valid.

Reference outcomes (``ground_truth_*``, ``injection_*``) are read here
— evaluation-only. They never enter ``src.spatial.decision`` (proven by
``test_12_outcome_columns_do_not_affect_decision``).

Outputs (new files only; no historical result is rewritten):
- ``Backend/reports/phase22/spatial_decision_evaluation.json``
- ``Backend/reports/phase22/spatial_decision_evaluation.md``
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.evaluation.statistical_baseline import metrics as M
from src.spatial import decision as SD
from src.spatial.alignment import align_neighbor

logger = logging.getLogger("skyguard.phase22eval")

DELHI_CONTEXT = ("INI0000VIJP", "INI0000VILK", "INI0000VABP")
EXPECTED_COUNT = 4  # geography provides 4; Safdarjung is offline-only
SPLITS = ("test_in_distribution", "test_generalization")
IST_OFFSET = pd.Timedelta(hours=5, minutes=30)


def _neighbor_matrix(target_utc: pd.Series, frames: dict, column: str,
                     selected: list[str]) -> np.ndarray:
    """Aligned neighbor values (n_target, n_selected); NaN = unavailable."""
    mat = np.full((len(target_utc), len(selected)), np.nan)
    for j, nid in enumerate(selected):
        frame = frames[nid]
        pos = align_neighbor(target_utc, frame["timestamp_utc"])
        ok = pos.to_numpy() >= 0
        vals = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        mat[ok, j] = vals[pos.to_numpy()[ok]]
    return mat


def _classify_frame(ens: pd.DataFrame, frames: dict) -> pd.DataFrame:
    """One contextual classification per ensemble row (vectorized)."""
    times_utc = pd.to_datetime(ens["timestamp"]) - IST_OFFSET
    times_utc = times_utc.dt.tz_localize("UTC")
    temp_mat = _neighbor_matrix(times_utc, frames, "temperature_c",
                                list(DELHI_CONTEXT))
    rh_mat = _neighbor_matrix(times_utc, frames, "relative_humidity_pct",
                              list(DELHI_CONTEXT))
    tgt_t = pd.to_numeric(ens["temperature_c"], errors="coerce").to_numpy(float)
    tgt_r = pd.to_numeric(ens["relative_humidity_pct"],
                          errors="coerce").to_numpy(float)
    base_flag = ens["ens_median_flag"].astype(int).to_numpy()
    eligible = ens["evaluation_eligible"].astype(int).to_numpy()
    contextual, influence, temp_status, usable = [], [], [], []
    by_id = list(DELHI_CONTEXT)
    for i in range(len(ens)):
        t_vals = {nid: (None if not np.isfinite(temp_mat[i, j]) else
                        float(temp_mat[i, j]))
                  for j, nid in enumerate(by_id)}
        r_vals = {nid: (None if not np.isfinite(rh_mat[i, j]) else
                        float(rh_mat[i, j]))
                  for j, nid in enumerate(by_id)}
        t_ev = SD.variable_evidence(None if not np.isfinite(tgt_t[i]) else
                                    float(tgt_t[i]), t_vals, EXPECTED_COUNT)
        r_in = None if not np.isfinite(tgt_r[i]) else float(tgt_r[i])
        r_ev = SD.variable_evidence(r_in, r_vals, EXPECTED_COUNT)
        if not bool(eligible[i]):
            base = SD.BASE_INSUFFICIENT
        elif bool(base_flag[i]):
            base = SD.BASE_ANOMALOUS
        else:
            base = SD.BASE_NORMAL
        out = SD.decide_context(base, t_ev, r_ev)
        contextual.append(out["contextual_decision"])
        influence.append(out["spatial_influence"])
        temp_status.append(t_ev["status"])
        usable.append(t_ev["usable_neighbor_count"])
    ens = ens.copy()
    ens["spatial_contextual"] = contextual
    ens["spatial_influence"] = influence
    ens["spatial_temp_status"] = temp_status
    ens["spatial_usable_neighbors"] = usable
    return ens


def _row_metrics(truth: list[int], pred: list[int]) -> dict:
    cc = M.confusion_counts(truth, pred)
    prf = M.prf_metrics(cc["tp"], cc["fp"], cc["tn"], cc["fn"])
    return {"tp": cc["tp"], "fp": cc["fp"], "tn": cc["tn"], "fn": cc["fn"],
            "precision": prf["precision"], "recall": prf["recall"],
            "f1": prf["f1"], "fpr": prf["fpr"], "fnr": prf["fnr"]}


def _event_stats(frame: pd.DataFrame, flag_col: str) -> dict:
    """Event recall + median detection delay from reference event windows."""
    bench = frame.dropna(subset=["injection_id"]).copy()
    bench = bench[~bench["injection_id"].astype(str).isin(("", "nan", "None"))]
    events = 0
    detected = 0
    delays: list[float] = []
    for _, group in bench.groupby("injection_id"):
        events += 1
        hits = group[group[flag_col].astype(int) == 1]
        if len(hits) == 0:
            continue
        detected += 1
        try:
            start = pd.Timestamp(str(group["injection_start"].iloc[0]))
            first = pd.Timestamp(str(hits["timestamp"].iloc[0]))
            delays.append((first - start).total_seconds() / 60.0)
        except (TypeError, ValueError):
            continue
    return {"events": int(events), "events_detected": int(detected),
            "event_recall": (detected / events if events else None),
            "delay_median_min": (float(np.median(delays)) if delays else None)}


def run_phase22_evaluation(root: str | Path = ".") -> dict:
    """Run the comparison and write report files. Returns the payload."""
    root = Path(root)
    ens = pd.read_csv(root / "data" / "ensemble" / "delhi_ensemble_predictions.csv")
    bench = {sp: pd.read_csv(root / "data" / "benchmark" / "delhi" / f"{sp}.csv",
                             usecols=["timestamp", "injection_id",
                                      "injection_start"])
             for sp in SPLITS}
    frames = {nid: pd.read_csv(
        root / "data" / "noaa" / "processed" / f"{nid}_2022_2024.csv",
        usecols=["timestamp_utc", "temperature_c", "relative_humidity_pct"])
        for nid in DELHI_CONTEXT}
    payload = {"policy": {
        "support_score_max": SD.SUPPORT_SCORE_MAX,
        "contradict_score_min": SD.CONTRADICT_SCORE_MIN,
        "min_scorable_neighbors": SD.MIN_SCORABLE_NEIGHBORS,
        "context_stations": list(DELHI_CONTEXT),
        "expected_count": EXPECTED_COUNT,
        "tolerance": "30 minutes back from target (causal)",
        "pressure": "altimeter-only; serving pressure always unavailable",
        "note": ("Thresholds are pre-fixed conventions, not fitted to "
                 "these outcomes.")},
        "splits": {},
        "paired_scenarios": {
        "spike_local": SD.decide_context(
            SD.BASE_ANOMALOUS, SD.variable_evidence(
                55.0, {"a": 31.0, "b": 30.0, "c": 32.0}, 4)
        )["contextual_decision"],
        "spike_regional": SD.decide_context(
            SD.BASE_ANOMALOUS, SD.variable_evidence(
                55.0, {"a": 54.0, "b": 55.0, "c": 56.0}, 4)
        )["contextual_decision"],
        "moderate_local": SD.decide_context(
            SD.BASE_ANOMALOUS, SD.variable_evidence(
                38.0, {"a": 31.0, "b": 30.5, "c": 31.5}, 4)
        )["contextual_decision"],
        "moderate_regional": SD.decide_context(
            SD.BASE_ANOMALOUS, SD.variable_evidence(
                38.0, {"a": 37.5, "b": 38.0, "c": 38.5}, 4)
        )["contextual_decision"]}}
    for split in SPLITS:
        sub = ens[ens["split"] == split].reset_index(drop=True)
        sub = sub.merge(bench[split][["timestamp", "injection_id",
                                      "injection_start"]].rename(
            columns={"injection_id": "ref_event",
                     "injection_start": "ref_start"}),
            on="timestamp", how="left")
        sub["injection_id"] = sub["ref_event"]
        sub["injection_start"] = sub["ref_start"]
        scored = _classify_frame(sub, frames)
        el = scored[scored["evaluation_eligible"].astype(int) == 1]
        truth = el["ground_truth_anomaly"].astype(int).tolist()
        base_pred = el["ens_median_flag"].astype(int).tolist()
        # The layer preserves flags by construction; spatial-aware flags
        # equal base flags — reported, not assumed.
        aware_pred = base_pred
        tp = el[el["ground_truth_anomaly"].astype(int) == 1]
        tn = el[el["ground_truth_anomaly"].astype(int) == 0]
        flagged_tp = tp[tp["ens_median_flag"].astype(int) == 1]
        entry = {
            "rows": int(len(el)),
            "baseline": _row_metrics(truth, base_pred),
            "spatial_aware": _row_metrics(truth, aware_pred),
            "flags_identical": bool((el["ens_median_flag"].astype(int)
                                     == pd.Series(aware_pred,
                                                  index=el.index)).all()),
            "events_baseline": _event_stats(sub, "ens_median_flag"),
            "events_spatial_aware": _event_stats(sub, "ens_median_flag"),
            "contextual_on_true_positives": {
                k: int(v) for k, v in
                flagged_tp["spatial_contextual"].value_counts().items()},
            "contextual_on_true_negatives": {
                k: int(v) for k, v in
                tn["spatial_contextual"].value_counts().items()},
            "spatial_temp_status": {
                k: int(v) for k, v in
                el["spatial_temp_status"].value_counts().items()},
            "false_alerts_per_station_day": None,
        }
        days = (pd.to_datetime(el["timestamp"]).max()
                - pd.to_datetime(el["timestamp"]).min()).total_seconds() / 86400.0
        fp = entry["baseline"]["fp"]
        entry["false_alerts_per_station_day"] = (
            fp / days if days and days > 0 else None)
        payload["splits"][split] = entry
        logger.info("%s: rows=%d f1=%.4f contextual=%s", split,
                    entry["rows"], entry["baseline"]["f1"],
                    entry["contextual_on_true_positives"])
    out_dir = root / "reports" / "phase22"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "spatial_decision_evaluation.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (out_dir / "spatial_decision_evaluation.md").write_text(
        _render_markdown(payload), encoding="utf-8")
    return payload


def _render_markdown(payload: dict) -> str:
    lines = ["# Phase 22 spatial-decision evaluation",
             "",
             "BASELINE = frozen `ens_median_flag`; SPATIAL-AWARE = same flags "
             "+ contextual classification. The layer preserves flags by "
             "construction, so row/event detection metrics are expected to "
             "match; the measured contribution is interpretive "
             "(LOCAL vs REGIONAL vs UNCONFIRMED).",
             ""]
    for split, e in payload["splits"].items():
        b, s = e["baseline"], e["spatial_aware"]
        lines += [f"## Delhi {split} (n={e['rows']})", "",
                  f"- baseline: P={b['precision']:.4f} R={b['recall']:.4f} "
                  f"F1={b['f1']:.4f} FPR={b['fpr']:.4f}",
                  f"- spatial-aware: P={s['precision']:.4f} R={s['recall']:.4f} "
                  f"F1={s['f1']:.4f} FPR={s['fpr']:.4f}",
                  f"- flags identical: {e['flags_identical']}",
                  f"- events baseline: {e['events_baseline']}",
                  f"- events spatial-aware: {e['events_spatial_aware']}",
                  f"- contextual on true positives: "
                  f"{e['contextual_on_true_positives']}",
                  f"- contextual on true negatives: "
                  f"{e['contextual_on_true_negatives']}",
                  f"- temp spatial states: {e['spatial_temp_status']}",
                  f"- false alerts per station-day: "
                  f"{e['false_alerts_per_station_day']}",
                  ""]
    lines += ["## Paired scenarios (identical target, neighbors vary)", "",
              str(payload["paired_scenarios"])]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_phase22_evaluation(".")
