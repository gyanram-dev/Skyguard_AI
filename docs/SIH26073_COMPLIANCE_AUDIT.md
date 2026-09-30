# SKYGUARD AI — SIH 2026 PS 26073 Compliance Audit

**Problem statement:** SIH26073 — AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations (AWS)
**Audit date:** 2026-09-30
**Auditor method:** static inspection of executable code, live execution against the running backend
(`127.0.0.1:8000`) and frontend (`localhost:3000`), a fresh test run, and read-back of the frozen
benchmark/evaluation artifacts committed in the repository. No code was changed by this audit.

Statuses used (no subjective scores): **IMPLEMENTED**, **PARTIALLY IMPLEMENTED**, **NOT IMPLEMENTED**,
**INSUFFICIENT EVIDENCE**.

**What was actually executed during this audit (2026-09-30):**

| Action | Result |
|---|---|
| `GET /api/v1/demo/readiness` | `ready: true`, `replay_available: true`, `probe_available: true`, `evaluation_available: true` |
| `GET /api/v1/stations` | 14 stations: 1 ensemble (DEL-01), 10 calibrated statistical detectors, 3 context-only |
| `POST /api/v1/demo/probe` DEL-01 (48.7 °C spike) | `is_anomalous: true`, score 0.99995 vs threshold 0.97830, availability `FULL_EVIDENCE`, root cause `SPIKE` 0.798 (runner-up `CROSS`), real SHAP top-5 list, spatial `LOCAL_SENSOR_ANOMALY` |
| `POST /api/v1/demo/probe` MUM-03 | HTTP 422 `insufficient_context` — probe refuses stations not covered by the frozen Delhi ensemble |
| WS `/api/v1/live` replay MUM-03 (`HISTORICAL`, 900×, limit 60) | 60 observations, 29 anomaly alerts, first alert severity `LOW`, confidence 0.5022, score 3.0268, reason `SPIKE: abrupt 8.0 robust-deviation jump within 2h; max|z|=3.03`, `alerts_recorded: 29`, `REPLAY_COMPLETE` in 121,441 ms |
| Upload E2E: 200-row clean CSV with one injected 58 °C spike | 1 anomaly, root-cause estimate `SPIKE`, correction suggestion 58.0 → 20.8 ("last valid observation before the spike; operator approval required") |
| `pytest -q tests/test_detection_mvp.py test_api.py test_indian_network.py test_evidence_states.py test_final_alignment.py test_replay.py` | **72 passed** in 438.96 s |
| `GET /api/v1/live/status` | `LIVE_UNAVAILABLE` / `NOT_CONFIGURED` (live ingestion disabled in this environment) |
| Edge-artifact search (`*.tflite *.onnx *.pte *.pb *.engine`, excluding `.venv`) | **zero files** |

---

## Requirement Compliance Table

