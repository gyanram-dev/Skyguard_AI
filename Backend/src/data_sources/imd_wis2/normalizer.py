"""Normalize IMD SYNOP records to SkyGuard canonical observations.

Variable roles (audited Phase 21A, never guessed):
- temperature ... air_temperature only
- humidity ...... actual RH observation only (dewpoint is NOT humidity;
  no dew-point conversion exists in this phase)
- pressure ...... non_coordinate_pressure only (station level);
  pressure_reduced_to_mean_sea_level is MSL and never substitutes

Units: Celsius -> C, hPa -> hPa, Fahrenheit/Pa converted when actually
seen. Unknown units raise instead of guessing. Missing stays None;
records group by report timestamp; UTC stays UTC (no local conversion).
"""

from __future__ import annotations

import datetime as dt
import logging
import math

from src.data_sources.imd_wis2.schemas import ImdRecord, NormalizedObservation

logger = logging.getLogger("skyguard.imd_wis2")

TEMPERATURE_NAMES = {"air_temperature"}
HUMIDITY_NAMES: set[str] = set()
PRESSURE_STATION_NAMES = {"non_coordinate_pressure"}
PRESSURE_MSL_NAMES = {"pressure_reduced_to_mean_sea_level"}


class NormalizationError(Exception):
    """Unusable record/variable (message only, no payload dump)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def parse_record(feature: dict) -> ImdRecord:
    """Parse one GeoJSON observation feature (KeyError/typed errors propagate)."""
    props = feature["properties"]
    value = props.get("value")
    number = None
    if value is not None:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            number = None
    return ImdRecord(
        record_id=str(props.get("id") or feature.get("id") or ""),
        wigos_id=str(props["wigos_station_identifier"]),
        name=str(props["name"]),
        value=number,
        units=str(props["units"]) if props.get("units") is not None else None,
        phenomenon_time=str(props["phenomenonTime"]),
        report_time=str(props["reportTime"]) if props.get("reportTime") is not None else None,
        report_id=str(props.get("reportId") or ""),
    )


def parse_utc(text: str) -> dt.datetime:
    """Timezone-aware UTC instant (naive input assumed UTC, documented)."""
    stamp = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def to_celsius(value: float, units: str | None, name: str) -> float:
    """Verified temperature units only (anything else raises)."""
    unit = (units or "").strip().lower()
    if unit in ("celsius", "c", "degc"):
        return float(value)
    if unit in ("fahrenheit", "f", "degf"):
        return (float(value) - 32.0) * 5.0 / 9.0
    raise NormalizationError(f"Unsupported temperature unit '{units}' for '{name}'.")


def to_hpa(value: float, units: str | None, name: str) -> float:
    """Verified pressure units only (anything else raises)."""
    unit = (units or "").strip().lower()
    if unit in ("hpa", "hectopascal"):
        return float(value)
    if unit in ("pa", "pascal"):
        return float(value) / 100.0
    raise NormalizationError(f"Unsupported pressure unit '{units}' for '{name}'.")


def normalize_group(station_id: str, station_name: str, timestamp: str,
                    records: list[ImdRecord], latitude: float | None = None,
                    longitude: float | None = None,
                    elevation: float | None = None) -> NormalizedObservation:
    """Group one timestamp's records (first value wins per variable)."""
    temperature, humidity, pressure = None, None, None
    names: list[str] = []
    provenance: dict = {}
    for record in sorted(records, key=lambda r: r.record_id):
        names.append(record.name)
        if record.value is None:
            continue
        if record.name in TEMPERATURE_NAMES and temperature is None:
            temperature = to_celsius(record.value, record.units, record.name)
            provenance["temperature"] = {"variable": record.name,
                                         "units": record.units,
                                         "report_id": record.report_id}
        elif record.name in HUMIDITY_NAMES and humidity is None:
            humidity = float(record.value)
            provenance["humidity"] = {"variable": record.name,
                                      "units": record.units,
                                      "report_id": record.report_id}
        elif record.name in PRESSURE_STATION_NAMES and pressure is None:
            pressure = to_hpa(record.value, record.units, record.name)
            provenance["pressure"] = {"variable": record.name,
                                      "units": record.units,
                                      "report_id": record.report_id}
    return NormalizedObservation(
        timestamp=timestamp, station_id=station_id, station_name=station_name,
        temperature_c=temperature, relative_humidity_pct=humidity,
        pressure_hpa=pressure, source="IMD_WIS2",
        source_station_id=station_id, source_variable_names=tuple(names),
        source_report_id=records[0].report_id if records else "",
        latitude=latitude, longitude=longitude, elevation=elevation,
        provenance={**provenance, "record_count": len(records)},
    )


def group_by_timestamp(records: list[ImdRecord]) -> dict[str, list[ImdRecord]]:
    """Group records by phenomenon time (insertion order kept)."""
    groups: dict[str, list[ImdRecord]] = {}
    for record in records:
        groups.setdefault(record.phenomenon_time, []).append(record)
    return groups
