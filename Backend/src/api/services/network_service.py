"""Network-wide counts derived from backend station states."""

from __future__ import annotations

from src.api.services import station_service as SS


def summarize(store, states: list[dict]) -> dict:
    """Aggregate per-station statuses into network counts."""
    counts = {"healthy": 0, "needs_review": 0, "anomaly": 0, "offline": 0}
    latest = None
    for entry, state in zip(store.mapping, states):
        status = state["status"]
        if status == "healthy":
            counts["healthy"] += 1
        elif status == "anomaly":
            counts["anomaly"] += 1
        elif status == "offline":
            counts["offline"] += 1
        else:
            counts["needs_review"] += 1
        if state.get("last_updated") and (latest is None or state["last_updated"] > latest):
            latest = state["last_updated"]
    monitored = len(store.mapping)
    denominator = monitored - counts["offline"]
    health_pct = round(100.0 * counts["healthy"] / denominator, 2) if denominator else 0.0
    return {"stations_monitored": monitored, **counts,
            "network_health_pct": health_pct, "data_mode": "historical_replay",
            "last_updated": latest}