| Requirement | Status | Evidence | Gap |
|---|---|---|---|
| **A. DATA** | | | |
| Temperature °C input | IMPLEMENTED | Delhi AWS `AWS_20220401_20241231.csv` 289,728 rows @5 min; GHCNh 10 calibrated stations ≈52 K obs each @30 min; benchmark CSVs `Backend/data/benchmark/{delhi,jena}/`; all carry `temperature_c` | — |
| Relative humidity % input | IMPLEMENTED | `relative_humidity_pct` in every dataset and in probe (`humidity`), live, upload; upload validates RH range 0–100 (`rh_invalid`) | GHCNh RH provenance documented as `REPORTED (provider file; measured-vs-calculated not verifiable)` — must not be presented as measured humidity |
| Pressure hPa input | IMPLEMENTED | `pressure_hpa` everywhere; probe requires it | — |
| Pressure semantics (station vs altimeter) | IMPLEMENTED | DEL-01/live = `station_level_hpa`; GHCNh = `altimeter_qnh_hpa` (`Backend/data/detectors/registry.json`); spatial explicitly returns `pressure_basis_mismatch: station pressure is never compared against altimeter data`; probe card labels QNH | Different bases are never compared, which is honest but means cross-source pressure logic is limited to same-basis stations |
| Units | IMPLEMENTED | °C / hPa / %; upload units confirmation (`C`, `hPa`) enforced before analysis | — |
| Timestamps | IMPLEMENTED | AWS IST, GHCNh UTC (documented); replay source refuses non-chronological frames (`Backend/src/api/replay/source.py`); duplicate/invalid-timestamp detection in upload preview | Mixed timezone conventions (`IST` bulk file, `UTC` GHCNh) are documented but are not unified into one canonical timeline |
| Missingness | IMPLEMENTED | Delhi ≈0.28 % temperature missing; `Backend/reports/data_audit/delhi_missing_runs.csv` (97 runs) and Jena counterpart (6 runs); NaN never imputed or zero-filled anywhere (`Backend/src/baseline/run.py`, `noaa/process.py`) | Missing current values yield NaN scores/flags (deliberate honesty, but reduces usable rows) |
| Communication gaps | IMPLEMENTED (data-quality layer) | `timeline_checks.detect_communication_gap`; states `DATA_AVAILABILITY_EVENT` / `COMMUNICATION_GAP`; ML ineligible while in gap; gap counts in upload preview (`large_gaps`) and DQ reports | Gaps are DQ events, not "anomaly alerts", and there is no benchmark metric for gap detection (injectors do not inject gaps) |
| Multiple stations | IMPLEMENTED | 14 mapped stations; three capability tiers (ensemble / calibrated statistical / context-only) exposed via `probe_available`, `detector_capability`, `capability_notes` | Only 1 station (DEL-01) has the full IF+LSTM+ensemble+SHAP stack; 10 have a statistical detector; 3 are context-only |
| Historical data | IMPLEMENTED | Delhi 2022-04-01 → 2024-12-31; GHCNh 2022-01-01 → 2024-12-31; Jena benchmark; frozen artifacts read back at serving time | — |
| Controlled anomaly injection | IMPLEMENTED | `Backend/src/benchmark/injectors.py` with SPIKE / FROZEN / DRIFT / CROSS_VARIABLE / SPIKE_PLUS_DRIFT labels; `test_in_distribution.csv`, `test_generalization.csv`; controlled live demo PATNA-TEST-01 (`Backend/reports/phase23/live_demo_run.json`, explicitly "CONTROLLED LIVE DEMO (scripted, not IMD data)") | Controlled injections are synthetic, not real sensor faults; they are correctly separated from real data in provenance labels |
| **B. DETECTION** | | | |
| Spike detection | IMPLEMENTED | Event recall (ens_median): Jena generalisation 1.00, Delhi generalisation 0.967; live probe example (`SPIKE` 0.798, max|z|=141.4); replay example reason cites a real 8.0 robust jump | Row-level recall is lower because labels are sparse (Delhi gen SPIKE row recall 0.851, Jena ID 0.685); must quote the right metric |
| Frozen-value detection | PARTIALLY IMPLEMENTED | `POSSIBLE_FREEZE` DQ state (`freeze_checks.detect_frozen_runs_with_threshold`, FREEZE_DURATION_HOURS=6) keeps ML eligibility; frozen-sensor features; benchmark event recall Jena gen 0.367 / Delhi gen 0.167; live demo found the FROZEN segment | Weakest fault family: root-cause FROZEN recall is **0.0 in every split**; on Delhi ID only 2/30 events. PS explicitly lists "frozen values" — this is the biggest detection gap |
| Drift detection | PARTIALLY IMPLEMENTED | Detected as sustained statistical deviation; event recall Jena gen 0.533 / Delhi gen 0.333; MUM-03 calibration validation drift recall 0.5 | No dedicated drift/trend detector is part of the frozen ensemble; latency to detect drift is minutes-to-hours (median 10–210 min in event metrics) |
| Cross-variable detection | IMPLEMENTED | CROSS_VARIABLE event recall 1.00 (both datasets, generalisation); Delhi gen row-level F1 0.982 (dense injections); multivariate deviation features; probe evidence shows temp deviation with joint context | In-distribution event recall is weaker (Jena ID 0.40, Delhi ID 0.567); no thermodynamic/physical consistency equation — it is learned deviation, not a physical model |
| Communication-error detection | IMPLEMENTED (as DQ) | Gap taxonomy with deterministic priority: `PASS` → `DATA_AVAILABILITY_EVENT` → `COMMUNICATION_GAP` → `DATA_INTEGRITY_FAULT` → `POSSIBLE_FREEZE` → `PHYSICAL_SANITY_FAULT`; DQ events are surfaced in API/UI | Not counted as detection metric; no benchmark evaluation of gap detection quality |
| Detector algorithm | IMPLEMENTED | Statistical z/IQR baseline (|z|>3.0 or IQR), Isolation Forest (94-feature allowlist), LSTM autoencoder (reconstruction MSE); combine by mean AND median (`Backend/src/ensemble/aggregation.py`); calibrated to clean-training percentiles | — |
| Station-specific calibration | IMPLEMENTED (for 10 stations) | `Backend/src/detection/calibrate.py` → `Backend/data/detectors/registry.json`; per-station cadence, thresholds, pressure semantics; validation example `Backend/reports/india_ghcnh/mumbai_statistical_validation.json` (precision 0.187 / recall 0.504; spike 1.0, frozen 0.5, drift 0.5, cross 1.0) | Calibration is statistical-only; new stations do not get IF/LSTM/ensemble/root-cause models |
| Threshold strategy | IMPLEMENTED | z=3.0/IQR for statistical; ensemble threshold = 99th percentile of clean-training ensemble scores, frozen (`Backend/src/ensemble/threshold.py`); availability policy 3 components → FULL_EVIDENCE, 2 → PARTIAL, <2 → INSUFFICIENT (NaN, never zero-filled) | Ensemble threshold exists only for Delhi/Jena; statistical stations use per-station calibration instead |
| False-positive handling | PARTIALLY IMPLEMENTED | FPR 1.2–3.5 %, FP/10k 112–350 across splits; frozen threshold; `reports/ensemble/false_positive_analysis.csv`; durable replay alerts are deterministic per (station, timestamp, detector) so re-runs do not duplicate | At row level FP (1,059–1,813 per split) far exceed TP (129–822); no explicit debouncing/hysteresis in the ensemble (episodes exist only for live), so alert feeds can cluster FPs |
| Confidence calculation | PARTIALLY IMPLEMENTED | Two different definitions, both documented: ensemble `CONFIDENCE_BY_AVAILABILITY` (FULL 1.0 / PARTIAL 0.67 / LOW_CONTEXT 0.33 / INSUFFICIENT None) and statistical `confidence_for(zmax)=zmax/(zmax+3)` (observed 0.5022 for z=3.03) | Neither is a calibrated statistical confidence; judges must not be told "confidence" means probability of correctness; ensemble path effectively reports evidence availability |
| Severity calculation | PARTIALLY IMPLEMENTED | `SEVERITY_BANDS` on max|z| for the 10 statistical detectors and the statistical replay path (observed `LOW`); replay alert store defaults `LOW` if absent | The Delhi ensemble path has **no severity**: `GET /api/v1/alerts` records show `severity: null`; ensemble alert events use the root-cause class as `event`. PS expects severity as an output |
| Delhi vs new-station consistency | IMPLEMENTED | Different detectors for different validation levels, surfaced explicitly per station (`detector_capability` FULL_TPR / PARTIAL / context-only) | Two detection vocabularies in one product (ensemble score vs statistical z) — the UI must keep their scales distinct |
| **C. TEMPORAL / SEASONAL** | | | |
| Temporal learning | IMPLEMENTED | 106 features in 11 families (`Backend/reports/features/feature_schema.json`): first-order dynamics 9, frozen-sensor 6, variability 3, causal rolling baseline 36, local deviation 18, trend 9, multivariate 6, quality metadata 7, gap metadata 3, cyclical 4; causality enforced (no future leakage) and tested (`test_causality_*`) | — |
| Seasonal learning | PARTIALLY IMPLEMENTED | Cyclical hour / day-of-year sin–cos encodings; same-hour descriptive reference (`Backend/src/seasonal/context.py`, MIN_DAYS=3; live probe shows `n_days: 1006`, note "descriptive reference only") | No seasonal model is trained or evaluated; no seasonal holdout split; `src/seasonal/` contains only `context.py`. Do not claim "seasonal modeling" |
| **D. MULTIVARIATE CONSISTENCY** | | | |
| Joint T/RH/pressure evaluation | IMPLEMENTED | Multivariate deviation features (`multivariate_max_abs_robust_deviation_2h`, range) enter detector features and SHAP; probe explanation cites them as top SHAP contributors (0.133, 0.105); CROSS_VARIABLE injections detected at 1.00 event recall | Not a physical consistency model (e.g., no Magnus/Tetens closure test); "joint" means joint learned deviations |
| Concrete cross-variable example | IMPLEMENTED | Probe DEL-01 48.7 °C: temperature departs by 37.2 from neighbors while humidity is indeterminate and pressure is basis-incompatible → spatial `LOCAL_SENSOR_ANOMALY`; benchmark CROSS_VARIABLE 30/30 detected in generalisation | — |
| **E. SPATIAL CONSISTENCY** | | | |
| Neighboring stations | IMPLEMENTED | `Backend/data/` spatial artifacts (`neighbor_graph.csv`, `spatial_consistency.csv`); DEL-01 probe used 3 usable of 4 neighbors (real NOAA stations named in the response); live uses co-temporal live neighbors only | DEL-01's own deployed context showed `neighbor_count: 0` in the frozen snapshot (UNAVAILABLE) — neighbor availability depends on timestamp |
| Time matching | IMPLEMENTED | Causal alignment: latest neighbor value ≤ target timestamp, 30-min staleness cap, no interpolation (`Backend/src/api/replay/engine.py`, `Backend/src/live/inference.py`) | — |
| Distance constraints | IMPLEMENTED | Only the station's audited selected neighbors from the neighbor graph participate (≤600 km per graph construction) | — |
| Spatial score | IMPLEMENTED | Variable-level robust scores vs neighbor median/MAD; SUPPORT_SCORE_MAX=2.0, CONTRADICT_SCORE_MIN=3.0, MIN_SCORABLE_NEIGHBORS=2; pressure only same-basis | Thresholds are fixed, not calibrated per station |
| Does spatial affect the final decision? | PARTIALLY IMPLEMENTED (interpretation only — by design) | `Backend/reports/phase22/spatial_decision_evaluation.json`: baseline vs spatial-aware **flags_identical: true** (no metric change); spatial never enters the ensemble score and never creates an anomaly; it only interprets flagged rows (`LOCAL_SENSOR_ANOMALY`, `POSSIBLE_REGIONAL_EVENT`, `ANOMALY_WITHOUT_SPATIAL_CONFIRMATION`) | The PS example ("use temporal/spatial consistency to determine probable sensor anomaly") is satisfied as an *interpretation label*, not as a detection input. Do not claim spatial anomaly detection |
| **F. EXPLAINABILITY** | | | |
| Real SHAP implementation | IMPLEMENTED | `Backend/src/root_cause/explain.py`; live probe returned top-5 SHAP values with signed contributions and direction (e.g., `multivariate_max_abs_robust_deviation_2h=113.330 (SHAP +0.133, increases predicted-class support)`) and `Backend/models/root_cause/*_root_cause_explainer.joblib` | SHAP runs only when a row is anomalous AND the evidence frame is complete; it is absent for non-anomalous rows and for the statistical-only stations |
| Which model SHAP explains | IMPLEMENTED | The root-cause classifier (`delhi_root_cause.joblib`), not the anomaly detector; `reports/root_cause/model_config.json` | The ensemble/IF/LSTM anomaly score itself is not explained — explanations are diagnostic (why this class), not score decomposition |
| Feature contributions | IMPLEMENTED | Probe response `explanation.features[]` with name/value/contribution/direction | — |
| Plain-language explanation | IMPLEMENTED | Per-class wording template instantiated with measured values, then "Top features contributing to the classifier's prediction: …"; probe text combines statistical, LSTM, SHAP, spatial | Wording is a documented template, not free-form generation; it must be presented as templated |
| Fallback behavior | IMPLEMENTED | Exception → text `None` → "Insufficient evidence for root-cause classification…"; non-anomalous → "Observation consistent with the station's historical context…"; upload path: `Not a trained-model diagnosis.` | — |
| **G. ROOT CAUSE** | | | |
| Classes tested | IMPLEMENTED | SPIKE / FROZEN / DRIFT / CROSS / MIXED / UNKNOWN in `Backend/reports/root_cause/root_cause_metrics.csv`; COMMUNICATION_GAP handled in the DQ/action vocabulary | — |
| Root-cause accuracy | PARTIALLY IMPLEMENTED | Delhi gen accuracy 0.617 incl UNKNOWN / 0.917 excl UNKNOWN, CROSS F1 0.864; Jena ID 0.674 / 0.978; but Jena gen 0.197 / 0.324; FROZEN recall 0.0 everywhere; MIXED F1 0.007 (Jena gen) | Classifier does not generalise across datasets; frozen class is never diagnosed; MIXED effectively unsupported in practice |
| Upload root-cause estimates | PARTIALLY IMPLEMENTED | Transparent heuristic (`_estimate_pattern`): SPIKE/DRIFT/FROZEN/CROSS rules over measured features; `confidence: None`; labelled "heuristic pattern estimate … not a trained-model diagnosis." | Heuristics share names with trained classes — must not be presented as classifier output |
| **H. SENSOR HEALTH / DEGRADATION** | | | |
| Sensor health display | PARTIALLY IMPLEMENTED | Per-observation DQ status (`PASS`, gap, integrity, freeze, sanity) + station status (`healthy` / `historical_only`) + checks (`sensor_variability`, `frozen_sensor` features) in API and UI | Health is per-observation/per-check, not a station health score; freeze detection is weak (see B) |
| Degradation indicator | NOT IMPLEMENTED | No degradation trend/rate model, no RUL, no calibration-drift monitor in code or reports | PS objective 9 ("sensor degradation") is only indirectly represented by drift detection |
| Maintenance indication | PARTIALLY IMPLEMENTED | `station_service.maintenance_review`: Delhi only, trailing-30-day alert episodes → `MAINTENANCE_REVIEW_RECOMMENDED` / `ELEVATED_WATCH` / `NO_ACTION_INDICATED`; explicitly "not a failure prediction"; observed on DEL-01 (`episodes_30d: 82`) | GHCNh stations report `NOT_APPLICABLE`; it is an alert-history counter, not maintenance prediction |
| **I. REAL-TIME** | | | |
| Live pipeline | PARTIALLY IMPLEMENTED | Code path exists: observation → DQ → statistical → multivariate → pattern estimate → spatial (co-temporal) → episode alerting → WebSocket → UI (`Backend/src/live/*`); IMD WIS2 adapter with CA bundle config | In this environment `LIVE_SOURCE_MODE=DISABLED` (`LIVE_UNAVAILABLE` / `NOT_CONFIGURED`); live stations get no IF/LSTM/ensemble/root-cause and produce **no severity/confidence**; no live measurements were executed during this audit |
| Processing latency | IMPLEMENTED (measured) | Scripted live demo: p50 54.09 ms, p95 87.33 ms, max 89.1 ms (`Backend/reports/phase23/live_demo_run.json`); replay: per-reading median 0.094 s, p95 0.096 s, throughput 10.7 rows/s, 300 rows in 39 s, effective 2,680× (`Backend/reports/replay/performance.json`); statistical replay today reached effective 268,522.9× (no TF per row) | Latency measured on one local machine only; ensemble path is ~0.1 s/row, statistical path ~0.007 s/row — do not average them into one claim |
| Observation → result → alert → WS → frontend | IMPLEMENTED | WS contract verified today: `connection` → 60 × `reading` → 29 × `alert` → `complete`; frontend consumes the same socket (`Frontend/src/lib/live.ts`, `useLiveReplay.ts`); investigations route for streamed anomalies | Frontend streaming was verified interactively in earlier work (UI FIX 1); today's run verified the backend contract only |
| Alert persistence | IMPLEMENTED | Durable replay alerts in `Backend/data/replay/replay_alerts.db` (29 recorded today, deterministic IDs); live store SQLite for episodes; frozen operational alerts rebuilt at startup | Frozen `/api/v1/alerts` feed carries `severity: null`, `confidence: null`, `score: null` — it cannot support a severity demo |
| "Real-time" claim validity | PARTIALLY IMPLEMENTED | Replay is accelerated historical streaming (paced, e.g. 2 s/observation at 900×); probe is on-demand; live ingestion is currently disabled | Do not describe the product as live-connected; describe it as a real-time-capable pipeline demonstrated over historical replay + controlled live demo |
| **J. SCALABILITY** | | | |
| Number of stations | PARTIALLY IMPLEMENTED | 14 mapped; 11 with detectors (1 ensemble + 10 calibrated); 3 context-only; network summary computed from station states | Nationwide claim unsupported; no multi-region deployment evidence |
| Station-specific configuration & detector reuse | IMPLEMENTED | Registry-driven: one detector class + per-station registry entries; no per-station code paths; calibration script produces artifacts | Registry can add more statistical stations, but each needs calibration data |
| Statelessness / concurrency | INSUFFICIENT EVIDENCE | Replay sessions are per-WebSocket-connection; upload sessions in memory; SQLite stores; no shared mutable inference state observed in code | No concurrent-session load test was run; TF CPU inference per row means parallel replays contend; throughput numbers are single-session |
| Network processing | PARTIALLY IMPLEMENTED | `network/summary` aggregates station states; neighbor graph used for spatial context | No streaming/distributed architecture; single FastAPI process |
| **K. DEPLOYABILITY** | | | |
| FastAPI backend | IMPLEMENTED | `Backend/src/api/app.py`, pinned `Backend/requirements.txt` (fastapi 0.141.1, tensorflow-cpu 2.22.0rc0, shap 0.52.0, …), `/health` green with all models loaded | — |
| Startup validation / required artifacts | IMPLEMENTED | `Backend/src/api/dependencies.py REQUIRED_FILES` (station mapping, delhi_clean, ensemble/root-cause predictions, spatial artifacts + 6 model files); server fails fast when missing; `/demo/readiness` checked today | Artifacts are git-ignored and must travel with the demo machine (manifest `phase21b_go1_artifact_manifest.json` with sha256) |
| Reproducibility | PARTIALLY IMPLEMENTED | Pinned requirements; reproducibility tests exist; this audit's 72-test run passed in 438.96 s | README documents two known environment-dependent failures (`test_raw_inventory_presence`, `test_deterministic_processed_output`); they were not part of the audited run and should be disclosed |
| Deployment readiness | PARTIALLY IMPLEMENTED | Local uvicorn run verified (cold TF load ≈10 s reported; launcher ≈30–40 s observed); frontend builds with Vite | No Dockerfile, compose, systemd, or cloud deployment artifacts exist; "deployable" currently means "runs on the demo machine" |
| **L. ENERGY / EDGE** | | | |
| Edge AI / ESP32 model | NOT IMPLEMENTED | Filesystem search for `*.tflite`, `*.onnx`, `*.pte`, `*.pb`, `*.engine` (excluding `.venv`) returned zero files; models = 47 MB of CPU TensorFlow/joblib | Server-side inference only; no quantization, no edge runtime |
| Edge latency / memory | NOT IMPLEMENTED | No edge artifacts to measure | — |
| Energy efficiency | INSUFFICIENT EVIDENCE | No power measurement, no energy report anywhere in the repo | Do not claim energy efficiency; at most cite 47 MB artifact footprint |
| **M. OPTIONAL CORRECTION** | | | |
| Corrected / imputed value | PARTIALLY IMPLEMENTED (optional) | Upload analysis only: for heuristic SPIKE, suggests the last valid observation (`Backend/src/api/services/upload_analysis.py`); rendered in `Frontend/src/routes/_app.analyze-data.tsx`; verified today 58.0 → 20.8 with "operator approval required" | No imputation in probe/live/replay/ensemble paths; value is a naive last-valid suggestion, unvalidated (no accuracy metric), and must not be presented as corrected data |
| **N. UI** | | | |
| Network / station / anomaly / severity / confidence / explanation / replay / alerts / status | IMPLEMENTED | Overview with station map and replay stage, station pages, alerts + investigations, evaluation, judge probe, analyze-data, live page; verified in earlier sessions (UI FIX 1/2) with `tsc` + `vite build` clean | Severity/confidence shown only where they exist: statistical replay shows real values; Delhi ensemble alerts must show "not available" instead of invented numbers |
| UI claims vs backend evidence | PARTIALLY IMPLEMENTED | Honest provenance labels (`REPLAY`/`HISTORICAL`, `Live` nav, "no readings are synthesized" empty state, capability notes, `source_mode` labels). Earlier UI fixes removed misleading "Offline" for historical observations | Residual product risk: the deprecated "Live" naming while live ingestion is disabled; reviewer may read "Live & Replay" as live-connected |
| **O. DEMONSTRATION** | IMPLEMENTED | Full E2E runs performed and reproduced today (details in section 7) | Demo = historical replay + on-demand probe + controlled live demo; no real live IMD feed |
| **Evaluation-criteria areas (no scores)** | | | |
| Innovation & novelty | IMPLEMENTED (evidence-based) | Differentiators are real and testable: availability policy that returns INSUFFICIENT_EVIDENCE instead of zero-filling; percentile-calibrated thresholds frozen from clean training; causal neighbor alignment with no interpolation; DQ taxonomy with an ML-eligibility gate; three-tier station capability separation; durable deterministic replay alerts; truth-separation tests | Novelty is architectural, not a new algorithm; IF/LSTM/SHAP themselves are standard |
| Detection accuracy | PARTIALLY IMPLEMENTED | See table B/G: strong spikes/cross-variable, weak frozen, modest row-level precision/recall, low FPR | Lead with event-level recall and FPR; never quote only the favourable split |
| Real-time capability | PARTIALLY IMPLEMENTED | See I: measured latency on scripted live + replay; WS streaming verified | Live ingestion disabled; replay is historical |
| Explainability | IMPLEMENTED | See F: real SHAP for root-cause classifier, fallbacks, measured-value templates | Detector score itself unexplained |
| Scalability | PARTIALLY IMPLEMENTED | See J | No concurrency/load evidence, no nationwide deployment |
| Practical deployability | PARTIALLY IMPLEMENTED | See K: pinned deps, fail-fast startup, readiness endpoint, artifact manifest | No containerization or production deployment evidence |
| Visualization/UI | IMPLEMENTED | See N | Severity/confidence availability gaps |
| Energy efficiency | INSUFFICIENT EVIDENCE | See L | No edge artifact, no power data |

