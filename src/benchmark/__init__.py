"""Controlled fault-injection benchmark on real weather observations (Phase 5).

Ground truth for later detector/root-cause evaluation. NOT an ML model,
NOT fake weather: real Phase 2 observations with controlled,
recorded sensor-fault operations applied to COPIES.
"""

from src.benchmark.config import (
    BENCHMARK_VERSION,
    DEFAULT_SEED,
    FAULT_TYPES,
    LAYER_DATA_QUALITY,
    LAYER_ML_BENCHMARK,
)

__all__ = [
    "BENCHMARK_VERSION",
    "DEFAULT_SEED",
    "FAULT_TYPES",
    "LAYER_DATA_QUALITY",
    "LAYER_ML_BENCHMARK",
]
