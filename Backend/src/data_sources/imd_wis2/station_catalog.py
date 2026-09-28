"""Official station catalogue parsing (IDs preserved verbatim)."""

from __future__ import annotations

from src.data_sources.imd_wis2.schemas import ImdStation


def parse_station(feature: dict) -> ImdStation:
    """Parse one GeoJSON station feature (KeyError on malformed input)."""
    props = feature["properties"]
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates") or [None, None]
    topics = props.get("topics") or []
    if isinstance(topics, str):
        topics = [topics]
    return ImdStation(
        wigos_id=str(props["wigos_station_identifier"]),
        traditional_id=str(props["traditional_station_identifier"]),
        name=str(props.get("name") or props["traditional_station_identifier"]),
        latitude=float(coords[1]) if coords[1] is not None else None,
        longitude=float(coords[0]) if coords[0] is not None else None,
        barometer_height=float(props["barometer_height"])
        if props.get("barometer_height") is not None else None,
        facility_type=props.get("facility_type"),
        territory=props.get("territory_name"),
        status=props.get("status"),
        topics=tuple(topics),
    )


def parse_catalogue(page: dict) -> list[ImdStation]:
    """Parse one catalogue page (malformed features raise, never skipped)."""
    if not isinstance(page, dict) or not isinstance(page.get("features"), list):
        raise ValueError("Station catalogue page has no feature list.")
    return [parse_station(feature) for feature in page["features"]]


def find_by_traditional(stations: list[ImdStation], traditional_id: str) -> ImdStation | None:
    """Lookup by traditional identifier (exact match, no substitution)."""
    wanted = str(traditional_id).strip()
    for station in stations:
        if station.traditional_id == wanted:
            return station
    return None
