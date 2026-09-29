"""Evidence-based operator recommendations (no automatic action).

One shared map from root-cause / quality outcome to a recommended human
review step. Used by probe, investigation, and upload analysis so every
surface says the same thing. Recommendations never claim hardware is
repaired; REGIONAL readings explicitly warn against blaming the sensor.
"""

from __future__ import annotations

SPIKE = ("Inspect the temperature sensor and its calibration; verify the "
         "reading against nearby stations before trusting it.")
FROZEN = ("Inspect sensor telemetry and verify physical sensor output; a "
          "stuck value suggests the instrument, not the weather.")
DRIFT = ("Schedule a calibration review; compare recent readings against "
         "reference instruments.")
CROSS = ("Cross-check the affected variables for a shared failure mode "
         "(power, exposure, housing) rather than a single-channel fault.")
COMMUNICATION = ("Check station connectivity and data transmission; this is "
                 "a data-delivery problem, not necessarily a faulty sensor.")
REGIONAL = ("Do not treat the target sensor as faulty solely from this "
            "observation; nearby stations report compatible behavior.")
UNKNOWN = ("Preserve the observation, review sensor quality and nearby "
           "station context, then verify the instrument before making a "
           "field adjustment.")
NORMAL = ("No action indicated; the observation is consistent with "
          "available context.")


def for_root_cause(predicted: str | None, contextual: str | None = None) -> str:
    """Recommendation for a root-cause class + spatial interpretation."""
    if contextual == "POSSIBLE_REGIONAL_EVENT":
        return REGIONAL
    name = str(predicted or "UNKNOWN").upper()
    if name == "SPIKE":
        return SPIKE
    if name in ("FROZEN", "FROZEN_SENSOR"):
        return FROZEN
    if name == "DRIFT":
        return DRIFT
    if name in ("CROSS", "CROSS_VARIABLE", "CROSS-VARIABLE"):
        return CROSS
    if name in ("MIXED", "UNKNOWN", "NONE", ""):
        return UNKNOWN
    return UNKNOWN


def for_quality_event(state: str) -> str:
    """Recommendation for a data-quality / availability outcome."""
    if str(state) in ("DATA_SOURCE_STALE", "COMMUNICATION_GAP", "STALE",
                      "SOURCE_ERROR"):
        return COMMUNICATION
    return UNKNOWN


def for_verdict(normal: bool) -> str:
    return NORMAL if normal else UNKNOWN
