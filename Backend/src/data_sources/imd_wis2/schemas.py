"""Typed records for the IMD WIS2 adapter (plain dataclasses)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImdStation:
    """One official catalogue entry (IDs preserved verbatim)."""

    wigos_id: str
    traditional_id: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    barometer_height: float | None = None
    facility_type: str | None = None
    territory: str | None = None
    status: str | None = None
    topics: tuple = ()


@dataclass(frozen=True)
class ImdRecord:
    """One raw SYNOP observation record (single variable)."""

    record_id: str
    wigos_id: str
    name: str
    value: float | None
    units: str | None
    phenomenon_time: str
    report_time: str | None
    report_id: str


@dataclass(frozen=True)
class NormalizedObservation:
    """One timestamp's grouped observation (missing stays None)."""

    timestamp: str
    station_id: str
    station_name: str
    temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    pressure_hpa: float | None = None
    source: str = "IMD_WIS2"
    source_station_id: str = ""
    source_variable_names: tuple = ()
    source_report_id: str = ""
    latitude: float | None = None
    longitude: float | None = None
    elevation: float | None = None
    provenance: dict = field(default_factory=dict)