---

## 1. What the current system genuinely solves

1. **A working T/RH/pressure anomaly-detection pipeline, end-to-end, over real historical data.** Real
   AWS/GHCNh observations flow through data-quality checks, feature engineering, detectors, calibrated
   scoring, root-cause classification and explanation, and come out as alerts with persisted evidence.
   Verified by execution today: 60 replayed MUM-03 observations produced 29 durable alerts with real
   reasons, and a 48.7 °C Delhi probe produced a full evidence record.
2. **Spikes and cross-variable inconsistencies.** Event-level recall reaches 1.00 for SPIKE (Jena
   generalisation) and 1.00 for CROSS_VARIABLE, with fast latencies (spikes: 0 min median).
3. **Communication gaps, integrity faults and freeze suspects as first-class data-quality states**, with
   deterministic priority and an ML-eligibility gate; no silent imputation anywhere.
4. **Station-specific calibration instead of one global threshold** for 10 Indian GHCNh stations
   (registry artifacts + per-station validation, e.g. Mumbai: precision 0.187 / recall 0.504), plus a
   frozen Delhi ensemble, with capability tiers surfaced honestly to the UI.
5. **Explainability that is genuinely SHAP-based** for the root-cause classifier, with signed
   contributions and a documented fallback chain.
6. **Spatial interpretation of flagged observations** using real neighbors, causal time matching and
   basis-compatible variables — including the PS's example scenario (station extreme while neighbors are
   normal → `LOCAL_SENSOR_ANOMALY`).
