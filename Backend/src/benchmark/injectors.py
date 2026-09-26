"""Pure fault-application functions.

Each injector takes clean numpy values for an event window and returns
(injected_values, metadata). No I/O, no RNG inside (parameters are
sampled by the caller), fully deterministic given inputs.

Humidity is never clipped: callers must validate the [0, 100] range via
`humidity_valid` and use rejection sampling instead.
"""

from __future__ import annotations

import numpy as np


def humidity_valid(values: np.ndarray) -> bool:
    """True when every value lies within [0, 100] (NaN fails)."""
    v = np.asarray(values, dtype=float)
    return bool(np.all(~np.isnan(v)) and np.all(v >= 0.0) and np.all(v <= 100.0))


def apply_spike(clean: np.ndarray, amplitude: float, direction: int) -> np.ndarray:
    """Add a constant signed offset over the (short) event window."""
    return np.asarray(clean, dtype=float) + direction * float(amplitude)


def apply_frozen(cleans: dict[str, np.ndarray], target_var: str) -> dict[str, np.ndarray]:
    """Hold the target variable at its window-start value; others untouched."""
    out = {k: np.asarray(v, dtype=float).copy() for k, v in cleans.items()}
    anchor = float(np.asarray(cleans[target_var], dtype=float)[0])
    out[target_var] = np.full_like(out[target_var], anchor)
    return out


def apply_drift(
    clean: np.ndarray,
    rate_per_hour: float,
    direction: int,
    elapsed_hours: np.ndarray,
) -> np.ndarray:
    """Progressive monotonic offset: rate * elapsed_hours * direction."""
    ramps = float(rate_per_hour) * np.asarray(elapsed_hours, dtype=float) * int(direction)
    if direction > 0:
        assert bool(np.all(np.diff(ramps) >= 0)), "drift ramp must be monotonic"
    else:
        assert bool(np.all(np.diff(ramps) <= 0)), "drift ramp must be monotonic"
    return np.asarray(clean, dtype=float) + ramps


def apply_cross_variable(
    cleans: dict[str, np.ndarray],
    rates_per_reading: dict[str, float],
) -> dict[str, np.ndarray]:
    """Progressive per-reading ramps on all three core variables.

    Temperature and humidity ramp upward together while pressure moves
    minimally/inconsistently: a controlled multivariate inconsistency,
    NOT a claim of physical impossibility.
    """
    out = {}
    for var, vals in cleans.items():
        arr = np.asarray(vals, dtype=float).copy()
        steps = np.arange(1, len(arr) + 1, dtype=float)
        out[var] = arr + float(rates_per_reading[var]) * steps
    return out
