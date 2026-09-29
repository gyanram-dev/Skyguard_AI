# SkyGuard AI — Product Proof Matrix

**Problem statement:** AI/ML-Based Intelligent Anomaly Detection for Automatic Weather
Stations (AWS) — distinguish genuine meteorological events from abnormal/faulty AWS
observations while minimising false alarms.

**Base commit audited:** `8c24c904ce87cdc5cca324cff37faaecfd02da60`
(`phase24: validate Indian multi-city network`). All changes in this pass are
uncommitted. This pass added no model, no new detector and no new data pipeline — it
exposed and surfaced capabilities that already existed.

Every value shown in the UI is read from a backend response. Where a capability does not
exist, the UI says **Unavailable / Not configured / Historical only** rather than inventing
completeness.

---

## Core required parameters

| PS requirement | Implementation | UI location | Backend endpoint / module | Demo evidence | Limitation |
| --- | --- | --- | --- | --- | --- |
| Temperature (°C) | Probe input + station snapshot + station history | Test an Observation; Overview sensor cards; Station detail | `POST /api/v1/demo/probe`; `GET /api/v1/stations`; `/stations/{id}/history?variable=temperature` | Probe normal/spike runs submit °C | Station-detail anchors are the replayed latest row, not "now" |
| Atmospheric Pressure (hPa) | Same pipeline | Same | Same (`pressure_hpa`) | Probe submits 971.3 hPa | GHCNh stations use altimeter basis (labelled) |
| Relative Humidity (%) | Same pipeline | Same | Same (`relative_humidity_pct`) | Probe submits %RH | Some GHCNh stations report RH unavailable — rendered as "Not available", never 0 |

## Required / expected capabilities

| PS requirement | Existing implementation | UI location | Backend endpoint / module | Demo evidence | Limitation |
| --- | --- | --- | --- | --- | --- |
| Real-time anomaly detection | Phase-23 live ingestion manager (poll → causal history → ensemble → episodes) | Live page; Overview "Operating source"; Alerts (Live filter) | `GET /api/v1/live/status`, `/live/stations`, `/live/alerts`, `POST /live/start`, `/live/demo/start`; `src/live/manager.py` | Live page honestly shows `LIVE_UNAVAILABLE / NOT_CONFIGURED`; controlled live demo can be started | No IMD credentials in this environment — `LIVE_SOURCE_MODE=DISABLED`. Controlled live is scripted and labelled as such |
| Sensor fault detection | Statistical z-score + Isolation Forest + LSTM autoencoder, ensembled (median) | Test an Observation; Investigation "Model evidence" | `POST /api/v1/demo/probe`; `src/api/services/scoring.py`; frozen `*_ensemble_predictions.csv` | Spike probe → `is_anomalous=true`, score 1.000 | Detection strength varies by fault class (see Evaluation) |
| Spike detection | Thresholded ensemble deviation | Probe result "SENSOR ANOMALY / Root cause SPIKE" | `root_cause` in probe + alert payloads | Spike scenario → SPIKE @ 79% confidence | — |
| Frozen values | Data-quality frozen-run detector gates `quality_status`; `*_zero_delta` features feed the ensemble | "What SkyGuard Detects" (Frozen sensor); station "Freeze evidence" | `src/data_quality/*` (run-length thresholds); `data_quality.flags` | Frozen runs appear as DQ state; the probe cannot synthesise one | No dedicated freeze *score*; per-station freeze evidence is not exposed → shown as **Unavailable** |
| Drift | Causal trend features (`*_trend_30m/2h/6h`) feed IF/LSTM/root cause | "What SkyGuard Detects" (Drift — *monitors*) | `src/features/*`; historical DRIFT alerts exist (e.g. DEL-01, 72%) | Investigation of a DRIFT alert | No persistence detector today → worded "monitors", not "detects" |
| Communication errors | Live source staleness events (`DATA_SOURCE_STALE`) + DQ flags | Live page; "What SkyGuard Detects" (Communication) | `src/live/manager.py` staleness guard; `save_quality_event` | Live page shows `last_error` / `last_success` when configured | Historical replay has no live link → "Historical replay — no live link" |
| Temporal / seasonal patterns | Causal deltas, rolling windows, trends; 24 h history charts | Investigation "Temporal evidence"; Overview sensor cards | `/stations/{id}/history`; `src/features/feature_builder.py` | 24 h temperature chart on the SPIKE investigation | Charts are 24 h windows (no explicit seasonal model) |
| Multivariate consistency | Multivariate deviation block feeds scoring | Probe "MULTIVARIATE EVIDENCE"; Investigation evidence item 5 | `probe.evidence.multivariate`; `src/features/*` | Spike probe → multivariate deviation 71.5 | Multivariate payload is not retained for every historical alert → shown as unavailable there |
| Confidence | Evidence-completeness mapping: FULL 1.0 / PARTIAL 0.67 / LOW 0.33 / INSUFFICIENT null | Probe "Confidence"; Alert rows; Investigation | `station_service.EVIDENCE_COMPLETENESS` | Probe confidence 100% (full evidence) | Confidence is *evidence coverage*, not a calibrated probability — worded accordingly |
| Explainability | SHAP feature contributions + rule-based evidence items | Investigation "Why this needs review"; Probe "Why this assessment?" | `explanation` in probe and `/alerts/{id}`; `src/api/services/investigation_service.py` | SPIKE investigation shows 6 numbered evidence items + SHAP text | Some historical alerts return zero SHAP features → the block is omitted, not faked |
| Root-cause classification | Frozen multiclass classifier (SPIKE / FROZEN / DRIFT / CROSS_VARIABLE) | Probe header; Investigation "Root cause & confidence"; Alert rows | `POST /api/v1/demo/probe` → `root_cause`; `src/root_cause/*` | Spike probe → SPIKE, 79%, runner-up CROSS | Diagnoses are model predictions, labelled as such |
| Sensor health | Station snapshot + DQ state + alert history + spatial context | Station detail "Sensor health" (Can I trust this station?) | `GET /api/v1/stations/{id}` | Factors render with real values where available | Freeze/drift factors are not exposed per station → **Unavailable**, never "Healthy" |
| Network health / scalability | Network summary over the operational registry (14 Indian stations) | Overview "India station network"; Network Health page | `GET /api/v1/network/summary`, `/api/v1/stations`; `src/indian_network/*` | 14 stations, 793,872 observations indexed, 5 live-capable | 13 stations carry historical context only (no detector) — labelled |
| Optional corrected / imputed value | Upload-analysis `correction` (original → suggested + reason) | Analyze Data upload flow | `POST /api/v1/analyze/{id}/run` → `correction`, `recommended_action` | Operator-approved correction in upload analysis | Not available in the live/probe path → stated as not available for those sources |
| Optional degradation prediction | **Not implemented** | — | — | — | Explicitly not claimed anywhere in the UI |
| Visualization dashboard | Soft-3D India map, triage queue, evidence workspace, sensor cards, replay panel | Overview, Alerts, Investigations, Stations, Live, Network Health | `GET /api/v1/*` | 90-second judge walkthrough (see `demo_script.md`) | Desktop-first (1920/1440/1366); mobile is not a design target |

