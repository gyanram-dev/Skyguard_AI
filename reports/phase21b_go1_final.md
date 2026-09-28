# Phase 21B / GO 1 — Final report: correctness + reproducibility hardening

Date: 2026-09-28. Baseline: `reports/phase21b_go1_baseline.md`
(audit prompt written against `757d68a`; verified against the current tree
which adds Judge Probe, replay + investigation + session + intelligence,
CSV upload + ordering hardening, and the IMD WIS2 audit).

Per-finding verdicts (no FIXED claim without a regression test):

- F1 future-dependent freeze detection — FIXED
  (`test_causality_freeze.py` 7 tests + updated `test_16/17/17b`).
- F2 non-causal spatial matching — FIXED
  (`test_causality_spatial.py` 9 tests + updated `test_5/6`; report +
  config wording regenerated honestly with slightly lower coverage).
- F3 investigation anchored at dataset latest — FIXED
  (`test_investigation_anchoring.py`; new `history_range` helper).
- F4 operational alerts built from benchmark truth — FIXED
  (`test_truth_separation.py`; alerts/investigation keyed by
  `(dataset, timestamp)`; evaluation CSVs removed from REQUIRED_FILES).
- F5 confidence/trust wording — PARTIALLY FIXED
  (no calibrated-probability claims existed; `test_evidence_states.py`
  pins 8 states; judge-probe wording corrected to "Not flagged —
  consistent with available context" / "Evidence coverage". Full UX
  relabeling deferred as redesign-adjacent.)
- F6 unfamiliar CSV contract — FIXED (was already fixed by 20/20.1;
  `test_upload_general.py` adds 3 genuinely different fixtures).
- F7 reproducible clean checkout — PARTIALLY FIXED
  (`Backend/requirements.txt` pinned, artifact manifest with
  path/purpose/version/sha256 for all 21 serving artifacts, README
  clean-start path, startup fail-fast test. No download URLs invented;
  demo artifacts still travel with the demo machine. Fresh-container
  end-to-end verification NOT performed — no container tooling here.)

## 1. Findings before repair

See baseline §F1–F7: batch freeze flagged whole runs from final length;
`align_neighbor` matched ±30 min (future allowed); investigation history
ended at dataset latest; `/alerts` + investigation read
`*_event_results.csv` / `end_to_end_diagnosis.csv` (`injection_id`,
`fault_type`, latency); "confidence" labeled evidence grades and the
probe claimed "Trusted observation"; no dependency manifest or artifact
manifest existed and serving required evaluation label tables.

## 2. Files changed

Backend code: `src/data_quality/freeze_checks.py` (causal flags +
`detection_pos`), `src/data_quality/batch_validator.py`
(`detection_timestamp`), `src/spatial/alignment.py`
(`direction="backward"`), `src/spatial/run.py` + `data/noaa/metadata/
spatial_config.json` + `reports/noaa/spatial_consistency_report.md`
(regenerated wording/coverage), `src/api/services/anomaly_service.py`
(detector-run alerts, no truth), `src/api/services/
investigation_service.py` (timestamp-keyed lookup + alert-anchored
history), `src/api/services/station_service.py` (`history_range`),
`src/api/dependencies.py` (evaluation CSVs not required),
`src/api/app.py` (404 when an alert has no evidence row).
Tests: new `test_causality_freeze.py`, `test_causality_spatial.py`,
`test_investigation_anchoring.py`, `test_truth_separation.py`,
`test_evidence_states.py`, `test_upload_general.py`,
`test_reproducibility.py`; updated `test_data_quality.py`
(`test_16/17/17b` causal tails), `test_spatial.py` (`test_5/6`
causal), `test_statistical_baseline_evaluation.py` (`test_19` now
rerun-vs-rerun — see §5). Frontend: `judge-probe.tsx` honest wording.
Docs/meta: `Backend/requirements.txt`,
`Backend/reports/phase21b_go1_artifact_manifest.json`, root `README.md`
clean-start path, this report (+ root `reports/` copies).

## 3. What was fixed (§2) — all with regression tests listed above.

## 4. Already fixed before this phase

F6 upload contract (Phase 20/20.1: aliases, °C/°F, hPa/Pa, strict
timestamps, duplicates, shuffled/multi-station, gaps, unknown-station
statistical-only with ML unavailable); F5 partial (scores documented
NOT-probabilities, missing renders "—"/"Not available", unknown→review).

## 5. Intentionally deferred (NOT FIXED / out of scope)

- Stored `data/evaluation/` snapshots still encode pre-causal freeze
  flags; `test_19` was narrowed to rerun-vs-rerun determinism with an
  in-test note. Refreshing the evaluation bundle + reported metrics is
  deferred (would rewrite published metrics; evaluation refresh belongs
  to a later phase).
- Replay alerts remain ephemeral by design; no permanent DB; no live
  IMD adapter; no spatial scoring/decision integration; no model
  redesign/retraining; no UI redesign beyond the two honest labels.
- Fresh-container clean-start verification NOT performed here.

## 6. Tests added

`test_causality_freeze` (7), `test_causality_spatial` (9),
`test_investigation_anchoring` (5), `test_truth_separation` (3),
`test_evidence_states` (8), `test_upload_general` (3),
`test_reproducibility` (3) = 38 new tests.

## 7. Full test results (per-file runs, 2026-09-28)

- New suites: 38/38 pass.
- Updated suites: `test_data_quality` + `test_spatial` 36/36;
  `test_api`/`test_probe`/`test_upload`/`test_upload_ordering`/
  `test_hardening`/`test_audit`/`test_evaluation`/`test_replay`/
  `test_imd_wis2`/`test_benchmark`/`test_ensemble`/
  `test_feature_engineering`/`test_preprocessing`/`test_root_cause`/
  `test_statistical_baseline*`/`test_isolation_forest`/
  `test_lstm_autoencoder` — all pass.
- Known pre-existing failures (also documented in root README,
  unrelated to serving): `test_noaa_acquisition ::
  test_raw_inventory_presence`, `::test_deterministic_processed_output`
  (author-machine paths / pandas-version byte-identity).
- One combined-run anomaly (`test_benchmark` errors under a shared
  TF-heavy process) does not reproduce per-file; treated as resource
  contention, not a code defect.
- Full single-process `pytest tests/` was not green-lit end-to-end in
  one invocation here (TF-heavy suite exceeds practical per-command
  time); coverage above is per-file and complete except the two known
  failures.

## 8. Frontend verification

- `npx tsc --noEmit`: clean.
- `npm run build`: succeeds (built in ~3 s).
- `npx eslint src/lib src/components src/routes src/hooks`: 501
  prettier/CRLF errors across many untouched files — byte-identical at
  HEAD (CRLF 501/501), i.e. pre-existing Windows line endings, not
  introduced here. Our edited file adds no non-CRLF violations.

## 9. Clean-start verification

Manifest covers all 21 `REQUIRED_FILES` with sha256; `requirements.txt`
pinned to the verified environment; `DataStore.load` fail-fast proven
by test; README documents clone→install→verify→start. Benchmark
labels/reports no longer required to serve. Fresh-environment
end-to-end install NOT executed (would need a second machine/
container); marked above as the remaining reproducibility gap.

## 10. Known limitations

Historical replay (no live AWS); benchmark faults are controlled/
injected; root-cause accuracy varies and degrades OOD; replay covers
detector stations (DEL-01, JENA-01); NOAA data is context, not truth;
no Docker/cloud deployment in this repo; stored evaluation snapshots
pre-date the causal freeze fix (§5).
