# PS 26073 implementation matrix (final alignment pass)

Base: Phase 24 (`8c24c90`) plus the uncommitted 24.1/final deltas. A row is
marked implemented only when the backend produces the evidence; UI-only
claims are marked as gaps. Companion: `product_proof_matrix.md`
(measured demo evidence), `ps26073_gap_analysis.md` (verdicts).

## A. Input parameters (T/P/RH)

- Implementation: canonical `temperature_c / pressure_hpa /
  relative_humidity_pct` end to end (DQ, features, detectors, spatial,
  upload, live). No wind/rain/radiation inputs anywhere in scoring.
- Modules: `src/data_quality/*`, `src/features/*`, `src/api/services/scoring.py`
- API: `POST /api/v1/demo/probe`, `/stations/{id}/history`
- Page: Judge Probe ("Test an Observation"), station detail
- Evidence: probe submits only T/P/RH; feature schema frozen
- Gap: none. Action: none.

## B. Real-time detection

- Implementation: live ingestion manager (poll → causal history →
  inference → episodes) + WebSocket replay streaming + probe.
- Modules: `src/live/*`; API: `/api/v1/live/*`, `/api/v1/live` (WS replay)
- Page: Live (CONTROLLED LIVE / NOT_CONFIGURED states), Overview source badge
- Evidence: controlled demo run (`reports/phase23/live_demo_run.json`)
- Gap: no authorized IMD stream in this environment. Action: document;
  never fake.

## C. Sensor faults

- Implementation: statistical + IF + LSTM ensemble over T/P/RH.
- Page: probe, investigation model evidence. Gap: none. Action: none.

## D. Spike detection

- Implementation: ensemble deviation + SPIKE root-cause class.
- Evidence: spike probe → SPIKE with confidence; benchmark per-fault metrics.
- Gap: none. Action: none.

## E. Frozen-value detection

- Implementation: DQ frozen-run detector (causal, Go 1) gates quality
  status; `*_zero_delta` features feed detectors; FROZEN root-cause class.
- Modules: `src/data_quality/freeze_checks.py`
- Page: station "Freeze evidence" row; investigation DQ state
- Evidence: causal freeze regression tests; frozen runs surface as DQ state
- Gap: no dedicated freeze *score*; per-station freeze factor renders
  Unavailable. Action: honest wording kept; dedicated scoring deferred.

## F. Communication errors

- Implementation: `DATA_SOURCE_STALE`/gap DQ states + live silence guard;
  never classified as temperature anomalies.
- Page: Live status; station "Historical replay — no live link"
- Evidence: stale-event tests; controlled demo silence flag
- Gap: none. Action: none.

## G. Temporal patterns

- Implementation: causal rolling features, temporal baselines, LSTM-12
  lookback; investigation 24h history + temporal evidence items.
- Gap: none material. Action: none.

## H. Seasonal patterns

- Implementation: hour/day-of-year cyclical encodings in the frozen
  feature set (diurnal + annual response learned by IF/LSTM) + new
  read-only same-hour history reference (`src/seasonal/context.py`,
  causal, Delhi) shown on probe.
- Gap: no explicit seasonal baseline model. Action: documented; no new
  model built (scope/risk). Verdict: partially implemented.

## I. Multivariate consistency

- Implementation: canonical deviation features feed scoring; probe
  MULTIVARIATE EVIDENCE block; investigation item.
- Gap: multivariate payload not retained per historical alert
  (stated as unavailable there). Action: none (honest).

## J. Genuine weather vs sensor anomaly

- Implementation: Phase-22 `decide_context` (LOCAL_SENSOR_ANOMALY /
  POSSIBLE_REGIONAL_EVENT / unconfirmed); thresholds unchanged.
- Evidence: paired tests; probe `spatial_decision`; PS-example spike →
  LOCAL_SENSOR_ANOMALY (contradicted).
- Gap: only DEL-01 has detector+spatial together. Action: none.

## K. False-alarm minimization

- Implementation: calibrated ensemble median + multi-evidence decision;
  Evaluation page shows real P/R/F1/FPR/event-recall.
- Gap: none claimed beyond measured. Action: none.

## L. Confidence score

- Implementation: evidence-coverage grades (1.0/0.67/0.33/null) +
  classifier confidence; score and confidence kept distinct; missing →
  "Not available".
- Gap: grades are not calibrated probabilities (worded as such). Action: none.

## M. Explainable AI

- Implementation: frozen SHAP TreeExplainer per scored row + numbered
  evidence items; omitted (never faked) when absent.
- Gap: none. Action: none.

## N. Root-cause classification

- Implementation: frozen classifier (SPIKE/FROZEN/DRIFT/CROSS/UNKNOWN/
  MIXED rules); UNKNOWN is a valid outcome.
- Gap: accuracy varies by fault (see Evaluation). Action: none.

## O. Sensor health

- Implementation: station "Sensor health" (DQ, recent anomalies, freeze/
  drift availability, communication, spatial) + trust verdict; no 0–100
  score.
- Gap: none. Action: none.

## P. Sensor degradation

- Implementation: none (no predictive model).
- Action taken: evidence-based `maintenance_review` (trailing-30d
  episode counts → MAINTENANCE_REVIEW_RECOMMENDED / ELEVATED_WATCH /
  NO_ACTION_INDICATED / NOT_APPLICABLE), documented as not-a-prediction.
- Verdict: partially implemented (review signal, no forecasting).

## Q. Maintenance requirement

- Same as P: `recommended_action` mapping (SPIKE/FROZEN/DRIFT/COMM/
  REGIONAL) from one shared backend module, shown on probe +
  investigation + upload. Verdict: partially implemented.

## R. Corrected/imputed value

- Implementation: upload-analysis operator-approved correction
  (observed/suggested/reason), never silent.
- Gap: unavailable in probe/live paths (stated). Verdict: optional,
  implemented where it exists.

## S. Real-time alerts

- Implementation: triage queue (station/parameter/time/source/type/
  severity/score/confidence/root-cause/state) over historical + replay
  + persisted live episodes; OPEN INVESTIGATION flow.
- Gap: none. Action: none.

## T. Visualization

- Implementation: dashboard (map supporting, decision central),
  triage, evidence workspace, network, live, evaluation pages.
- Gap: desktop-first; mobile not a target (stated). Action: none.

## U. Scalability

- Implementation: 14-station Indian network, ~794k indexed rows,
  per-station bounded histories, single-loop ingestion.
- Gap: large-network load not measured (stated). Action: none.

## V. Practical deployment

- Implementation: FastAPI + React, env-configured, TLS enforced,
  `.env.example` contract, graceful live start/stop.
- Gap: local-only (stated, no cloud claim). Action: none.

## W. Edge/energy

- Implementation: none. Stated as future path; no ESP32 claim anywhere.
- Verdict: not implemented (suggested-only per PS).

## X. Anomaly-injected evaluation

- Implementation: frozen benchmark (ID/OOD splits, per-fault + event
  metrics) served verbatim on the Evaluation page (Delhi; Jena removed
  from product UI but artifacts retained for regression).
- Gap: none. Action: none.