7. **A real-time-capable transport** (WebSocket) with measured latency, durable alert persistence, and a
   React dashboard that streams observations and alerts.
8. **Reproducibility and honesty mechanisms**: frozen thresholds, artifact manifest with hashes, readiness
   endpoint, provenance labels separating benchmark / controlled / historical data, and tests that pin
   these properties (72 passed today).

## 2. What it only partially solves

1. **Frozen-value detection** — the PS's headline fault case #3 is the weakest: event recall 0.10–0.37
   and root-cause FROZEN recall 0.0 in every split. The DQ freeze state exists, but the downstream ML
   rarely confirms it.
2. **Drift detection** — detected only as sustained deviation; event recall 0.33–0.53; no dedicated
   trend detector; detection can lag hours.
3. **Confidence** — currently an evidence-availability proxy on the ensemble path or a bounded magnitude
   ratio on the statistical path, not a calibrated probability.
4. **Severity** — produced by the 10 statistical detectors (presentation bands on |z|) but absent from the
   ensemble path; frozen Delhi alerts carry `severity: null`.
5. **Spatial consistency** — implemented for interpretation, deliberately not for detection: the
   spatial-aware evaluation has identical flags to the baseline. This is defensible engineering, but it
   is not "spatial anomaly detection".
6. **Temporal/seasonal learning** — rich causal/temporal features and cyclical encodings, but no seasonal
   model and no seasonal evaluation.
