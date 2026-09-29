"""Live observation sources: adapter contract + three implementations.

Adapters handle transport, parsing, units, timestamps, station IDs and
provenance ONLY. They never detect anomalies, never fill missing
values, never convert across pressure bases.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass, field

from src.data_sources.imd_wis2 import client as WC
from src.data_sources.imd_wis2 import normalizer as WN
from src.live import obs as LO

logger = logging.getLogger("skyguard.live_sources")

# Explicit capability map from the Phase 21A station audit
# (Backend/reports/imd_wis2/phase21a_station_audit.json). Only SYNOP
# variables actually observed are listed; dewpoint is never humidity
# and MSL pressure is never station pressure.
STATION_CAPABILITIES = {
    "PATNA": {"wigos_id": "0-20000-0-42492", "temperature": True,
              "humidity": False, "station_pressure": False,
              "latitude": 25.6, "longitude": 85.1667, "elevation_m": 57},
    "DELHI": {"wigos_id": "0-20000-0-42182", "temperature": True,
              "humidity": False, "station_pressure": False,
              "latitude": 28.6139, "longitude": 77.2090, "elevation_m": None},
    "KOLKATA": {"wigos_id": "0-20000-0-42809", "temperature": True,
                "humidity": False, "station_pressure": False,
                "latitude": 22.5726, "longitude": 88.3639, "elevation_m": None},
    "BENGALURU": {"wigos_id": "0-20000-0-43295", "temperature": True,
                  "humidity": False, "station_pressure": True,
                  "latitude": 12.9716, "longitude": 77.5946, "elevation_m": None},
    "PUNE": {"wigos_id": "0-20000-0-43063", "temperature": True,
             "humidity": False, "station_pressure": True,
             "latitude": 18.5204, "longitude": 73.8567, "elevation_m": None},
}


class SourceError(Exception):
    """Structured source failure (code, detail — never secrets)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class ObservationSource:
    """Adapter contract: fetch new canonical observations, describe self."""

    name: str = "base"

    def fetch_new(self) -> list[LO.CanonicalObservation]:
        """Observations since the last call (may be empty). Raises
        SourceError on transport failure; never returns fabricated rows."""
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name}


class IMDWIS2Source(ObservationSource):
    """Live IMD SYNOP observations via the audited WIS2 adapter.

    Polls the allowlisted WIGOS stations; each poll fetches the latest
    page and emits only records newer than the high-water mark (per
    station). Missing variables stay None per the audited roles.
    """

    name = "IMD_WIS2"

    def __init__(self, stations: list[str] | None = None,
                 client: WC.IMDWIS2Client | None = None,
                 timeout_s: int = 30) -> None:
        self.stations = [s for s in (stations or list(STATION_CAPABILITIES))
                         if s in STATION_CAPABILITIES]
        self.client = client or WC.IMDWIS2Client(timeout_s=timeout_s)
        self._seen: dict[str, set[str]] = {}

    def fetch_new(self) -> list[LO.CanonicalObservation]:
        out: list[LO.CanonicalObservation] = []
        for station in self.stations:
            try:
                page = self.client.get_observations(
                    STATION_CAPABILITIES[station]["wigos_id"], limit=100)
            except WC.IMDWIS2Error as exc:
                raise SourceError(exc.code, exc.detail) from None
            records = [WN.parse_record(f) for f in page.get("features", [])]
            seen = self._seen.setdefault(station, set())
            fresh = [r for r in records if r.record_id not in seen]
            for r in records:
                seen.add(r.record_id)
            out.extend(self._normalize(station, fresh))
        return out

    def _normalize(self, station: str,
                   records: list) -> list[LO.CanonicalObservation]:
        caps = STATION_CAPABILITIES[station]
        groups = WN.group_by_timestamp(records)
        normalized = []
        for stamp, group in groups.items():
            try:
                moment = WN.parse_utc(stamp)
            except (TypeError, ValueError):
                continue
            try:
                n = WN.normalize_group(station, station, moment.isoformat(),
                                       group, latitude=caps.get("latitude"),
                                       longitude=caps.get("longitude"),
                                       elevation=caps.get("elevation_m"))
            except WN.NormalizationError:
                continue
            humidity = n.relative_humidity_pct if caps["humidity"] else None
            pressure = n.pressure_hpa if caps["station_pressure"] else None
            normalized.append(LO.CanonicalObservation(
                station_id=f"IMD-{station}", timestamp=moment,
                temperature_c=n.temperature_c if caps["temperature"] else None,
                pressure_hpa=pressure, relative_humidity_pct=humidity,
                source="IMD_WIS2", source_station_id=station,
                source_observation_id=n.source_report_id,
                pressure_basis=("station_level" if caps["station_pressure"]
                                else "unavailable"),
                latitude=caps.get("latitude"), longitude=caps.get("longitude"),
                elevation=caps.get("elevation_m"), received_at=LO.utcnow(),
                raw_timestamp=stamp, raw={"report_id": n.source_report_id}))
        return sorted(normalized, key=lambda o: o.timestamp)

    def describe(self) -> dict:
        return {"name": self.name, "stations": list(self.stations),
                "capabilities": {s: {k: v for k, v in caps.items()
                                     if k in ("temperature", "humidity",
                                              "station_pressure")}
                                 for s, caps in STATION_CAPABILITIES.items()
                                 if s in self.stations}}


