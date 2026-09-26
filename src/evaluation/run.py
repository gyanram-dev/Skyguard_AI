"""Phase 6 entry point: evaluate the frozen statistical baseline on the benchmark.

Usage:
    python -m src.evaluation.run

Delegates to the statistical-baseline evaluator (the only evaluation
implemented). Trains no model; tunes no thresholds.
"""

from __future__ import annotations

from src.evaluation.statistical_baseline.run import run_evaluation

if __name__ == "__main__":
    run_evaluation()