7. **Live ingestion** — the code path, IMD adapter and controlled demo exist, but live is disabled in this
   environment, unvalidated for ML components on live stations, and carries no severity/confidence.
8. **Root cause** — excellent on Delhi generalisation (CROSS F1 0.864, accuracy 0.917 excluding UNKNOWN)
   but does not generalise to Jena (accuracy 0.324 excluding UNKNOWN) and never diagnoses FROZEN.
9. **Sensor degradation / maintenance** — an alert-history review flag on Delhi only; no degradation
   trend model.
10. **Scalability** — 14 mapped stations, single process, no concurrency or load evidence.
11. **Deployability** — local server only; no container/orchestration artifacts; artifacts are
    git-ignored and must be shipped.

## 3. What is not implemented

1. **Edge AI (TFLite/ONNX/quantized/ESP32)** — zero edge artifacts; server-side CPU TensorFlow only.
2. **Degradation indicator / remaining-useful-life prediction** — nothing in code or reports.
3. **Validated correction/imputation** — only an unvalidated upload-time last-valid suggestion exists.
4. **Seasonal model** — only descriptive same-hour context and cyclical encodings.
5. **Spatial contribution to detection decisions** — deliberately absent (context-only layer).
6. **Dedicated communication-gap detection metric** — DQ state exists, but no evaluated gap detector.
7. **Any power/energy measurement or efficiency engineering.**
8. **Containerization / production deployment pipeline** — no Dockerfile, compose, or CI deploy.