@dataclass
class IMDArgConfig:
    """AWS/ARG API contract (env-driven; disabled unless configured).

    No endpoint or credential is invented here: the operator provides
    IMD_ARG_BASE_URL (+ IMD_ARG_API_KEY when the deployment requires
    one). IP whitelisting, where required by IMD, is an operational
    prerequisite documented in the Phase 23 report.
    """

    base_url: str = ""
    api_key_present: bool = False
    timeout_s: int = 30
    stations: tuple = ()

    @classmethod
    def from_env(cls) -> "IMDArgConfig":
        return cls(
            base_url=(os.environ.get("IMD_ARG_BASE_URL") or "").strip(),
            api_key_present=bool(os.environ.get("IMD_ARG_API_KEY")),
            timeout_s=int(os.environ.get("IMD_TIMEOUT_SECONDS") or 30),
            stations=tuple(s.strip() for s in
                           (os.environ.get("IMD_STATION_ALLOWLIST") or "")
                           .split(",") if s.strip()))


class IMDArgSource(ObservationSource):
    """IMD AWS/ARG adapter (configuration contract only).

    Raises SourceError("not_configured") until the operator configures
    the endpoint; never fabricates observations, never disables TLS.
    """

    name = "IMD_ARG"

    def __init__(self, config: IMDArgConfig | None = None) -> None:
        self.config = config or IMDArgConfig.from_env()

    def fetch_new(self) -> list[LO.CanonicalObservation]:
        if not self.config.base_url:
            raise SourceError("not_configured",
                              "IMD AWS/ARG endpoint is not configured "
                              "(IMD_ARG_BASE_URL). Live ARG stays disabled.")
        raise SourceError("not_implemented",
                          "IMD AWS/ARG fetch is a configuration contract in "
                          "this phase; no demo traffic is synthesized.")

    def describe(self) -> dict:
        return {"name": self.name,
                "configured": bool(self.config.base_url),
                "stations": list(self.config.stations)}


@dataclass
class ControlledLiveSource(ObservationSource):
    """Scripted causal feed for tests and the controlled-live demo.

    Observations are released one poll at a time in script order (which
    must be chronological); the source never looks ahead. It is labeled
    CONTROLLED everywhere and must never be presented as IMD data.
    """

    name = "CONTROLLED"
    script: list = field(default_factory=list)
    _pos: int = 0

    def fetch_new(self) -> list[LO.CanonicalObservation]:
        if self._pos >= len(self.script):
            return []
        item = self.script[self._pos]
        self._pos += 1
        return [item]

    @property
    def exhausted(self) -> bool:
        return self._pos >= len(self.script)

    def describe(self) -> dict:
        return {"name": self.name, "scripted": len(self.script),
                "released": self._pos}
