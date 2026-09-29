"""Deterministic Indian station registry + neighbor graph.

Neighbors come from coordinates through the existing spatial selection
(``pairwise_distances`` / ``select_neighbors``: k <= 3, 600 km —
Phase 22 policy, thresholds untouched). Per-pair variable
compatibility: temperature where both sides measure it, RH only where
both sides measure it, pressure only on equal bases. Jena is never a
registry member.
"""

from __future__ import annotations

import pandas as pd

from src.spatial import neighbors as NB

# Registry membership: audited Indian data stations only.
OPERATIONAL = "operational"
DATA_AVAILABLE_UNMAPPED = "data_available_unmapped"
LIVE_CAPABLE = "live_capable"

# Frontend-mapped stations (existing station_mapping.json IDs).
MAPPED = {"DELHI-AWS", "INI0000VIJP", "INI0000VILK", "INI0000VABB",
          "INI0000VABP", "INI0000VOBL", "INI0000VOMM", "INU042809-1"}


def _registry_members(inventory: list[dict]) -> list[dict]:
    members = []
    for entry in inventory:
        sid = entry["station_id"]
        if entry["source_status"] == "benchmark_internal":
            continue
        if entry["source"] == "IMD_WIS2":
            status = LIVE_CAPABLE
        elif sid in MAPPED:
            status = OPERATIONAL
        else:
            status = DATA_AVAILABLE_UNMAPPED
        members.append({"entry": entry, "status": status})
    members.sort(key=lambda m: m["entry"]["station_id"])
    return members


def _pairwise(members: list[dict]) -> pd.DataFrame:
    """Reuse the frozen neighbor selection on registry coordinates."""
    stations = [{"ghcnh_id": m["entry"]["station_id"],
                 "lat": m["entry"]["latitude"],
                 "lon": m["entry"]["longitude"]}
                for m in members
                if m["entry"]["latitude"] is not None
                and m["entry"]["longitude"] is not None]
    pairs = NB.pairwise_distances(stations)
    return NB.select_neighbors(pairs)


def _compatible(a: dict, b: dict, variable: str) -> bool:
    if variable == "temperature":
        return bool(a["temperature_available"] and b["temperature_available"])
    if variable == "humidity":
        return bool(a["relative_humidity_available"]
                    and b["relative_humidity_available"])
    if variable == "pressure":
        return bool(a["pressure_available"] and b["pressure_available"]
                    and a["pressure_basis"] == b["pressure_basis"])
    return False


def build_registry(inventory: list[dict]) -> dict:
    """Registry dict (deterministic): stations + neighbor edges."""
    members = _registry_members(inventory)
    by_id = {m["entry"]["station_id"]: m for m in members}
    selected = _pairwise(members)
    edges: dict[str, list] = {m["entry"]["station_id"]: [] for m in members}
    for _, row in selected.iterrows():
        target, nid = row["target_station"], row["neighbor_station"]
        if target not in by_id or nid not in by_id:
            continue
        a, b = by_id[target]["entry"], by_id[nid]["entry"]
        edges[target].append({
            "neighbor_id": nid,
            "distance_km": float(row["distance_km"]),
            "rank": int(row["rank"]),
            "temperature_compatible": _compatible(a, b, "temperature"),
            "humidity_compatible": _compatible(a, b, "humidity"),
            "pressure_compatible": _compatible(a, b, "pressure"),
        })
    stations = []
    for m in members:
        entry = m["entry"]
        stations.append({
            "station_id": entry["station_id"],
            "name": entry["station_name"],
            "latitude": entry["latitude"], "longitude": entry["longitude"],
            "region": _region(entry),
            "source": entry["source"],
            "available_variables": sorted(
                v for v, ok in (("temperature",
                                 entry["temperature_available"]),
                                ("relative_humidity",
                                 entry["relative_humidity_available"]),
                                ("pressure", entry["pressure_available"]))
                if ok),
            "pressure_basis": entry["pressure_basis"],
            "operational_status": m["status"],
            "data_coverage": {"start": entry["coverage_start"],
                              "end": entry["coverage_end"],
                              "records": entry["record_count"],
                              "cadence_min": entry["cadence_min"]},
            "spatial_neighbors": edges[entry["station_id"]],
        })
    return {"version": "phase24-v1", "stations": stations,
            "selection": {"k_maximum": NB.MAX_NEIGHBORS,
                          "radius_km": NB.MAX_RADIUS_KM,
                          "note": "Phase 22 spatial policy, unchanged"}}


def _region(entry: dict) -> str:
    if entry["station_id"] == "DELHI-AWS":
        return "North"
    if entry["source"] == "IMD_WIS2":
        return {"IMD-PATNA": "East", "IMD-DELHI": "North",
                "IMD-KOLKATA": "East", "IMD-BENGALURU": "South",
                "IMD-PUNE": "West"}.get(entry["station_id"], "India")
    return str(entry.get("region", "India"))
