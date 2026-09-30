"""Durable replay alerts (reuses the existing SQLite persistence layer).

Replay anomaly events are evidence a judge can inspect after the socket
closes, so they are persisted — but they are NOT live operational alerts
and NOT frozen historical alerts, so they must never pollute either feed:

- frozen operational alerts: served from `data/api` / detector outputs and
  rebuilt at startup (`src.api.services.anomaly_service`) — untouched;
- live operational episodes: persisted by `LiveStore` for live ingestion;
- replay records: this module, same `LiveStore` implementation, dedicated
  database file under `data/replay/` with replay-specific provenance.

No schema change: the existing `alert_episodes` / `observations` tables are
used as-is. Records are deterministic per (station, timestamp, detector),
so re-running a replay updates rather than duplicates. A normal
observation never produces a record — `record` refuses anything whose
unified result is not an anomaly.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
from pathlib import Path

from src.live.obs import CanonicalObservation
from src.live.store import LiveStore

logger = logging.getLogger("skyguard.replay_alerts")

DB_REL = Path("data") / "replay" / "replay_alerts.db"

# Record type marker. Replay records are immutable evidence, not an
# operational episode lifecycle, so they never reuse OPEN/RESOLVED.
RECORD_STATUS = "RECORDED"
RECORD_INTERPRETATION = "HISTORICAL_REPLAY_ANOMALY"


def db_path(root: str | Path = ".") -> Path:
    return Path(root) / DB_REL


def alert_id(station_id: str, timestamp: str, detector: str) -> str:
    """Deterministic replay alert ID (same event -> same record)."""
    seed = f"replay|{station_id}|{timestamp}|{detector}"
    return "replay-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


class ReplayAlertStore:
    """Append/read replay anomaly records over the existing LiveStore."""

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root)
        self.path = db_path(self.root)
        self._store = LiveStore(str(self.path))

    def record(self, result: dict, *, backend_id: str, city: str = "",
               station_id: str | None = None) -> dict | None:
        """Persist one unified detection result; None unless it is an anomaly.

        The returned record exposes exactly the contract fields:
        station, timestamp, severity, confidence, reason, detector, status.
        """
        if not isinstance(result, dict) or not result.get("anomaly"):
            # Normal observation: never create an alert record.
            return None
        station = station_id or str(result.get("station_id") or backend_id)
        timestamp = str(result.get("timestamp") or "")
        detector = str(result.get("detector") or "Statistical Baseline")
        record = {
            "alert_id": alert_id(station, timestamp, detector),
            "station_id": station,
            "backend_station_id": backend_id,
            "city": city,
            "timestamp": timestamp,
            "severity": str(result.get("severity") or "LOW"),
            "confidence": result.get("confidence"),
            "reason": str(result.get("primary_reason") or ""),
            "detector": detector,
            "status": RECORD_STATUS,
            "score": result.get("anomaly_score"),
            "data_mode": "HISTORICAL_REPLAY",
            "source_mode": "REPLAY_ALERT",
            "data_quality": result.get("data_quality"),
            "contributing_factors": result.get("contributing_factors") or [],
        }
        episode = {
            "alert_id": record["alert_id"],
            "station_id": station,
            "episode_key": f"replay|{station}|{record['severity']}",
            "interpretation": RECORD_INTERPRETATION,
            "started_at": timestamp,
            "last_seen_at": timestamp,
            "detection_count": 1,
            "status": RECORD_STATUS,
            "resolved_at": None,
            "score": record["score"],
        }
        self._store.upsert_episode(episode, {"alert": record})
        self._link_observation(record, result, backend_id)
        return record

    def _link_observation(self, record: dict, result: dict,
                          backend_id: str) -> None:
        """Store the triggering observation with replay provenance."""
        try:
            stamp = dt.datetime.fromisoformat(record["timestamp"].replace(
                "Z", "+00:00")).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return
        quality = result.get("data_quality") or {}
        observation = CanonicalObservation(
            station_id=record["station_id"], timestamp=stamp,
            temperature_c=result.get("temperature"),
            pressure_hpa=result.get("pressure"),
            relative_humidity_pct=result.get("relative_humidity"),
            source="HISTORICAL_REPLAY", source_station_id=backend_id,
            pressure_basis="altimeter_qnh_hpa",
            raw_timestamp=record["timestamp"])
        self._store.save_observation(
            observation, str(quality.get("status") or "UNKNOWN"),
            dt.datetime.now(dt.timezone.utc).isoformat())
        self._store.link_observation(record["alert_id"], observation.obs_id,
                                     record["timestamp"], record["score"])

    def records(self, station_id: str | None = None,
                limit: int = 100) -> list[dict]:
        """Persisted replay alerts, newest first (read back from SQLite)."""
        out: list[dict] = []
        for episode in self._store.episodes(station_id, limit):
            detail = self._store.episode_detail(episode["alert_id"])
            record = (detail or {}).get("evidence", {}).get("alert")
            if not isinstance(record, dict):
                record = {"alert_id": episode["alert_id"],
                          "station_id": episode["station_id"],
                          "timestamp": episode["started_at"],
                          "severity": episode["episode_key"].rsplit("|", 1)[-1],
                          "confidence": None, "reason": "",
                          "detector": "", "status": episode["status"],
                          "score": episode.get("score")}
            out.append(record)
        return out

    def count(self, station_id: str | None = None) -> int:
        """Number of persisted replay alerts (optionally one station)."""
        return len(self._store.episodes(station_id, 100000))

    def close(self) -> None:
        self._store.close()


def record_anomaly(root: str | Path, result: dict, *, backend_id: str,
                   city: str = "", station_id: str | None = None) -> dict | None:
    """Persist one replay anomaly; returns the record (None when normal).

    Opens and closes the store per call (replay is a short-lived session),
    so a crash mid-replay never holds the database open.
    """
    store = ReplayAlertStore(root)
    try:
        return store.record(result, backend_id=backend_id, city=city,
                            station_id=station_id)
    finally:
        store.close()


def read_records(root: str | Path = ".", station_id: str | None = None,
                 limit: int = 100) -> list[dict]:
    """Read persisted replay alerts without keeping a connection open."""
    store = ReplayAlertStore(root)
    try:
        return store.records(station_id, limit)
    finally:
        store.close()
