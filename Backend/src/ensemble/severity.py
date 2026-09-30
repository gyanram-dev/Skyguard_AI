"""Presentation-only severity bands for the calibrated ensemble verdict.

The frozen pipeline defines detection, not severity: a row is anomalous
when ``ens_median`` >= the frozen 99th-percentile clean-training threshold.
Severity is therefore reported as the ratio of the calibrated score to
that frozen threshold — a documented presentation band, mirrored from the
statistical detector's |z| bands and never used for detection.

The bands below are fixed (not tuned on labels); the ratio is the only
scale-free margin the frozen score supports. ``severity_basis`` explains
this in API responses.
"""

from __future__ import annotations

import math

# (ratio edge, band), evaluated high-to-low.
BANDS = (
    (2.5, "CRITICAL"),
    (1.75, "HIGH"),
    (1.25, "MEDIUM"),
    (1.0, "LOW"),
)

SEVERITY_BASIS = (
    "calibrated ensemble median / frozen 99th-percentile threshold ratio; "
    "presentation-only bands, not detection thresholds")

_RANK = {"NORMAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def severity_for(score: float | None, threshold: float | None,
                 flagged: bool) -> str | None:
    """Severity band for an ensemble verdict, or None without inputs.

    ``NORMAL`` when the row was not flagged; ``None`` when the frozen score
    or threshold is unavailable (an unavailable verdict never gets a band).
    """
    if not flagged:
        return "NORMAL"
    if score is None or threshold is None:
        return None
    if not math.isfinite(float(score)) or not math.isfinite(float(threshold)):
        return None
    if threshold <= 0.0:
        return None
    ratio = float(score) / float(threshold)
    for edge, label in BANDS:
        if ratio >= edge:
            return label
    return "LOW"


def rank(value: str | None) -> int:
    """Numeric rank of a severity band (unknown/None = -1)."""
    if value is None:
        return -1
    return _RANK.get(str(value).upper(), -1)
