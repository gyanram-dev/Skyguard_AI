# Phase 22 / GO 2 — Baseline: spatial context before decision integration

Starting commit: `f25c38c`. Go 1 is complete and is not reopened by this
phase (causal freeze flags, causal backward alignment, alert-anchored
history, truth-separated alerts, honest evidence states all stand).

## A. What spatial signals currently exist?

Per (target, timestamp) rows in two frozen offline frames:

- `Backend/data/noaa/processed/spatial_consistency.csv` — every NOAA
  station vs its selected neighbors: per variable `target`,
  `neighbor_median`, `difference`, `abs_difference`, `robust_score`,
  `neighbor_count`, `context`, plus `available_neighbor_count` and
  `temporal_alignment_status`.
- `Backend/reports/noaa/aws_context_validation.csv` — every Delhi AWS
  row vs 4 NOAA Delhi-context stations: `ctx_temp_*` and `ctx_rh_*`
  (median/difference/robust_score/station_count/context) plus
  `ctx_altimeter_median_hpa` / `ctx_altimeter_station_count` (median
  only, never differenced).
- Serving-time (`scoring.score_position`): a temp-only lookup
  (`noaa_lookup`) of that CSV by Delhi IST timestamp → `{available,
  neighbor_count, context, reference_median, probe_difference}`.
  RH columns exist in the CSV but are not loaded at serving time.

## B. Which variables have spatial context?

Temperature and relative humidity (median + MAD score + count +
context). Pressure: altimeter median + count only — no score, by rule.

## C. How are neighbors selected?

`src/spatial/neighbors.py`: deterministic ordered pairs by
`(distance_km, station ID)`; `select_neighbors` keeps up to
`MAX_NEIGHBORS = 3` within radius. Delhi AWS context =
`DELHI_NOAA_ID + sel_by_target[DELHI_NOAA_ID]` = 4 stations
(`INI0000VIDD, INI0000VIJP, INI0000VILK, INI0000VABP`).

## D. Maximum allowed distance?

`MAX_RADIUS_KM = 600.0`. Fixed constant, tuned against nothing.

## E. Temporal alignment?

`align_neighbor`: causal backward-only, neighbor ≤ target within
`TIME_TOLERANCE = 30 min` (Go 1). UTC throughout; Delhi IST − 5:30.

## F. Stale/missing neighbor handling?

No match → position −1 → NaN → excluded from median/MAD; per-variable
context degrades UNAVAILABLE (0 neighbors / missing target) →
LOW (1 neighbor or MAD == 0) → MEDIUM (≥2 but < expected) → HIGH (all
expected + valid score). No interpolation, no fill, ever.

## G. Pressure basis?

Altimeter (QNH, hPa) ONLY. `station_level_pressure` and
`sea_level_pressure` never enter a comparison; Delhi AWS station
pressure is reported beside the altimeter median but never
differenced (`build_aws_validation` docstring + config
`pressure_basis_note`).

## H. MAD/reference calculation?

`reference.py`: median needs ≥1; MAD = median(|n_i − median|) needs ≥2,
else NaN. `scoring.score_variable`: robust_score = |target − median| /
MAD; NaN when <2 neighbors or MAD == 0. Higher = stronger
inconsistency; NOT a probability.

## I. Is spatial evidence currently used in …?

- ensemble score: NO (`aggregation.combine` sees only
  statistical/IF/LSTM).
- anomaly decision: NO (`is_anomalous` ignores spatial).
- root cause: NO (classifier inputs are detector features only).
- explanation: only as one descriptive sentence
  (`EX.noaa_sentence_for`), no decision weight.
- replay/probe: displayed (`reference_median`, `probe_difference`,
  `context`), never decisive.

## J. Which stations have valid spatial context?

DEL-01 (Delhi): temp (+RH offline) vs up to 4 NOAA stations; median
usable-neighbor counts 3/3 (temp/RH). JENA-01: none (single-station
climate dataset, no neighbor graph — honest gap). NOAA frontend
stations: observations + spatial display only, no detectors. Uploaded /
unfamiliar stations: spatial honestly UNAVAILABLE.

Serving-store caveat: `DataStore` loads 7 mapped NOAA stations;
`INI0000VIDD` (Delhi/Safdarjung) is offline-only, so live serving can
align at most 3 Delhi-context neighbors (VIJP, VILK, VABP) — still ≥
the 2-neighbor scoring minimum.

## K. What happens with zero neighbors?

`score_variable` → UNAVAILABLE with all-NaN reference/score; serving
`spatial = {available: False, neighbor_count: 0}`; the anomaly
decision is unchanged (spatial is display-only today).

## Implication for this phase

The gap is real: neighbor agreement cannot change any interpretation
today. The fix is a deterministic post-detector contextual layer
(`src/spatial/decision.py`, new) reusing `align_neighbor`,
`neighbor_median`/`neighbor_mad`, and the HIGH/MEDIUM/LOW/UNAVAILABLE
taxonomy — no new ML, no ensemble averaging, no label contact, causal
by construction. Proving tests: `tests/test_spatial_decision.py`.
