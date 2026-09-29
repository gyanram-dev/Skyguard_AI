"""Live ingestion configuration (environment-driven, no secrets in Git).

Source modes: DISABLED (default), CONTROLLED_LIVE (scripted causal feed,
no credentials), LIVE_IMD (WIS2 poller), LIVE_ARG (contract-gated).
The server always starts; live endpoints report LIVE_UNAVAILABLE with a
safe explanation when the mode cannot serve.
"""

from __future__ import annotations

import os

DISABLED = "DISABLED"
CONTROLLED_LIVE = "CONTROLLED_LIVE"
LIVE_IMD = "LIVE_IMD"
LIVE_ARG = "LIVE_ARG"

# Historical (non-live) modes, reported for UI clarity only.
REPLAY = "REPLAY"
UPLOAD = "UPLOAD"


class LiveConfig:
    """Validated live configuration snapshot."""

    def __init__(self) -> None:
        self.mode = (os.environ.get("IMD_SOURCE_MODE") or DISABLED).strip().upper()
        if self.mode not in (DISABLED, CONTROLLED_LIVE, LIVE_IMD, LIVE_ARG):
            self.mode = DISABLED
        self.base_url = (os.environ.get("IMD_API_BASE_URL") or "").strip()
        self.timeout_s = _bounded_int("IMD_TIMEOUT_SECONDS", 30, 2, 300)
        self.poll_interval_s = _bounded_float("IMD_POLL_INTERVAL_SECONDS",
                                              60.0, 5.0, 3600.0)
        self.max_retries = _bounded_int("IMD_MAX_RETRIES", 5, 0, 20)
        self.retry_base_s = _bounded_float("IMD_RETRY_BASE_SECONDS",
                                           2.0, 0.5, 120.0)
        self.stations = [s.strip().upper() for s in
                         (os.environ.get("IMD_STATION_ALLOWLIST") or "").split(",")
                         if s.strip()]
        self.expected_cadence_min = _bounded_float("IMD_EXPECTED_CADENCE_MIN",
                                                   180.0, 1.0, 1440.0)
        self.stale_after_multiples = _bounded_float("IMD_STALE_MULTIPLES",
                                                    3.0, 1.5, 24.0)
        self.history_maxlen = _bounded_int("IMD_HISTORY_MAXLEN", 500, 50, 5000)
        self.db_path = (os.environ.get("IMD_DB_PATH") or
                        "data/live/skyguard_live.sqlite").strip()

    def describe(self) -> dict:
        """Safe snapshot (credential presence only, never values)."""
        return {"mode": self.mode,
                "poll_interval_s": self.poll_interval_s,
                "timeout_s": self.timeout_s,
                "max_retries": self.max_retries,
                "expected_cadence_min": self.expected_cadence_min,
                "stale_after_multiples": self.stale_after_multiples,
                "stations": list(self.stations),
                "arg_configured": bool(os.environ.get("IMD_ARG_BASE_URL")),
                "wis2_configured": True}


def _bounded_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def _bounded_float(name: str, default: float, lo: float, hi: float) -> float:
    try:
        value = float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))
