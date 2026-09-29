"""Network-wide counts derived from backend station states.

Health is only reported for stations a detector actually covers. Stations that
carry historical observations but have no detector ("context only") and stations
with no data at all ("offline") are counted separately, so a missing capability
is never presented as a healthy verdict.

The displayed buckets therefore satisfy:

    healthy + needs_review + anomaly + offline + context_only == stations_monitored
"""

from __future__ import annotations

from src.api.services import station_service as SS


def indexed_observations(store) -> int:
    """Rows actually loaded from the frozen datasets (measured, not claimed).

    Counts the observation frames the datastore already holds in memory:
    the historical pipeline station(s) plus every mapped GHCNh station.
    """
    total = sum(len(bundle["obs"]) for bundle in store.pipeline.values())
    total += sum(len(frame) for frame in store.noaa_obs.values())
    return int(total)


def live_capable_station_count() -> int:
    """Audited IMD WIS2 capability registry size (capability only, no rows)."""
    try:
        from src.live import sources as LS

        return int(len(LS.STATION_CAPABILITIES))
    except Exception:  # noqa: BLE001 - capability count is display-only
        return 0


def live_connected_count() -> int:
    """Stations with a REAL live connection right now (measured, not inferred).

    A configured provider is not a connection: only a RUNNING live-manager
    loop actually feeding observations counts. Default configuration is
    disabled, so this is 0 unless a live session is genuinely active.
    """
    try:
        from src.api.services import live_service as LV

        manager = LV.get_manager()
        if manager.config.mode in ("DISABLED", ""):
            return 0
        from src.live import manager as LM

        if manager.status != LM.RUNNING or manager.source is None:
            return 0
        return int(len(manager.histories))
    except Exception:  # noqa: BLE001 - display-only count
        return 0


def summarize(store, states: list[dict]) -> dict:
    """Aggregate per-station statuses into honest network counts."""
    counts = {"healthy": 0, "needs_review": 0, "anomaly": 0, "offline": 0}
    detector_covered = 0
    context_only = 0
    indian = 0
    indian_healthy = 0
    indian_context_only = 0
    latest = None
    for entry, state in zip(store.mapping, states):
        scope = SS.operational_scope(entry)
        is_indian = scope == SS.INDIAN_OPERATIONAL
        if is_indian:
            indian += 1
        if not state.get("data_available", False):
            counts["offline"] += 1
        elif SS.probe_capable(entry):
            # Detector-covered: an actual verdict is available.
            detector_covered += 1
            status = state["status"]
            if status == "healthy":
                counts["healthy"] += 1
                if is_indian:
                    indian_healthy += 1
            elif status == "anomaly":
                counts["anomaly"] += 1
            else:
                counts["needs_review"] += 1
        else:
            # Real observations, no detector: no health verdict exists.
            context_only += 1
            if is_indian:
                indian_context_only += 1
        if state.get("last_updated") and (latest is None or state["last_updated"] > latest):
            latest = state["last_updated"]
    monitored = len(store.mapping)
    judged = counts["healthy"] + counts["needs_review"] + counts["anomaly"]
    health_pct = round(100.0 * counts["healthy"] / judged, 2) if judged else 0.0
    # Phase-25 capability buckets (measured from loaded data + detector coverage).
    full_tpr = 0
    partial = 0
    context_only_stations = 0
    historical = 0
    total_observations = indexed_observations(store)
    for entry in store.mapping:
        variables = SS.available_variables(store, entry)
        capability = SS.detector_capability(store, entry, variables)
        if capability == SS.DETECTOR_CAPABILITY_FULL_TPR:
            full_tpr += 1
        elif capability == SS.DETECTOR_CAPABILITY_PARTIAL:
            partial += 1
        elif capability == SS.DETECTOR_CAPABILITY_CONTEXT_ONLY:
            context_only_stations += 1
        if SS.observation_counts(store, entry) > 0:
            historical += 1
    return {"stations_monitored": monitored, **counts,
            "network_health_pct": health_pct,
            "detector_covered": detector_covered,
            "context_only": context_only,
            "data_mode": "historical_replay",
            "indian_operational_monitored": indian,
            "indian_operational_healthy": indian_healthy,
            "indian_operational_context_only": indian_context_only,
            "observations_indexed": total_observations,
            "live_capable_stations": live_capable_station_count(),
            # Phase-25 additive capability summary.
            "total_stations": monitored,
            "historical_stations": historical,
            "full_tpr_stations": full_tpr,
            "partial_stations": partial,
            "context_only_stations": context_only_stations,
            "total_observations": total_observations,
            "live_connected_stations": live_connected_count(),
            "last_updated": latest}
