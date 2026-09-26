"""LSTM temporal feature set: documented subset of the Phase 7 allowlist.

30 features covering core observations, cyclical time, first-order
dynamics, 2h local deviations, 2h trends, freeze/stability ratios, and
multivariate consistency. Every entry is a member of the frozen Phase 7
94-feature allowlist (same causal Phase 3 definitions).

Excluded from the allowlist with reasons:
- 30m/6h rolling baselines, deviations, trends: redundant with the 2h
  window at a 12-step lookback; keeps the input compact for CPU training.
- 2h prev_mean/std/median/mad raw baselines: levels are already carried by
  the core observations; deviations and trends encode the dynamics.
- temperature/pressure/humidity_rolling_std_2h and zero_delta flags:
  covered by zero_delta_ratio_2h and deviation features.
- No timestamp/provenance/gap/label columns were ever candidates.
"""

from __future__ import annotations

import pandas as pd

from src.isolation_forest.features import assert_no_forbidden_columns

LSTM_FEATURES: tuple[str, ...] = (
    "temperature_c",
    "pressure_hpa",
    "relative_humidity_pct",
    "hour_sin",
    "hour_cos",
    "day_of_year_sin",
    "day_of_year_cos",
    "temperature_delta",
    "temperature_rate_per_hour",
    "temperature_abs_rate_per_hour",
    "pressure_delta",
    "pressure_rate_per_hour",
    "pressure_abs_rate_per_hour",
    "humidity_delta",
    "humidity_rate_per_hour",
    "humidity_abs_rate_per_hour",
    "temperature_deviation_from_median_2h",
    "temperature_robust_deviation_2h",
    "pressure_deviation_from_median_2h",
    "pressure_robust_deviation_2h",
    "humidity_deviation_from_median_2h",
    "humidity_robust_deviation_2h",
    "temperature_trend_2h",
    "pressure_trend_2h",
    "humidity_trend_2h",
    "temperature_zero_delta_ratio_2h",
    "pressure_zero_delta_ratio_2h",
    "humidity_zero_delta_ratio_2h",
    "multivariate_max_abs_robust_deviation_2h",
    "multivariate_deviation_range_2h",
)

N_FEATURES = len(LSTM_FEATURES)


def validate_feature_schema(columns: list[str]) -> list[str]:
    """Assert the ordered LSTM feature set against a Phase 3 schema."""
    from src.isolation_forest.features import build_allowlist

    assert_no_forbidden_columns(pd.DataFrame(columns=list(columns)))
    allowlist = build_allowlist(list(columns))
    missing = [c for c in LSTM_FEATURES if c not in allowlist]
    if missing:
        raise ValueError(f"LSTM features outside Phase 7 allowlist: {missing}")
    return list(LSTM_FEATURES)


__all__ = ["LSTM_FEATURES", "N_FEATURES", "validate_feature_schema",
           "assert_no_forbidden_columns"]
