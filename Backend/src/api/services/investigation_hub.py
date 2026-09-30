"""Station investigation hub: target station vs its real nearby stations.

Reuses the EXISTING spatial implementation end to end:

- neighbour selection ... ``data/noaa/metadata/neighbor_graph.csv`` (the
  audited selected edges, <=600 km, ranked, up to 3 neighbours);
- alignment ............. ``src.spatial.alignment.align_neighbor``
  (neighbour timestamp <= target, 30-minute tolerance, no interpolation,
  no fill);
- reference/decision .... ``src.spatial.decision`` (``gather_neighbor_values``,
  ``variable_evidence``, ``decide_context``, ``describe``).

Nothing here changes a Phase-22 threshold, creates a second spatial
algorithm, or invents a neighbour value. Stations with no audited graph
edges report the comparison UNAVAILABLE, and stations whose pressure
channel is on a different basis (AWS station pressure vs GHCNh QNH
altimeter) report pressure as UNAVAILABLE with the reason attached.
"""

from __future__ import annotations

import math

import pandas as pd

from src.api.services import station_service as SS
from src.spatial import decision as SD
from src.spatial.alignment import align_neighbor

# The neighbour graph is a GHCNh-station graph. Delhi's AWS station is
# served through the audited Delhi-Safdarjung (INI0000VIDD) edges — the
# exact identity the serving spatial path already uses (scoring.
# _serving_neighbors), so distances are the audited ones.
SPATIAL_IDENTITY = {"delhi": "INI0000VIDD"}

GRAPH_NEIGHBOR_NOTE = ("Neighbour edges come from the audited spatial graph "
                       "(selected station pairs, <=600 km).")


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _graph_path(store):
    return store.root / "data" / "noaa" / "metadata" / "neighbor_graph.csv"


def graph_edges(store, entry: dict) -> list[dict]:
    """Audited selected neighbour edges for a station (possibly empty).

    Returns ``[{backend_station_id, distance_km, rank}]`` sorted by rank.
    An empty list is the honest answer for a station whose geography has
    no audited neighbour inside the configured radius.
    """
    backend_id = entry.get("backend_station_id")
    if not backend_id:
        return []
    identity = SPATIAL_IDENTITY.get(backend_id, backend_id)
    try:
        frame = pd.read_csv(_graph_path(store))
    except Exception:  # noqa: BLE001 - missing graph means no neighbours
        return []
    mask = ((frame["target_station"].astype(str) == identity)
            & (frame["selected"].astype(str).str.lower() == "true"))
    rows = frame.loc[mask].sort_values("rank")
    return [{"backend_station_id": str(r["neighbor_station"]),
             "distance_km": _finite(r["distance_km"]),
             "rank": int(r["rank"])} for _, r in rows.iterrows()]


def _entry_by_backend(store, backend_id: str) -> dict | None:
    for entry in store.mapping:
        if entry.get("backend_station_id") == backend_id:
            return entry
    return None


def neighbour_entries(store, entry: dict) -> list[dict]:
    """Resolve graph edges to mapping entries with real coordinates."""
    out = []
    for edge in graph_edges(store, entry):
        resolved = _entry_by_backend(store, edge["backend_station_id"])
        if resolved is None:
            continue
        out.append({**edge, "entry": resolved})
    return out


def target_frame(store, entry: dict) -> tuple[pd.DataFrame, str, str]:
    """Station observation frame plus its timestamp column and basis."""
    if entry["source_dataset"] == "noaa_ghcnh":
        return store.noaa_obs[entry["backend_station_id"]], "timestamp_utc", "UTC"
    return store.pipeline[entry["backend_station_id"]]["obs"], "timestamp", "IST"


