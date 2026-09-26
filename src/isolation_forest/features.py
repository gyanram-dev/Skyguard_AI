"""Model input allowlist: documented, deterministic, label-free.

From the 106 Phase 3 columns, the model sees 94 numeric causal signals:
current observations, cyclical encodings, dynamics, frozen/stability
indicators, rolling baselines, deviations, trends, multivariate context.

Excluded with reasons:
- timestamp, source_dataset: non-numeric provenance, not predictors.
- 7 quality/missing flags: constant on DQ-eligible rows (all present).
- elapsed_minutes_since_prev, gap_before, segment_id: gap machinery;
  post-gap rows are DQ-ineligible, segment_id is an arbitrary integer.

Any benchmark label / evaluation / manifest column is FORBIDDEN and
rejected loudly (never silently dropped).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

OBS_COLS = ("temperature_c", "pressure_hpa", "relative_humidity_pct")

EXCLUDED_PROVENANCE = ("timestamp", "source_dataset")
EXCLUDED_QUALITY = (
    "temperature_missing", "humidity_missing", "pressure_missing",
    "any_core_missing", "missing_core_count", "valid_core_count", "all_core_valid",
)
EXCLUDED_GAP_META = ("elapsed_minutes_since_prev", "gap_before", "segment_id")

FORBIDDEN_SUBSTRINGS = (
    "ground_truth", "injection", "target_variable", "fault_type",
    "anomaly", "label", "manifest", "split",
)


def build_allowlist(feature_columns: list[str]) -> list[str]:
    """Deterministic allowlist from a 106-column Phase 3 schema."""
    excluded = set(EXCLUDED_PROVENANCE) | set(EXCLUDED_QUALITY) | set(EXCLUDED_GAP_META)
    kept = [c for c in feature_columns if c not in excluded]
    if len(feature_columns) == 106 and len(kept) != 94:
        raise ValueError(f"Expected 94 allowlisted features, got {len(kept)}")
    return kept


def assert_no_forbidden_columns(df: pd.DataFrame) -> None:
    """Raise if any label/evaluation/manifest column is present."""
    bad = [c for c in df.columns
           if any(s in c.lower() for s in FORBIDDEN_SUBSTRINGS)]
    if bad:
        raise ValueError(f"Forbidden label/evaluation columns in model input: {bad}")


def to_model_matrix(features: pd.DataFrame, allowlist: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Return (X, scorable_mask). Rows with NaN/inf are unscorable, never imputed."""
    assert_no_forbidden_columns(features)
    mat = features[allowlist].to_numpy(dtype=float)
    finite = np.isfinite(mat).all(axis=1)
    return mat, finite