## 4. Claims we MUST NOT make in PPT/demo

1. **"Real-time detection from live IMD AWS"** — live ingestion is `DISABLED`/`NOT_CONFIGURED` here.
   Say: "real-time-capable pipeline; demonstrated over accelerated historical replay (paced), an
   on-demand probe, and a scripted controlled live demo — never IMD data."
2. **"Detects frozen sensors"** without qualification — say: "freeze suspects are flagged by the DQ
   layer; ML confirmation of frozen episodes is weak (event recall 0.10–0.37) and is a known
   limitation."
3. **"Seasonal anomaly detection / seasonal model"** — say: "temporal features include cyclical
   encodings and a descriptive same-hour reference; seasonal modelling is future work."
4. **"Spatial anomaly detection / neighbors confirm anomalies"** — say: "spatial context interprets
   already-flagged observations (local sensor anomaly vs possible regional event); it never creates or
   changes an anomaly (spatial-aware evaluation flags are identical)."
5. **"Edge AI / ESP32 deployment"** — not implemented.
6. **"Corrected values"** — only an upload-time suggestion requiring operator approval, unvalidated.
7. **High overall precision/recall** — do not quote row-level ensemble F1 (0.08–0.44) as the headline
   without event-level metrics (event recall 0.46–0.76) and FPR (1.2–3.5 %).
8. **"Confidence = probability the anomaly is real"** — it is an availability proxy / magnitude ratio.
   Never present it as statistical confidence.
9. **"Severity" as a universal output** — severity exists only on the statistical-detector path; the
   Delhi ensemble alerts have none.
10. **"Nationwide scalability"** — say: "14 mapped stations, 11 detector-covered, single-node
    deployment; scale-out architecture is future work."
11. **"Root cause is accurate in general"** — quote per-dataset numbers; FROZEN is never diagnosed and
    cross-dataset generalisation is weak.
12. **"Controlled injections are real observations"** — they are synthetic, labelled benchmark faults;
    the scripted PATNA-TEST-01 live demo is explicitly not IMD data.

