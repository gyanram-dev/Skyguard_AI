# Phase 22 / GO 2 — Final report: spatial context → decision integration

Starting commit: `f25c38c`. Baseline: `reports/phase22_go2_baseline.md`.
Go 1 is intact (one documented test-shape update in `test_probe.py`
§7, no Go 1 logic reopened).

## 1. Previous spatial architecture

Display-only neighbor evidence: offline median/MAD/robust-score frames
(`spatial_consistency.csv`, `aws_context_validation.csv`), a temp-only
frozen lookup at serving time, deterministic selection (k ≤ 3, 600 km),
causal backward alignment (30 min), altimeter-only pressure basis.
Nothing downstream of the ensemble read it (§I of the baseline).

## 2. New spatial decision policy

New pure module `Backend/src/spatial/decision.py`, applied AFTER the
base detector verdict inside the shared `scoring.score_position`
(so probe, replay, and batch inference share it; CSV calls the same
`decide_context` on its unavailable branch):

- Per-variable evidence (`variable_evidence`): neighbor median (≥1),
  MAD (≥2), robust_score = |Δ|/MAD; states SPATIAL_SUPPORTED (score ≤
  2.0) / SPATIAL_CONTRADICTED (score ≥ 3.0) / SPATIAL_INSUFFICIENT
  (<2 neighbors, MAD == 0, indeterminate band) / SPATIAL_UNAVAILABLE
  (none usable, target missing, pressure-basis mismatch). Per-neighbor
  supporting/contradicting lists via 2×/3× MAD bands.
- Contextual classification (`decide_context`): NORMAL (base normal —
  spatial never raises flags), LOCAL_SENSOR_ANOMALY (base anomalous +
  contradicted), POSSIBLE_REGIONAL_EVENT (base anomalous + supported,
  flag preserved), ANOMALY_WITHOUT_SPATIAL_CONFIRMATION (base anomalous
  + unavailable/insufficient), INSUFFICIENT_EVIDENCE (base
  insufficient). Temperature drives; humidity corroborates; serving
  pressure is always basis-mismatched → UNAVAILABLE.

## 3. Why this policy

Post-detector interpretation (not ensemble averaging) keeps detection
metrics untouched while making disagreement measurable; score bands
leave an indeterminate zone instead of knife-edge flips; regional
wording stays "possible" because neighbors are evidence, not truth.

## 4. Exact thresholds / configuration

`SUPPORT_SCORE_MAX = 2.0`, `CONTRADICT_SCORE_MIN = 3.0` (mirrors the
official `Z_THRESHOLD = 3.0`), `MIN_SCORABLE_NEIGHBORS = 2` (reuses
`MIN_NEIGHBORS_FOR_SCORE`), per-neighbor bands 2×/3× MAD; neighbor
selection unchanged (k ≤ 3, 600 km, backward 30 min); serving expected
count 4 (geography) over 3 mapped live stations (VIJP/VILK/VABP;
Safdarjung offline-only, so serving caps below HIGH — documented).
All pre-fixed conventions, never fitted to outcomes.

## 5. Causality rules

`gather_neighbor_values` uses Go 1 `align_neighbor` only (neighbor ≤
target); source rows sorted internally (order-invariant);
`test_6/7/8` prove future-rejection, exact-acceptance, determinism.

## 6. Neighbor selection

Unchanged code path (`neighbors.py` constants); serving subset =
mapped Delhi-context stations, sorted; Jena/unfamiliar stations = no
graph = UNAVAILABLE.

## 7. Variable compatibility

Temp primary; RH only when measured both sides (missing → UNAVAILABLE,
temp still decides); pressure serving-side always UNAVAILABLE with
`pressure_basis_mismatch`; altimeter-vs-altimeter allowed only via
explicit `pressure_compatible=True` (paired tests).

## 8. Paired-test results

Identical target, neighbors vary → interpretation changes, every time:
spike 55 °C (local vs regional), moderate 38 °C (local vs regional),
humidity (contradicted vs supported), pressure compatible-basis
(contradicted vs supported), plus no/stale/one/two/conflicting/mixed
cases (`test_spatial_decision.py`, 23 tests, all pass).

## 9. Benchmark comparison (Delhi held-out, new files only)

`Backend/reports/phase22/spatial_decision_evaluation.{json,md}` —
flags identical by construction (P/R/F1/FPR/event-recall/delay
unchanged: ID F1 0.0802, event recall 0.517; OOD F1 0.2164, event
recall 0.671; FP/station-day 6.43 / 9.01). Measured contribution is
interpretive: of base-flagged true fiducials, ID → 61 local / 80
regional-supported / 62 unconfirmed; OOD → 355 local / 86 regional /
381 unconfirmed. Honest reading: discrimination added, raw recall not
improved (and not claimed).

## 10. False-positive behavior

Unchanged counts (flags preserved); FP rows receive interpretations
like any flagged row; NORMAL rows stay NORMAL (spatial never flags).

## 11. Known limitations

Jena has no neighbor graph; serving caps at MEDIUM (4th station
offline-only); RH coverage follows measurement availability; stored
`data/evaluation/` snapshots still pre-date Go 1 (see Go 1 report §5);
fresh-container verification not performed; no new ML, DB, live
connector, or redesign (per scope).

## 12. Next phase leaves

Freeze/drift redesign, persistence, live IMD integration — not started.

## Tests / verification

- New `test_spatial_decision.py` (23 tests) + eval script pass.
- Updated `test_probe.py::test_12` (schema-stable nulls, documented
  in-test): probe suite 9/9 with the new file (32/32 combined).
- Regression: api/replay/evidence/upload(+ordering/general)/
  truth/anchoring/causality suites all pass; `tsc` clean; `npm run
  build` succeeds; eslint shows only the pre-existing repo-wide CRLF
  class (byte-identical at HEAD) — the one new long JSX line was
  wrapped and is clean.
- Go 1 suites untouched and passing; full single-process backend run
  remains impractical here (TF-heavy), coverage is per-file as in Go 1.