def _as_utc(ts: str | None, basis: str):
    """Anchored timestamp in UTC (documented IST->UTC shift for the AWS set)."""
    if ts is None:
        return None
    try:
        stamp = pd.Timestamp(str(ts))
    except (TypeError, ValueError):
        return None
    if basis == "IST":
        return (stamp - pd.Timedelta(hours=5, minutes=30)).tz_localize("UTC")
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def anchor_position(store, entry: dict, at: str | None) -> tuple[int, str, str]:
    """Row position + timestamp for the requested (or latest) observation.

    ``at`` is a station-local timestamp string from the station's own
    series; the last row at or before it is used (no future data).
    """
    frame, ts_col, basis = target_frame(store, entry)
    stamps = frame[ts_col].astype(str)
    if at is None:
        pos = len(frame) - 1
    else:
        mask = stamps <= str(at)
        pos = int(len(frame) - 1) if not mask.any() else int(
            mask.to_numpy().nonzero()[0][-1])
    return pos, str(stamps.iloc[pos]), basis


def window_evidence(store, entry: dict, anchor_ts: str, cadence_min: float,
                    rows: int = 400) -> dict:
    """Causal window evidence at the anchor from the frozen feature/statistical layer.

    Runs the same ``prepare_split`` + ``build_statistical_baseline`` helpers
    the serving detector uses, on a bounded window ending at the anchor, so
    no future observation can influence the numbers.
    """
    from src.baseline.statistical_baseline import build_statistical_baseline
    from src.isolation_forest.evaluator import prepare_split

    frame, ts_col, _basis = target_frame(store, entry)
    pressure_col = ("altimeter_setting_hpa"
                    if entry["source_dataset"] == "noaa_ghcnh" else "pressure_hpa")
    raw_stamps = frame[ts_col].astype(str)
    # Ordering is preserved: UTC ISO strings and the truncated naive form
    # sort identically, so the causal cut is the same either way.
    if entry["source_dataset"] == "noaa_ghcnh":
        stamps = pd.to_datetime(raw_stamps, utc=True).dt.strftime(
            "%Y-%m-%d %H:%M:%S")
    else:
        stamps = raw_stamps
    prepared = pd.DataFrame({
        "timestamp": stamps,
        "temperature_c": pd.to_numeric(frame["temperature_c"], errors="coerce"),
        "pressure_hpa": pd.to_numeric(frame[pressure_col], errors="coerce"),
        "relative_humidity_pct": pd.to_numeric(frame["relative_humidity_pct"],
                                               errors="coerce"),
    })
    mask = (raw_stamps <= str(anchor_ts)).to_numpy()
    if not bool(mask.any()):
        return {"available": False, "reason": "No observations at or before the anchor."}
    window = prepared.loc[mask].tail(rows).reset_index(drop=True)
    if len(window) < 24:
        return {"available": False,
                "reason": (f"Only {len(window)} observations precede the anchor; "
                           "a causal window is not available.")}
    features, quality = prepare_split(window, "delhi", float(cadence_min))
    baseline, _ = build_statistical_baseline(features, quality, "delhi",
                                             cadence_min=float(cadence_min))
    pos = len(window) - 1
    feat = features.iloc[pos]
    z = {}
    for name, column in (("temperature", "temperature_zscore_baseline"),
                         ("pressure", "pressure_zscore_baseline"),
                         ("humidity", "humidity_zscore_baseline")):
        z[name] = _finite(pd.to_numeric(baseline[column], errors="coerce").iloc[pos])
    finite = [abs(v) for v in z.values() if v is not None]
    reason = str(baseline["statistical_baseline_reason"].iloc[pos])
    dq_reason = str(quality["quality_reason"].iloc[pos])
    return {
        "available": True,
        "window_rows": int(len(window)),
        "window_start": str(window["timestamp"].iloc[0]),
        "window_end": str(window["timestamp"].iloc[-1]),
        "cadence_min": float(cadence_min),
        "z_scores": z,
        "z_max_abs": max(finite) if finite else None,
        "statistical_flag": bool(
            pd.to_numeric(baseline["statistical_baseline_flag"],
                          errors="coerce").iloc[pos] == 1.0),
        "statistical_reason": reason,
        "multivariate_max_abs_robust_deviation_2h": _finite(
            feat.get("multivariate_max_abs_robust_deviation_2h")),
        "temperature_rate_per_hour": _finite(feat.get("temperature_rate_per_hour")),
        "temperature_delta_c": _finite(feat.get("temperature_delta")),
        "temperature_deviation_from_median_2h": _finite(
            feat.get("temperature_deviation_from_median_2h")),
        "data_quality_status": str(quality["quality_status"].iloc[pos]),
        "data_quality_reason": dq_reason,
        "ml_eligible": bool(int(quality["ml_eligible"].iloc[pos])),
        "freeze_flag_in_quality": "possible_freeze" in dq_reason,
    }


