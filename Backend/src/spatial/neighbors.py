"""Deterministic geographic neighbor discovery from manifest coordinates."""

from __future__ import annotations

import pandas as pd

from src.spatial.distance import haversine_km

MAX_NEIGHBORS = 3
MAX_RADIUS_KM = 600.0


def pairwise_distances(stations: list[dict]) -> pd.DataFrame:
    """All ordered station pairs with great-circle distance (km)."""
    rows = []
    for a in stations:
        for b in stations:
            if a["ghcnh_id"] == b["ghcnh_id"]:
                continue
            rows.append({
                "target_station": a["ghcnh_id"],
                "neighbor_station": b["ghcnh_id"],
                "distance_km": round(haversine_km(a["lat"], a["lon"],
                                                  b["lat"], b["lon"]), 2),
            })
    frame = pd.DataFrame(rows).sort_values(
        ["target_station", "distance_km", "neighbor_station"]).reset_index(drop=True)
    frame["rank"] = frame.groupby("target_station").cumcount() + 1
    return frame


def select_neighbors(pairs: pd.DataFrame, k: int = MAX_NEIGHBORS,
                     radius_km: float = MAX_RADIUS_KM) -> pd.DataFrame:
    """Up to k nearest stations within radius; fewer when geography dictates.

    Deterministic: ordered by (distance, station ID). Never tuned: k and the
    radius are fixed constants, not fitted to any label.
    """
    sel = pairs[pairs["distance_km"] <= radius_km].copy()
    sel = sel[sel.groupby("target_station").cumcount() < k].reset_index(drop=True)
    sel["selected"] = True
    return sel
