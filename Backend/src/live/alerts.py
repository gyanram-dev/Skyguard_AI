"""Live alert episodes: operational grouping over scored observations.

One episode per contiguous anomalous run per station: repeated polling
of the same condition extends the episode (``last_seen_at``,
``detection_count``) instead of spawning alerts. Recovery closes it.
Individual observations are never hidden — each scored row is stored
with its evidence. Records carry predictions and provenance only;
reference-outcome fields must never enter this module.
"""

from __future__ import annotations

import hashlib
import uuid

from src.live import obs as LO

OPEN = "OPEN"
RESOLVED = "RESOLVED"


def episode_key(station_id: str, contextual: str) -> str:
    """Grouping key: station + interpretation family."""
    family = ("ANOMALY" if contextual in (
        "LOCAL_SENSOR_ANOMALY", "POSSIBLE_REGIONAL_EVENT",
        "ANOMALY_WITHOUT_SPATIAL_CONFIRMATION") else contextual)
    return f"{station_id}|{family}"


def make_alert_id(station_id: str, started_at: str) -> str:
    seed = f"live|{station_id}|{started_at}|{uuid.uuid4().hex}"
    return "live-" + hashlib.sha256(seed.encode()).hexdigest()[:16]


class EpisodeTracker:
    """In-memory open-episode state (durable mirror lives in SQLite)."""

    def __init__(self, continuation_s: float = 3600.0,
                 resolve_after_normals: int = 2) -> None:
        self.continuation_s = continuation_s
        self.resolve_after_normals = resolve_after_normals
        self._open: dict[str, dict] = {}
        self._normals: dict[str, int] = {}

    def observe(self, station_id: str, scored: dict) -> dict | None:
        """Feed one scored observation; return episode event or None.

        Returns ``{"action": "opened"|"extended"|"resolved", ...}``.
        NORMAL verdicts advance recovery counters; anomalous verdicts
        open or extend the station's episode.
        """
        contextual = scored.get("spatial_decision", {}).get(
            "contextual_decision", "")
        anomalous = contextual in ("LOCAL_SENSOR_ANOMALY",
                                   "POSSIBLE_REGIONAL_EVENT",
                                   "ANOMALY_WITHOUT_SPATIAL_CONFIRMATION")
        key = episode_key(station_id, contextual)
        stamp = scored.get("timestamp", "")
        if anomalous:
            self._normals[station_id] = 0
            if key in self._open:
                ep = self._open[key]
                ep["last_seen_at"] = stamp
                ep["detection_count"] += 1
                return {"action": "extended", "episode": ep}
            ep = {"alert_id": make_alert_id(station_id, stamp),
                  "station_id": station_id,
                  "episode_key": key,
                  "interpretation": contextual,
                  "started_at": stamp, "last_seen_at": stamp,
                  "detection_count": 1, "status": OPEN,
                  "resolved_at": None,
                  "score": scored.get("anomaly_score"),
                  "station_key": station_id}
            self._open[key] = ep
            return {"action": "opened", "episode": ep}
        count = self._normals.get(station_id, 0) + 1
        self._normals[station_id] = count
        for ekey in [k for k, e in self._open.items()
                     if e["station_id"] == station_id]:
            if count >= self.resolve_after_normals:
                ep = self._open.pop(ekey)
                ep["status"] = RESOLVED
                ep["resolved_at"] = stamp
                return {"action": "resolved", "episode": ep}
        return None

    def open_episodes(self) -> list[dict]:
        return list(self._open.values())

    def restore(self, episodes: list[dict]) -> None:
        """Reload OPEN episodes after a restart (durable state wins)."""
        for ep in episodes:
            if ep.get("status") == OPEN:
                self._open[ep["episode_key"]] = dict(ep)
