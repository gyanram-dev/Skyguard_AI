"""Minimal JSON protocol for the replay WebSocket (Phase 16).

Server -> client: connection | replay_state | reading | alert | error | complete
Client -> server: start | pause | resume | stop | speed

Fixed allowlists only: stations resolve through the station mapping to
pipeline datasets (delhi/jena); splits to ID/OOD benchmark files; speeds
and limits to numeric ranges. No filesystem paths, model paths,
expressions, or commands ever come from the client.
"""

from __future__ import annotations

DATA_MODE = "historical_replay"

MIN_SPEED, MAX_SPEED = 1, 3600
MIN_LIMIT, MAX_LIMIT = 1, 5000

VALID_SPLITS = ("ID", "OOD")

# Error codes surfaced to the frontend (never stack traces).
INVALID_COMMAND = "invalid_command"
UNKNOWN_STATION = "unknown_station"
INVALID_SPLIT = "invalid_split"
INVALID_SPEED = "invalid_speed"
INVALID_LIMIT = "invalid_limit"
ALREADY_RUNNING = "already_running"
NOT_RUNNING = "not_running"
INSUFFICIENT_CONTEXT = "insufficient_context"
INTERNAL_ERROR = "internal_error"


class ProtocolError(Exception):
    """Invalid client message (code, detail)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def connection_event() -> dict:
    return {"type": "connection", "status": "connected", "data_mode": DATA_MODE}


def replay_state_event(status: str, station_id: str | None = None,
                       split: str | None = None, speed: int | None = None,
                       sequence: int = 0, processed: int = 0,
                       anomalies: int = 0,
                       effective_speed: float | None = None) -> dict:
    event: dict = {"type": "replay_state", "status": status,
                   "data_mode": DATA_MODE}
    if station_id is not None:
        event["station_id"] = station_id
    if split is not None:
        event["split"] = split
    if speed is not None:
        event["speed"] = speed
    event.update({"sequence": sequence, "processed": processed,
                  "anomalies": anomalies})
    if effective_speed is not None:
        event["effective_speed"] = effective_speed
    return event


def error_event(code: str, detail: string) -> dict:
    return {"type": "error", "code": code, "detail": detail,
            "data_mode": DATA_MODE}


def complete_event(station_id: str, split: str, processed: int,
                   anomalies: int, duration_ms: int,
                   effective_speed: float | None = None) -> dict:
    event: dict = {"type": "complete", "station_id": station_id,
                   "split": split, "processed": processed,
                   "anomalies": anomalies, "duration_ms": duration_ms,
                   "data_mode": DATA_MODE}
    if effective_speed is not None:
        event["effective_speed"] = effective_speed
    return event


def parse_client_message(raw) -> tuple[str, dict]:
    """Validate one client message; return (action, params)."""
    if not isinstance(raw, dict):
        raise ProtocolError(INVALID_COMMAND, "Message must be a JSON object.")
    action = raw.get("action")
    if action not in ("start", "pause", "resume", "stop", "speed"):
        raise ProtocolError(
            INVALID_COMMAND,
            f"Unknown action '{action}' (start|pause|resume|stop|speed).")
    params = dict(raw)
    params.pop("action", None)
    if action == "start":
        station_id = params.get("station_id")
        if not isinstance(station_id, str) or not station_id.strip():
            raise ProtocolError(UNKNOWN_STATION,
                                "start requires a station_id string.")
        params["station_id"] = station_id.strip()
        split = str(params.get("split", "OOD")).upper()
        if split not in VALID_SPLITS:
            raise ProtocolError(INVALID_SPLIT,
                                f"Unknown split '{params.get('split')}' (ID|OOD).")
        params["split"] = split
        params["speed"] = _checked_speed(params.get("speed", 10))
        if "limit" in params and params["limit"] is not None:
            params["limit"] = _checked_limit(params["limit"])
        else:
            params["limit"] = None
    if action == "speed":
        if "value" not in params:
            raise ProtocolError(INVALID_SPEED, "speed requires a value.")
        params["value"] = _checked_speed(params["value"])
    return action, params


def _checked_speed(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(INVALID_SPEED, "'speed' must be a number.")
    speed = int(value)
    if not (MIN_SPEED <= speed <= MAX_SPEED):
        raise ProtocolError(
            INVALID_SPEED,
            f"'speed' {value} is outside [{MIN_SPEED}, {MAX_SPEED}].")
    return speed


def _checked_limit(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(INVALID_LIMIT, "'limit' must be a number.")
    limit = int(value)
    if not (MIN_LIMIT <= limit <= MAX_LIMIT):
        raise ProtocolError(
            INVALID_LIMIT,
            f"'limit' {value} is outside [{MIN_LIMIT}, {MAX_LIMIT}].")
    return limit
