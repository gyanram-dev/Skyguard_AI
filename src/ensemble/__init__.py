"""Calibrated multi-detector ensemble (Phase 10).

Combines statistical, Isolation Forest, and LSTM evidence after
train-only ECDF calibration. Score direction: HIGHER = MORE anomalous,
never a probability. NOAA stays contextual and out of the official score.
"""

__all__: list[str] = []
