"""Live ingestion configuration (environment-driven, no secrets in Git).

Source modes: DISABLED (default), CONTROLLED_LIVE (scripted causal feed,
no credentials), LIVE_IMD (configured IMD provider), LIVE_ARG (contract-gated).
The server always starts; live endpoints report LIVE_UNAVAILABLE with a
safe explanation when the mode cannot serve.
"""

from __future__ import annotations

import os
import json

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
        self.mode = (os.environ.get("LIVE_SOURCE_MODE") or
                     os.environ.get("IMD_SOURCE_MODE") or DISABLED).strip().upper()
        if self.mode not in (DISABLED, CONTROLLED_LIVE, LIVE_IMD, LIVE_ARG):
            self.mode = DISABLED
        self.provider = (os.environ.get("LIVE_PROVIDER") or "IMD_WIS2").strip().upper()
        if self.provider == "IMD":
            self.provider = "IMD_WIS2"
        self.base_url = (os.environ.get("IMD_BASE_URL") or
                         os.environ.get("IMD_API_BASE_URL") or "").strip()
        self.ca_bundle = (os.environ.get("IMD_CA_BUNDLE") or "").strip() or None
        self.request_headers = _request_headers()
        self.client_certificate = os.environ.get("IMD_CLIENT_CERT") or None
        self.client_key = os.environ.get("IMD_CLIENT_KEY") or None
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
        """Safe snapshot; never return provider credentials or header values."""
        return {"mode": self.mode,
            "provider": self.provider,
                "poll_interval_s": self.poll_interval_s,
                "timeout_s": self.timeout_s,
                "max_retries": self.max_retries,
                "expected_cadence_min": self.expected_cadence_min,
                "stale_after_multiples": self.stale_after_multiples,
                "stations": list(self.stations),
                "arg_configured": bool(os.environ.get("IMD_ARG_BASE_URL")),
                "provider_configured": bool(self.base_url),
                "request_auth_configured": bool(self.request_headers),
                "client_certificate_configured": bool(self.client_certificate)}

    def redact(self, message: str) -> str:
        secrets = list(self.request_headers.values())
        secrets.extend(os.environ.get(name, "") for name in (
            "IMD_API_KEY", "IMD_API_TOKEN", "IMD_CLIENT_SECRET",
            "IMD_ARG_API_KEY"))
        for secret in secrets:
            if secret:
                message = message.replace(secret, "[REDACTED]")
        return message


def _request_headers() -> dict[str, str]:
    """Read provider-documented HTTP headers without exposing their values."""
    raw = os.environ.get("IMD_REQUEST_HEADERS", "").strip()
    if not raw:
        return {}
    try:
        headers = json.loads(raw)
    except (TypeError, ValueError):
        raise ValueError("IMD_REQUEST_HEADERS must be a JSON object.") from None
    if (not isinstance(headers, dict)
            or any(not isinstance(k, str) or not isinstance(v, str)
                   for k, v in headers.items())):
        raise ValueError("IMD_REQUEST_HEADERS must map strings to strings.")
    return headers


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
