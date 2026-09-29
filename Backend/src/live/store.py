"""Minimal SQLite persistence for live operation (no new infrastructure).

Tables: observations, quality_events, alert_episodes, alert_observations,
source_status. Operational records carry predictions + provenance only —
no reference-outcome columns exist anywhere in this schema. Replay stays
ephemeral; evaluation stays separate. WAL mode, one connection behind a
threading lock.
"""

from __future__ import annotations

import json
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
  obs_id TEXT PRIMARY KEY,
  station_id TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  temperature_c REAL,
  pressure_hpa REAL,
  relative_humidity_pct REAL,
  source TEXT NOT NULL,
  pressure_basis TEXT NOT NULL DEFAULT 'unknown',
  dq_state TEXT NOT NULL,
  received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_station_time
  ON observations (station_id, timestamp);
CREATE TABLE IF NOT EXISTS quality_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  station_id TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  state TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS alert_episodes (
  alert_id TEXT PRIMARY KEY,
  station_id TEXT NOT NULL,
  episode_key TEXT NOT NULL,
  interpretation TEXT NOT NULL,
  started_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  detection_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  resolved_at TEXT,
  score REAL,
  evidence_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS alert_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_id TEXT NOT NULL,
  obs_id TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  score REAL,
  UNIQUE (alert_id, obs_id)
);
CREATE TABLE IF NOT EXISTS source_status (
  source TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  last_success TEXT,
  last_attempt TEXT,
  last_error TEXT NOT NULL DEFAULT '',
  detail_json TEXT NOT NULL DEFAULT '{}'
);
"""


class LiveStore:
    """Thread-safe SQLite wrapper for live operational state."""

    def __init__(self, path: str) -> None:
        import os

        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL;")
        with self._lock:
            self._db.executescript(SCHEMA)

    def save_observation(self, ob, dq_state: str, received_at: str) -> bool:
        """Insert; False when the observation identity already exists."""
        with self._lock:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO observations "
                "(obs_id, station_id, timestamp, temperature_c, pressure_hpa,"
                " relative_humidity_pct, source, pressure_basis, dq_state,"
                " received_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ob.obs_id, ob.station_id, ob.timestamp.isoformat(),
                 ob.temperature_c, ob.pressure_hpa, ob.relative_humidity_pct,
                 ob.source, ob.pressure_basis, dq_state, received_at))
            self._db.commit()
            return cur.rowcount == 1

    def save_quality_event(self, station_id: str, timestamp: str,
                           state: str, detail: str = "") -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO quality_events (station_id, timestamp, state,"
                " detail) VALUES (?,?,?,?)",
                (station_id, timestamp, state, detail[:500]))
            self._db.commit()

    def upsert_episode(self, episode: dict, evidence: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO alert_episodes (alert_id, station_id,"
                " episode_key, interpretation, started_at, last_seen_at,"
                " detection_count, status, resolved_at, score, evidence_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(alert_id) DO UPDATE SET"
                " last_seen_at=excluded.last_seen_at,"
                " detection_count=excluded.detection_count,"
                " status=excluded.status, resolved_at=excluded.resolved_at,"
                " score=excluded.score, evidence_json=excluded.evidence_json",
                (episode["alert_id"], episode["station_id"],
                 episode["episode_key"], episode["interpretation"],
                 episode["started_at"], episode["last_seen_at"],
                 episode["detection_count"], episode["status"],
                 episode.get("resolved_at"), episode.get("score"),
                 json.dumps(evidence, default=str)[:8000]))
            self._db.commit()

    def link_observation(self, alert_id: str, obs_id: str,
                         timestamp: str, score) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO alert_observations (alert_id, obs_id,"
                " timestamp, score) VALUES (?,?,?,?)",
                (alert_id, obs_id, timestamp, score))
            self._db.commit()

    def set_source_status(self, source: str, state: str,
                          last_success: str | None, last_attempt: str,
                          last_error: str = "", detail: dict | None = None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO source_status (source, state, last_success,"
                " last_attempt, last_error, detail_json) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(source) DO UPDATE SET state=excluded.state,"
                " last_success=excluded.last_success,"
                " last_attempt=excluded.last_attempt,"
                " last_error=excluded.last_error,"
                " detail_json=excluded.detail_json",
                (source, state, last_success, last_attempt,
                 last_error[:500], json.dumps(detail or {}, default=str)[:2000]))
            self._db.commit()

    def open_episodes(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT alert_id, station_id, episode_key, interpretation,"
                " started_at, last_seen_at, detection_count, status,"
                " resolved_at, score FROM alert_episodes"
                " WHERE status='OPEN' ORDER BY started_at").fetchall()
        keys = ("alert_id", "station_id", "episode_key", "interpretation",
                "started_at", "last_seen_at", "detection_count", "status",
                "resolved_at", "score")
        return [dict(zip(keys, r)) for r in rows]

    def episodes(self, station_id: str | None = None,
                 limit: int = 100) -> list[dict]:
        with self._lock:
            if station_id:
                rows = self._db.execute(
                    "SELECT alert_id, station_id, episode_key, interpretation,"
                    " started_at, last_seen_at, detection_count, status,"
                    " resolved_at, score FROM alert_episodes"
                    " WHERE station_id=? ORDER BY started_at DESC LIMIT ?",
                    (station_id, limit)).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT alert_id, station_id, episode_key, interpretation,"
                    " started_at, last_seen_at, detection_count, status,"
                    " resolved_at, score FROM alert_episodes"
                    " ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        keys = ("alert_id", "station_id", "episode_key", "interpretation",
                "started_at", "last_seen_at", "detection_count", "status",
                "resolved_at", "score")
        return [dict(zip(keys, r)) for r in rows]

    def observations(self, station_id: str, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT obs_id, station_id, timestamp, temperature_c,"
                " pressure_hpa, relative_humidity_pct, source,"
                " pressure_basis, dq_state, received_at FROM observations"
                " WHERE station_id=? ORDER BY timestamp DESC LIMIT ?",
                (station_id, limit)).fetchall()
        keys = ("obs_id", "station_id", "timestamp", "temperature_c",
                "pressure_hpa", "relative_humidity_pct", "source",
                "pressure_basis", "dq_state", "received_at")
        return [dict(zip(keys, r)) for r in rows]

    def source_statuses(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT source, state, last_success, last_attempt,"
                " last_error FROM source_status").fetchall()
        return [dict(zip(("source", "state", "last_success", "last_attempt",
                           "last_error"), r)) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
