"""Hard physical sanity checks.

Only genuinely station-independent impossibilities are flagged:

- relative humidity < 0 or > 100  -> PHYSICAL_SANITY_FAULT
- non-finite core values (+/-inf) -> PHYSICAL_SANITY_FAULT
- non-numeric core values          -> PHYSICAL_SANITY_FAULT

Deliberately ABSENT (by design, see DECISIONS.md):
- no pressure thresholds (NOT 950/1030 hPa)
- no temperature range rejection (55 C passes)
- no station-specific calibration limits

NaN (missing) is NOT a sanity fault; it is a data-availability event
handled by the missingness logic.
"""

from __future__ import annotations

import math

import pandas as pd


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def is_physical_sanity_fault(
    temperature_c: object,
    pressure_hpa: object,
    relative_humidity_pct: object,
) -> tuple[bool, str]:
    """Return (fault, reason) for one observation's physical sanity.

    Reason is an empty string when there is no fault.
    """
    for name, value in (
        ("temperature_c", temperature_c),
        ("pressure_hpa", pressure_hpa),
        ("relative_humidity_pct", relative_humidity_pct),
    ):
        if value is None or _is_missing(value):
            continue  # missing -> availability event, not sanity fault
        try:
            v = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return True, f"non_numeric_{name}"
        if math.isinf(v) or math.isnan(v):
            if math.isinf(v):
                return True, f"non_finite_{name}"
            continue
    # Relative humidity is a percentage with hard physical bounds.
    if relative_humidity_pct is not None and not _is_missing(relative_humidity_pct):
        rh = float(relative_humidity_pct)  # type: ignore[arg-type]
        if rh < 0:
            return True, "relative_humidity_below_zero"
        if rh > 100:
            return True, "relative_humidity_above_100"
    return False, ""
