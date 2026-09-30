"""Judge-facing showcase artifacts (historical timelines, investigation hub).

Nothing in this package computes a new detector verdict: timelines are
either the stored frozen detector outputs (Delhi ensemble) or the
existing calibrated station detector run over that station's own real
history. Every artifact records the detector it came from and the window
it covers, so the API can be explicit when a verdict is unavailable.
"""
