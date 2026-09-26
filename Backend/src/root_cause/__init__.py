"""Post-detection root-cause diagnosis (Phase 11).

Classifies already-detected anomalies into SPIKE / FROZEN / DRIFT /
CROSS / MIXED / UNKNOWN and explains predictions. Never invents root
causes for normal observations; never modifies detector thresholds.
"""

__all__: list[str] = []
