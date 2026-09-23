"""Deterministic Data Quality Layer for SkyGuard AI (Phase 2.5).

Answers: "Did this observation arrive correctly and is it structurally
valid enough to continue into the context/ML pipeline?"

Runs BEFORE any ML. No ML dependencies. Deterministic and explainable.
"""

from src.data_quality.quality_engine import (
    COMMUNICATION_GAP,
    DATA_AVAILABILITY_EVENT,
    DATA_INTEGRITY_FAULT,
    EXPECTED_INTERVAL_MIN,
    FREEZE_DURATION_HOURS,
    FREEZE_THRESHOLD_ROWS,
    PASS,
    PHYSICAL_SANITY_FAULT,
    POSSIBLE_FREEZE,
    QUALITY_STATES,
    StreamingQualityEngine,
    classify_quality_status,
)
from src.data_quality.timeline_checks import GAP_FACTOR

__all__ = [
    "EXPECTED_INTERVAL_MIN",
    "GAP_FACTOR",
    "FREEZE_DURATION_HOURS",
    "FREEZE_THRESHOLD_ROWS",
    "PASS",
    "DATA_AVAILABILITY_EVENT",
    "COMMUNICATION_GAP",
    "DATA_INTEGRITY_FAULT",
    "POSSIBLE_FREEZE",
    "PHYSICAL_SANITY_FAULT",
    "QUALITY_STATES",
    "StreamingQualityEngine",
    "classify_quality_status",
]