## 5. Critical gaps before submission

| # | Gap | Why it matters | Where the evidence stands |
|---|---|---|---|
| 1 | Frozen-value detection weakness | PS objective #3; judges will test a flat-line sensor | Event recall 0.10–0.37; root-cause FROZEN recall 0.0; DQ freeze state exists |
| 2 | Severity absent on ensemble path | PS expected output lists severity | `/api/v1/alerts` `severity: null`; statistical replay has real bands |
| 3 | Confidence semantics | Explainability weight; risk of overclaiming | Two proxies documented in code, not calibrated |
| 4 | Live must be demonstrably configured or explicitly framed | Real-time weight 15 % | `LIVE_SOURCE_MODE=DISABLED`; controlled demo available |
| 5 | Root-cause cross-dataset weakness | Accuracy weight; judges may probe Jena-style data | Jena gen accuracy 0.197 (incl UNKNOWN) |
| 6 | Spatial is context-only | PS example emphasizes spatial reasoning | flags_identical=true (by design) — must be explained, not hidden |
| 7 | No edge artifact | Energy weight 5 % | Zero `.tflite`/`.onnx` files |
| 8 | Accuracy presentation | 20 % weight; row-level F1 looks weak | Use event recall + FPR + per-fault table; be upfront |
| 9 | Optional correction immaturity | Optional, not mandatory | Upload suggestion only; label it |
| 10 | Deployment/concurrency evidence | Deployability + scalability weights | Single machine; no load test; no containers |

## 6. Recommended fixes ordered by impact and implementation time

**High impact, low time (do first):**

1. **Frozen-sensor alerting path (≈4–8 h).** Route `POSSIBLE_FREEZE`/`frozen_sensor` evidence into an
   explicit freeze alert with root-cause override, and add a freeze-focused evaluation (the benchmark
   labels already exist). This closes the largest PS gap and the 0.0 FROZEN recall.
2. **Severity for the ensemble path (≈2–3 h).** Derive presentation bands from the frozen ensemble
   percentile (documented, not fitted) or display root-cause class + evidence availability with an
   explicit "severity band not defined for this detector" state — either way, remove `null` severity from
   demo flows.
3. **Confidence transparency (≈1–2 h).** Always send and render `confidence_basis`
   ("evidence availability: 3/3 components" vs "magnitude ratio z/(z+3)") so no judge can misread it as
   probability.
4. **Demo-safe live path (≈1 h).** Enable `CONTROLLED_LIVE` for the demo environment and show the Live
   page end-to-end, while keeping the "scripted, not IMD" label; or capture a screen recording of the
   controlled demo run as fallback.
5. **Alert-feed honesty in UI (≈1–2 h).** Ensure Delhi ensemble alerts render "severity/confidence not
   available" rather than blank or zero; confirm no "Live" badge implies connectivity.
6. **Evaluation narrative (≈2 h).** Build one slide/table from the existing CSVs: per-fault event recall
   + FPR + root-cause per-class, with explicit limitations (frozen, Jena generalisation). This converts
   weak rows into demonstrated rigor.

**Medium impact, medium time:**

7. **Drift detector as a first-class component (≈1–2 days).** Add a causal trend/level-shift statistic to
   the evidence set (not necessarily the score) and evaluate against the DRIFT labels.
8. **Spatial interpretation surfacing (≈3–4 h).** In the decision card, show neighbor agreement counts
   and an explicit "spatial context does not change the detection decision" note; add a spatial-labelled
   example to the demo script.
9. **Seasonal evaluation or explicit scope statement (≈1 day).** Either evaluate same-hour context
   deviations against the benchmark, or add a labelled "descriptive" seasonal card.
10. **Correction hardening (optional, ≈1 day).** Add an imputation-accuracy evaluation for the upload
    suggestion or label it "suggested value (unvalidated)" in UI and API.
11. **Concurrency/load test (≈4–8 h).** Script N simultaneous replay sessions and publish throughput/
    latency degradation; document the single-process assumption.

**Low priority before submission (do not attempt):**

12. **Edge quantization/TFLite** — would need a new export/eval pipeline; without honest edge validation
    it is worse than clearly stating server-side inference.
13. **Containerization** — nice for deployability weight but not demo-visible; a one-page deployment note
    may be cheaper.

## 7. Exact demo flow supported by the current implementation

All steps below were executed or verified today against the running system.

**Flow A — Historical replay (main flow, judge-safe, no credentials):**

1. Backend `cd Backend && .venv/Scripts/python.exe -m src.api.run`; frontend `cd Frontend && npm run dev`;
   open `http://localhost:3000`.
2. Overview → confirm Demo Ready (`GET /api/v1/demo/readiness` → `ready: true`).
3. Choose **DEL-01** for the full ensemble (root cause + SHAP + spatial interpretation), or a calibrated
   station (e.g. MUM-03) for the station-specific statistical detector with real severity/confidence.
4. Start Historical Replay (DEL-01 OOD at low speed for visuals; MUM-03 HISTORICAL at 900× for
   throughput — verified: 60 observations, 29 anomalies, 29 durable alerts, `REPLAY_COMPLETE`).
5. Observation arrives → DQ status + detector evaluation stream as `reading` events; anomalies emit
   `alert` events.
6. For MUM-03: severity `LOW`, confidence 0.5022, score 3.0268 vs z-threshold 3.0, reason
   "SPIKE: abrupt 8.0 robust-deviation jump within 2h; max|z|=3.03".