## The central PS story — regional event vs local sensor fault

| PS requirement | Existing implementation | UI location | Backend endpoint / module | Demo evidence | Limitation |
| --- | --- | --- | --- | --- | --- |
| Distinguish genuine events from faulty observations | Phase-22 spatial decision: compare the target against compatible neighbours (k ≤ 3, ≤ 600 km; temperature-basis compatible) | Overview "Real Weather or Sensor Fault?"; Investigation "NOAA spatial context"; Probe "SPATIAL EVIDENCE" | `src/spatial/decision.py`, `src/spatial/neighbors.py`; `spatial_decision` in probe/alert payloads | Spike probe → `contextual_decision = LOCAL_SENSOR_ANOMALY`, `spatial_influence = contradicted` | Phase-22 thresholds/policy unchanged. Only DEL-01 has detector + spatial evidence together; other stations carry NOAA context only |
| Minimise false alarms | Ensemble median + spatial corroboration before escalating | Probe "WHY?" checks; Alerts "Active/Resolved" | `src/ensemble/aggregation.py` | Normal probe → NORMAL with three consistency checks | Reported per-class metrics live on the Evaluation page; no new claims were added |

## Honesty / anti-fabrication rules enforced in this pass

- No station, observation, score, confidence, health value or metric is hardcoded.
- Headline counts (`Indian stations`, `Observations indexed`, `Live-capable`) come from the
  backend: `observations_indexed` is measured from the loaded frames (793,872) and
  `live_capable_stations` from the audited IMD-WIS2 capability registry (5).
- Jena remains `BENCHMARK_INTERNAL` and is filtered out of the datastore, so it can never
  appear in any list, count or map.
- Missing evidence is `Unavailable`; a missing spatial comparison is never a green tick.
- The probe only offers stations with detector coverage and explains why others are
  excluded, instead of letting the demo fall into a guaranteed error.
- Persisted live episodes are labelled by the active live mode (`CONTROLLED LIVE` unless
  the mode is `LIVE_IMD`), so scripted data never reads as IMD data.
- No ESP32/edge card was added, and nothing implies the full ensemble runs on a
  microcontroller.

## Corrections made in the regression pass

Three places were claiming more than the backend could support. All three were fixed at the
source rather than hidden in the UI.

| Issue | What was wrong | Fix | Where |
| --- | --- | --- | --- |
| Judge Probe dead end | The documented backend command crashed (`.venv` lacks `python-dotenv`), so the browser talked to a stale backend with no `probe_available` field; the UI then asserted "no station has detector coverage" from an absent field | `.env` loading is now optional so the server always starts; the UI only claims zero coverage when the backend reports zero, and otherwise falls back to the authoritative `/api/v1/demo/readiness` signal | `run.py`, `_app.judge-probe.tsx` |
| "14 healthy" | Context-only GHCNh stations were hardcoded `healthy` although no detector covers them | Context-only stations now report `historical_only`; operational buckets and `network_health_pct` are computed over detector-covered stations only; `detector_covered`/`context_only` added | `app.py::_station_state`, `network_service.summarize`, `kpi.tsx` |
| "1000 active" | The API caps `/api/v1/alerts` at 1000; the UI presented the cap as an active total (the real stored count is 1201) | The response now carries `returned`/`total`/`limit`; the UI shows "1000 shown of 1201 stored" and scopes counts to the loaded window; the hero CTA no longer shows a numeric badge | `app.py::list_alerts`, `_app/alerts/index.tsx`, `AppShell.tsx` |
