"""Causal 12-step sequence construction with gap/eligibility safety.

Convention: the prediction at time t uses observations [t-11 .. t]
("12-step historical sequence"; NOT a fixed real-time duration since Jena
is 10-minute and Delhi is 5-minute cadence). No future row ever enters.

A target row is scorable only when all 12 rows share one Phase 3 segment,
are all ML-eligible, and have finite values on every LSTM feature.
Nothing is interpolated or forward-filled; invalid targets stay unscorable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LOOKBACK = 12


def valid_sequence_mask(segment_ids: np.ndarray, eligible: np.ndarray,
                        finite: np.ndarray, lookback: int = LOOKBACK) -> np.ndarray:
    """Boolean mask over target rows; True where [t-L+1 .. t] is fully valid."""
    n = len(segment_ids)
    seg_ok = np.ones(n, dtype=bool)
    elig_ok = np.ones(n, dtype=bool)
    fin_ok = np.ones(n, dtype=bool)
    for lag in range(lookback):
        seg_ok[lag:] &= segment_ids[lag:] == np.roll(segment_ids, lag)[lag:]
        elig_ok[lag:] &= np.roll(eligible, lag)[lag:].astype(bool)
        fin_ok[lag:] &= np.roll(finite, lag)[lag:]
    valid = seg_ok & elig_ok & fin_ok
    valid[: lookback - 1] = False
    return valid


def build_sequences(matrix: np.ndarray, valid: np.ndarray,
                    lookback: int = LOOKBACK) -> tuple[np.ndarray, np.ndarray]:
    """Stack valid (12, F) windows; return (X, target_positions)."""
    positions = np.flatnonzero(valid)
    if len(positions) == 0:
        return (np.empty((0, lookback, matrix.shape[1]), dtype=np.float32),
                positions)
    starts = positions - lookback + 1
    index = starts[:, None] + np.arange(lookback)[None, :]
    return matrix[index].astype(np.float32), positions


def prepare_frame(features: pd.DataFrame, quality: pd.DataFrame,
                  feature_list: list[str]) -> tuple[np.ndarray, np.ndarray,
                                                   np.ndarray, np.ndarray]:
    """Return (matrix, segment_ids, eligible, finite) for sequence building."""
    from src.lstm_autoencoder.features import assert_no_forbidden_columns

    assert_no_forbidden_columns(features)
    mat = features[feature_list].to_numpy(dtype=float)
    finite = np.isfinite(mat).all(axis=1)
    # Phase 3 deterministic segment boundaries (not a model input).
    segment_ids = np.asarray(features["segment_id"])
    eligible = (quality["ml_eligible"].to_numpy(dtype=int) == 1)
    return mat, np.asarray(segment_ids), eligible, finite
