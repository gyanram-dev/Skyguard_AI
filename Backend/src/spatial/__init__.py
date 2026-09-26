"""Multi-station spatial-consistency evidence layer (Phase 8B).

Evidence signals only: how unusual is a target observation versus nearby
stations at approximately the same time. NOT a fault classifier; per-variable
signals are never combined into a final score here.
"""

from src.spatial.distance import haversine_km

__all__ = ["haversine_km"]
