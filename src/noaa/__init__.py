"""NOAA multi-station data acquisition + audit for SkyGuard AI (Phase 8A).

Acquisition and audit ONLY. No spatial anomaly detection, no modeling.
"""

from src.noaa.config import DATASET_NAME, DATASET_VERSION

__all__ = ["DATASET_NAME", "DATASET_VERSION"]
