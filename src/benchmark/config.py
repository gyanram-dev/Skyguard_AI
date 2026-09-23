"""Benchmark configuration: seed, splits, cadence, parameter ranges.

Single source of truth for every numeric range. OOD ranges are
disjoint from TRAIN/ID ranges by construction (validated at runtime).
"""

from __future__ import annotations

BENCHMARK_VERSION = "1.0"
GENERATOR_NAME = "skyguard_benchmark_gen"

# Global deterministic seed (configurable via run_benchmark_pipeline(seed=...)).
DEFAULT_SEED = 26073

# Chronological split fractions of each dataset timeline.
SPLIT_FRACTIONS = {"train": 0.60, "test_in_distribution": 0.20, "test_generalization": 0.20}

# Native sampling cadence in minutes.
CADENCE_MIN = {"jena": 10, "delhi": 5}

# History required before an injection start so later Phase 3 features
# (6h causal windows: 36 Jena rows / 72 Delhi rows) remain computable.
HISTORY_ROWS = {"jena": 36, "delhi": 72}

# Fault-type vocabulary (row-level) and layers.
FAULT_TYPES = ("SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE", "SPIKE_PLUS_DRIFT")
LAYER_ML_BENCHMARK = "ML_BENCHMARK"
LAYER_DATA_QUALITY = "DATA_QUALITY"

CORE_VARS = ("temperature_c", "pressure_hpa", "relative_humidity_pct")

# --- Spike: absolute amplitude ranges + short durations (readings) ---
SPIKE_AMPLITUDE = {
    # variable -> {split_group: (min, max)} in native units
    "temperature_c": {"train_id": (15.0, 25.0), "ood": (30.0, 45.0)},
    "pressure_hpa": {"train_id": (8.0, 15.0), "ood": (20.0, 35.0)},
    "relative_humidity_pct": {"train_id": (15.0, 25.0), "ood": (30.0, 45.0)},
}
SPIKE_DURATION_READINGS = (1, 3)  # all splits

# --- Frozen: run lengths (readings) ---
FROZEN_DURATION = {"train_id": (3, 10), "ood": (15, 30)}

# --- Drift: rates per hour (native units) + durations (hours) ---
DRIFT_RATE_PER_HOUR = {
    "temperature_c": {"train_id": (0.5, 1.5), "ood": (2.0, 4.0)},
    "pressure_hpa": {"train_id": (1.0, 3.0), "ood": (5.0, 8.0)},
    "relative_humidity_pct": {"train_id": (2.0, 5.0), "ood": (8.0, 12.0)},
}
DRIFT_DURATION_HOURS = {"train_id": (6.0, 12.0), "ood": (4.0, 8.0)}

# --- Cross-variable: progressive per-reading ramps on all three vars ---
CROSS_DURATION = {"train_id": (3, 10), "ood": (15, 30)}
CROSS_RATES_PER_READING = {
    "train_id": {
        "temperature_c": (0.3, 0.8),
        "relative_humidity_pct": (0.5, 1.5),
        "pressure_hpa": (-0.3, 0.1),
    },
    "ood": {
        "temperature_c": (0.8, 1.5),
        "relative_humidity_pct": (1.5, 3.0),
        "pressure_hpa": (-0.8, -0.2),
    },
}

# --- Communication gaps: durations in minutes ---
GAP_DURATION_MIN = {"train_id": (30.0, 120.0), "ood": (120.0, 360.0)}

# --- Event count targets per dataset per split ---
TARGETS_PER_SPLIT = {
    "train": {"SPIKE": 30, "FROZEN": 30, "DRIFT": 30, "CROSS_VARIABLE": 30,
              "SPIKE_PLUS_DRIFT": 0, "COMMUNICATION_GAP": 20},
    "test_in_distribution": {"SPIKE": 30, "FROZEN": 30, "DRIFT": 30, "CROSS_VARIABLE": 30,
                             "SPIKE_PLUS_DRIFT": 0, "COMMUNICATION_GAP": 20},
    "test_generalization": {"SPIKE": 30, "FROZEN": 30, "DRIFT": 30, "CROSS_VARIABLE": 30,
                            "SPIKE_PLUS_DRIFT": 20, "COMMUNICATION_GAP": 20},
}

# Placement attempts per event before recording a skip.
MAX_PLACEMENT_ATTEMPTS = 300


def split_group(split: str) -> str:
    """Map a split name to its parameter group (train_id vs ood)."""
    if split == "test_generalization":
        return "ood"
    return "train_id"


def buffer_rows(split: str, dataset: str) -> int:
    """Minimum separation between independent events: max duration + 2h, in rows."""
    if split == "test_generalization":
        max_hours = DRIFT_DURATION_HOURS["ood"][1]  # 8h dominates OOD
    else:
        max_hours = DRIFT_DURATION_HOURS["train_id"][1]  # 12h dominates train/ID
    total_min = (max_hours + 2.0) * 60.0
    return int(round(total_min / CADENCE_MIN[dataset.lower()]))
