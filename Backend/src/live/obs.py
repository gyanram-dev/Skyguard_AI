"""Canonical live observation + data-quality states.

The adapter layer ends here: everything downstream (history, inference,
alerts) speaks CanonicalObservation only. Raw source fields are kept in
``raw`` for auditability; anomaly detection never lives in this module.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field

# Canonical core (SI units as stored).
# Row-level live data-quality states.
VALID = "VALID"
MISSING = "MISSING"
INVALID = "INVALID"
OUT_OF_ORDER = "OUT_OF_ORDER"
DUPLICATE = "DUPLICATE"
STALE = "STALE"
SOURCE_ERROR = "SOURCE_ERROR"
WARMING_UP = "WARMING_UP"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

# Source-silence states (station level, not row level).
DATA_SOURCE_STALE = "DATA_SOURCE_STALE"
COMMUNICATION_GAP = "COMMUNICATION_GAP"


@dataclass(frozen=True)
class CanonicalObservation:
    """One source observation in SkyGuard canonical form.

    Missing stays None (never zero, never "normal"). Pressure keeps its
    measured basis in ``pressure_basis`` and is never converted across
    bases.
    """

    station_id: str
    timestamp: dt.datetime  # timezone-aware UTC instant of observation
    temperature_c: float | None = None
    pressure_hpa: float | None = None
    relative_humidity_pct: float | None = None
    # Provenance (audit trail, never detection input).
    source: str = "UNKNOWN"
    source_station_id: str = ""
    source_observation_id: str = ""
    pressure_basis: str = "unknown"
    latitude: float | None = None
    longitude: float | None = None
    elevation: float | None = None
    received_at: dt.datetime | None = None
    raw_timestamp: str = ""
    source_status: str = ""
    raw: dict = field(default_factory=dict, compare=False)

    @property
    def obs_id(self) -> str:
        """Deterministic identity: source observation ID when the source
        provides one, otherwise source + station + timestamp + values."""
        if self.source_observation_id:
            seed = (f"{self.source}|{self.source_observation_id}")
        else:
            seed = ("|".join((self.source, self.station_id,
                               self.timestamp.isoformat(),
                               repr(self.temperature_c),
                               repr(self.pressure_hpa),
                               repr(self.relative_humidity_pct))))
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_utc_instant(text: str) -> dt.datetime:
    """Strict UTC instant parsing (naive input assumed UTC, documented)."""
    stamp = dt.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)