def _neighbor_payload(store, neighbour: dict, target_utc) -> dict:
    """One neighbour's real, causally aligned observation (never filled)."""
    entry = neighbour["entry"]
    backend_id = entry["backend_station_id"]
    frame, ts_col, _basis = target_frame(store, entry)
    values = {}
    for name, column in (("temperature", "temperature_c"),
                         ("humidity", "relative_humidity_pct"),
                         ("pressure", None)):
        if column is None:
            column = ("altimeter_setting_hpa"
                      if entry["source_dataset"] == "noaa_ghcnh" else "pressure_hpa")
        got = SD.gather_neighbor_values(target_utc, {backend_id: frame},
                                        [backend_id], column, ts_col=ts_col)
        values[name] = got.get(backend_id)
    aligned_ts = None
    age_minutes = None
    if target_utc is not None and len(frame):
        pos = int(align_neighbor(pd.Series([target_utc]), frame[ts_col]).iloc[0])
        if pos >= 0:
            aligned_ts = str(frame[ts_col].astype(str).iloc[pos])
            try:
                neighbour_stamp = pd.to_datetime(aligned_ts, utc=True)
                delta = target_utc - neighbour_stamp
                age_minutes = round(float(delta.total_seconds()) / 60.0, 1)
            except (TypeError, ValueError):
                age_minutes = None
    return {
        "station_id": entry["frontend_station_id"],
        "city": entry["city"],
        "backend_station_id": backend_id,
        "latitude": entry.get("latitude"),
        "longitude": entry.get("longitude"),
        "distance_km": neighbour["distance_km"],
        "rank": neighbour["rank"],
        "aligned_timestamp": aligned_ts,
        "age_minutes": age_minutes,
        "temperature": values["temperature"],
        "humidity": values["humidity"],
        "pressure": values["pressure"],
        "pressure_basis": SS.pressure_basis(entry),
        "data_freshness": ("no observation within the 30-minute alignment window"
                           if aligned_ts is None else "aligned causally (<=30 min)"),
    }


