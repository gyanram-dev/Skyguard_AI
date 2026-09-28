# Phase 21B / GO 1 — Baseline: audit finding vs current implementation

Audit source: the Phase 21B prompt findings (written against commit
`757d68a`; the `SkyGuard_AI_Technical_Audit.md` file itself is not present
in the repository). Verified against the CURRENT tree, which additionally
contains Judge Probe, replay, replay investigation/session/intelligence,
CSV upload + ordering hardening, and the IMD WIS2 audit.

Status values: FIXED (already correct), PRESENT (defect confirmed),
PARTIAL (partly correct).

## F1. Future-dependent batch freeze detection — PRESENT

- Finding: batch freeze flags whole identical-value runs using final run
  length, so early rows are marked with future information.
- Current: `src/data_quality/freeze_checks.py::detect_frozen_runs_with_threshold`
  computes `max_len` over the full series, then flags every member row.
  `StreamingQualityEngine` is already causal (counter-at-check-time).
- Callers of the batch path: `batch_validator` → `prepare_split` →
  probe frames, replay frames, upload frames (DQ display/status only;
  freeze-flag columns are excluded from IF/LSTM/RC model inputs, so model
  scores are unaffected — only `quality_status`/reason timing changes).
- Already fixed: no.
- Planned repair: flag row *i* only when its causal run length at *i*
  reaches the threshold; report `detection_pos` separately from run
  `start_pos`. Update `test_16`, `test_17`, `test_17b` expectations that
  currently prove the non-causal behavior (documented in-test).
- Proving tests: prefix invariance, short/threshold/long runs, future-row
  append stability, batch-vs-streaming parity.

## F2. Non-causal spatial neighbor matching — PRESENT (offline only)

- Finding: `align_neighbor` uses nearest ±30 min, so a 12:00 target can
  match a 12:20 neighbor.
- Current: `src/spatial/alignment.py` `direction="nearest"`, used only by
  `src/spatial/evaluator.py` (offline frame builder). The serving API
  reads the frozen `spatial_consistency.csv` and never calls it, so live
  responses are unaffected; future offline runs and unit tests are.
- Already fixed: no.
- Planned repair: `direction="backward"` (neighbor ≤ target) with the
  same tolerance; keep distance/ranking/basis/stale semantics; update
  spatial alignment test expectations that prove nearest behavior.
- Proving tests: exact/previous/future-rejected/no-history/stale/
  multi-neighbor/ordering/prefix-invariance cases.

## F3. Investigation history anchored at dataset latest — PRESENT

- Finding: alert investigation history trails the dataset's latest
  timestamp instead of the alert timestamp.
- Current: `investigation_service.build_investigation` calls
  `station_service.history_series(..., "temperature", 24)`, whose window
  is `max(timestamp) - 24h`. Alert detail `history` therefore describes
  the wrong 24 hours for any non-latest alert.
- Already fixed: no.
- Planned repair: add `history_range(store, mapping, variable, end, hours)`
  and anchor investigation history at the alert timestamp (string-domain
  comparison inside the same dataset frame; no timezone arithmetic —
  Delhi/Jena frames are documented naive-local, NOAA UTC; the existing
  Delhi IST→UTC join for NOAA context stays untouched).
- Proving tests: old/recent/boundary alerts, replay-stored alerts N/A
  (live payload path), upload alerts N/A (no alert-detail endpoint).

## F4. Operational alerts built from benchmark truth — PRESENT

- Finding: `/alerts` derives from benchmark event tables/labels
  (`injection_id`, `fault_type`, detection counts, latency).
- Current: `anomaly_service.build_alerts` reads
  `reports/ensemble/*_event_results.csv` + `end_to_end_diagnosis.csv`;
  `investigation_service` looks rows up by `injection_id`.
- Already fixed: no.
- Planned repair: build operational alerts from frozen detector outputs
  only (`*_ensemble_predictions.csv`: `ens_median_flag` runs on
  evaluation-eligible rows; per-row RC lookup by timestamp where a
  diagnosis exists, else `review`/`None`); rewrite investigation lookup
  by `(dataset, timestamp)`; drop latency-vs-injection (needs labels).
  Remove the three evaluation CSVs from `DataStore.REQUIRED_FILES` so
  serving no longer requires benchmark labels/reports.
- Proving tests: labels-removed inference invariance (unit-level:
  operational builder never reads label columns), unlabeled anomalous
  row still alerts, alert/detail round-trip, sorted/unique invariants.

## F5. Confidence / trust wording — PARTIAL (no probability claims found)

- Finding: availability must not be sold as calibrated probability.
- Current: ensemble scores documented NOT-probabilities end to end;
  `EVIDENCE_COMPLETENESS` (1.0/0.67/0.33) is labeled "confidence" in
  station/probe payloads and rendered as "Confidence"/"Evidence
  confidence" — bounded evidence grades, never "99% probability".
  Missing scores render "—"/"Not available"/unavailable states;
  `normalizeStatus` maps unknown to `review` (never healthy).
- Already fixed: yes, except continued vigilance.
- Planned repair: wording audit only; add API tests pinning
  insufficient≠normal (offline/nulls), unknown→review mapping, and the
  no-`nan`-literals invariant in user-facing strings.

## F6. Unfamiliar CSV input contract — FIXED (Phase 20/20.1)

- Finding: arbitrary timestamped CSVs must work without source changes.
- Current: upload pipeline accepts aliases, °C/°F, hPa/Pa, ISO + strict
  timestamps (ambiguous rejected), duplicates, shuffled rows,
  multi-station files, missing values, gaps; unknown stations get
  statistical-only analysis with ML explicitly unavailable.
- Already fixed: yes (Phases 20/20.1 + 16 backend tests).
- Planned repair: 3 additional genuinely-different fixtures
  (unfamiliar names, different units, unfamiliar station) proving the
  same contract end to end.

## F7. Reproducible clean checkout — PRESENT (missing pieces)

- Finding: no clean-machine path exists.
- Current: no `requirements.txt`/`pyproject.toml`; no artifact manifest;
  `DataStore.REQUIRED_FILES` (24) forces evaluation CSVs for serving;
  startup fails fast but only at import/use time per missing file.
- Already fixed: no.
- Planned repair: pinned `Backend/requirements.txt`; committed
  `reports/phase21b_go1_artifact_manifest.json` (path/purpose/sha256 of
  serving-required artifacts); trim evaluation-only CSVs from required
  files (after F4); document clone→install→bootstrap→start in README.

## Tests proving each repair

- `tests/test_causality_freeze.py` (new): F1 cases 1–6.
- `tests/test_causality_spatial.py` (new): F2 cases 1–9.
- `tests/test_investigation_anchoring.py` (new): F3 cases 1,2,3,4,7
  (5 = live-payload path unchanged by construction; 6 = N/A, no
  upload alert-detail endpoint exists).
- Truth separation (F4): unit tests on the operational builder with
  label columns removed/renamed + unlabeled-anomaly alert test.
- Evidence states (F5): status-domain, null-rendering, no-nan tests.
- Input (F6): 3 new upload fixtures.
- Reproducibility (F7): manifest presence/content test + startup
  validation test (missing dir fails with exact causes).