7. For DEL-01: ensemble score vs frozen threshold 0.9783, availability `FULL_EVIDENCE`, root cause
   (e.g. SPIKE 0.798, runner-up CROSS) and SHAP top-5 features in the explanation; PERFECT for opening
   an anomaly investigation (route `/investigations/replay/<id>`).
8. Alert persisted (`alerts_recorded` count in the `complete` event; durable SQLite records).
9. WebSocket contract is visible in the UI stream; replay completes with observations/anomalies counts.
10. Evaluation page: frozen OOD metrics, per-fault event recall, root-cause metrics, runtime evidence
    (all read from committed reports; nothing recomputed).

**Flow B — Judge probe (real interactive inference):**

1. Judge Probe page → pick DEL-01 (only probe-capable station; the UI now labels why others are gated:
   calibrated → replay, context-only → network map).
2. Enter a normal observation → non-anomalous result with "consistent with historical context".
3. Enter an extreme temperature (e.g. 48.7 °C at the prefilled context) → score 0.99995 vs threshold
   0.97830, availability FULL_EVIDENCE, root cause SPIKE 0.798 with runner-up CROSS, SHAP top-5,
   spatial `LOCAL_SENSOR_ANOMALY` with contradicting neighbor list → exactly the PS's station-vs-neighbors
   example.
4. Attempt MUM-03 → the probe refuses with an explicit explanation (HTTP 422 `insufficient_context`) —
   demonstrates honest capability boundaries.

**Flow C — Controlled live demo (requires enabling `CONTROLLED_LIVE`):**

Live page → Start controlled live demo → PATNA-TEST-01 scripted traffic labelled
`CONTROLLED LIVE (scripted, not IMD data)`; verified in `reports/phase23/live_demo_run.json` (34
observations, 1 resolved episode, inference p50 54.09 ms). Use this only to demonstrate the live
transport; never call it IMD data.

**Flow D — Uploaded dataset analysis (optional, statistical + DQ):**

Analyze Data page → upload a CSV → confirm mapping/units → run. Verified today: 200-row clean series with
one 58 °C spike → 1 anomaly, root-cause estimate `SPIKE`, correction suggestion 58.0 → 20.8 with
"operator approval required". Explicitly labelled heuristic (no trained models, no confidence) — present
as an optional capability, not as the core engine.

**What the demo must not do:**

- Do not open the frozen `/api/v1/alerts` feed expecting severity/confidence — those fields are `null`
  there; use the replay stream for severity/confidence.
- Do not start a Jena replay on a station without coverage, or probe a non-DEL-01 station, on stage
  without explaining the 422.
- Do not claim live IMD, edge deployment, seasonal modeling, spatial detection, or validated corrected
  values.

---

---

## 8. Showcase layer added after the audit (historical analysis + spatial investigation + controlled demo)

Three judge-facing capabilities were added on top of the EXISTING detector, spatial layer and data.
No new dataset, model, threshold or spatial algorithm was introduced, and no synthetic row is ever
presented as history.

| Capability | Implementation | Honesty limits recorded |
| --- | --- | --- |
| Historical station timeline | `GET /api/v1/stations/{id}/timeline`; artifacts built by `src/showcase/build_timeline.py`. Delhi = stored frozen-ensemble verdicts (injection rows excluded); the 10 calibrated GHCNh stations = that station's own registered detector run over its real history; observations always real | SAF-11/GAU-12/TRV-13 return `detector.available = false` → UI states *HISTORICAL DATA — DETECTOR VERDICT UNAVAILABLE*. Delhi verdicts exist only for the held-out window 2023-11-25 → 2024-12-31. GHCNh flag rate ~47–50 % at 30-min cadence (documented frozen-rule limitation, shown in the UI) |
| Station investigation (target vs neighbours) | `GET /api/v1/stations/{id}/investigation`; `src/api/services/investigation_hub.py` reuses `neighbor_graph.csv`, `align_neighbor` (≤30 min, causal) and `decision.decide_context` unchanged | Neighbours exist only where the audited graph has selected edges (Delhi-context ×4, Bengaluru/Mumbai/Thiruvananthapuram, Kolkata/Guwahati). MUM-03/CHD-09/PUN-10/HYD-07 report *spatial context unavailable — no neighbour values are invented*. AWS station pressure is never compared with GHCNh QNH altimeter |
| Controlled fault demo | `GET /api/v1/demo/fault-sequence`; `src/api/services/fault_demo.py` applies `src.benchmark.injectors` to real Delhi rows with fixed parameters from `src.benchmark.config` | Labelled `CONTROLLED DEMO — NOT LIVE IMD DATA`; stored observations unmodified; measured on 2024-03-10: NORMAL 0/84 false positives, SPIKE 3/3, FROZEN 6/10 (root cause FROZEN via the deterministic rule from the 6th identical reading), DRIFT 3/36 (matches the documented DRIFT weakness in §2), CROSS_VARIABLE 12/12 |

Supporting work in the same period (documented in `README.md` and `reports/detection/freeze_evaluation.md`):

- deterministic stuck-signal (freeze) detector with a causally gated applicability rule (`FREEZE_MAX_CADENCE_MIN`);
- ensemble severity bands + confidence bases surfaced per verdict;
- longitudinal signal-health indicator on the station page;
- `tests/test_showcase_layer.py` (10 tests) covering timeline provenance, audited neighbours, causal
  anchoring, pressure-basis honesty and demo determinism/no-modification.

Still NOT implemented (unchanged): edge/quantized artifacts, live IMD ingestion, seasonal modeling,
validated corrected values, and any severity/confidence on the frozen `/api/v1/alerts` rows.

*End of audit. Sections 1–7 record the pre-existing gaps; §8 records what was added and the limits
that remain.*