def build_investigation(store, station_id: str, at: str | None = None) -> dict:
    """Full investigation bundle for one station (target vs neighbours)."""
    entry = SS.get_mapping(store, station_id)
    if entry is None:
        raise KeyError(station_id)
    frame, ts_col, basis = target_frame(store, entry)
    pos, anchor_ts, _basis = anchor_position(store, entry, at)
    row = frame.iloc[pos]
    obs = {
        "temperature_c": _finite(row.get("temperature_c")),
        "relative_humidity_pct": _finite(row.get("relative_humidity_pct")),
        "pressure_hpa": _finite(row.get("pressure_hpa")
                                if entry["source_dataset"] != "noaa_ghcnh"
                                else row.get("altimeter_setting_hpa")),
    }
    detector_entry = SS.detector_registry_entry(store, entry)
    cadence = (float(detector_entry.get("cadence", 30))
               if detector_entry is not None else
               (5.0 if entry["source_dataset"] == "delhi_clean"
                else 30.0))
    evidence = window_evidence(store, entry, anchor_ts, cadence)
    neighbours = neighbour_entries(store, entry)
    target_utc = _as_utc(anchor_ts, basis)
    nearby = [_neighbor_payload(store, n, target_utc) for n in neighbours]
    expected = len(nearby)
    target_pressure_basis = SS.pressure_basis(entry)
    # Pressure is only comparable on the same measurement basis (AWS station
    # pressure vs GHCNh QNH altimeter is never converted).
    pressure_compatible = expected > 0 and all(
        neighbour["pressure_basis"] == target_pressure_basis for neighbour in nearby)

    temp_vals = {n["backend_station_id"]: n["temperature"] for n in nearby}
    rh_vals = {n["backend_station_id"]: n["humidity"] for n in nearby}
    pres_vals = {n["backend_station_id"]: n["pressure"] for n in nearby}
    temp_ev = SD.variable_evidence(obs["temperature_c"], temp_vals, expected)
    rh_ev = SD.variable_evidence(obs["relative_humidity_pct"], rh_vals, expected)
    pres_ev = SD.variable_evidence(obs["pressure_hpa"], pres_vals, expected,
                                   pressure_compatible=pressure_compatible)

    base_state, base_basis = _base_state(store, entry, anchor_ts, evidence,
                                         detector_entry)
    decision = SD.decide_context(base_state, temp_ev, rh_ev)
    decision["description"] = SD.describe(decision)

    notes = [GRAPH_NEIGHBOR_NOTE]
    if not neighbours:
        notes.append("Spatial context unavailable — no neighbour values are "
                     "invented for this station.")
    if not pressure_compatible and expected:
        notes.append("Pressure is not compared across different measurement "
                     "bases (AWS station pressure vs GHCNh QNH altimeter).")
    notes.append("Nearby stations are contextual evidence, never confirmation "
                 "of a physical event.")
    return {
        "station_id": station_id,
        "city": entry["city"],
        "coordinates": ({"latitude": entry.get("latitude"),
                         "longitude": entry.get("longitude")}),
        "pressure_basis": target_pressure_basis,
        "source_dataset": entry.get("source_dataset"),
        "anchor": {"timestamp": anchor_ts,
                   "basis": base_basis,
                   "requested": at,
                   "time_basis": basis},
        "target_observation": obs,
        "detector_verdict": evidence,
        "nearby": nearby,
        "expected_neighbors": expected,
        "usable_neighbors": int(temp_ev.get("usable_neighbor_count") or 0),
        "comparison": {"temperature": temp_ev, "humidity": rh_ev,
                       "pressure": pres_ev,
                       "target_temperature": obs["temperature_c"],
                       "neighbor_median_temperature": temp_ev.get("reference_median"),
                       "temperature_deviation": temp_ev.get("deviation")},
        "interpretation": decision,
        "notes": notes,
    }


def _base_state(store, entry: dict, anchor_ts: str, evidence: dict,
                detector_entry: dict | None) -> tuple[str, str]:
    """Base detector state feeding the spatial decision (never spatial-driven).

    Only the station's own detector output can set BASE_ANOMALOUS: the
    frozen ensemble verdict when the station is ensemble-covered and the
    anchor falls inside the stored evaluation window, otherwise this
    station's calibrated statistical flag. No detector -> BASE_INSUFFICIENT.
    """
    is_delhi = entry.get("source_dataset") == "delhi_clean"
    if is_delhi:
        try:
            ens = store.pipeline["delhi"]["ens"]
            stamps = ens["timestamp"].astype(str)
            mask = stamps == str(anchor_ts)
            if bool(mask.any()):
                row = ens.loc[mask].iloc[0]
                flagged = (int(row["ens_median_flag"]) == 1
                           and int(row["evaluation_eligible"]) == 1)
                return ((SD.BASE_ANOMALOUS if flagged else SD.BASE_NORMAL),
                        "ensemble_verdict_at_anchor")
        except (KeyError, TypeError, ValueError):
            pass
        return SD.BASE_INSUFFICIENT, "no_ensemble_verdict_at_anchor"
    if detector_entry is None:
        return SD.BASE_INSUFFICIENT, "no_detector_for_station"
    if not evidence.get("available"):
        return SD.BASE_INSUFFICIENT, "no_causal_window_at_anchor"
    flagged = bool(evidence.get("statistical_flag")) or bool(
        evidence.get("freeze_flag_in_quality"))
    if flagged and evidence.get("ml_eligible", True):
        return SD.BASE_ANOMALOUS, "calibrated_statistical_flag_at_anchor"
    return SD.BASE_NORMAL, "calibrated_statistical_flag_at_anchor"
