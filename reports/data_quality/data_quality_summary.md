# SkyGuard AI — Data Quality Layer Report: Phase 2.5

**Project**: SIH 2026 PS 26073 — AI/ML-Based Anomaly Detection for Automatic Weather Stations
**Phase status**: Phase 2.5 complete (deterministic pre-ML integrity gate).
**Safety check**: No ML models, no synthetic anomalies, no input modifications, no interpolation.

---

## 1. Input datasets (read-only)

| Dataset | Input file | Rows | SHA-256 before | SHA-256 after | Status |
| :--- | :--- | ---: | :--- | :--- | :--- |
| Jena Climate | `data/processed/jena_clean.csv` | 420,224 | `36835cd1615a4655...` | `36835cd1615a4655...` | **PASSED (Identical)** |
| Delhi-NCR AWS | `data/processed/delhi_clean.csv` | 289,728 | `019de716920f3a09...` | `019de716920f3a09...` | **PASSED (Identical)** |

Raw inputs (`jena_climate_2009_2016.csv`, `AWS_20220401_20241231.csv`) and
Phase 3 outputs (`data/features/*.csv`) were hash-verified unchanged as well.

---

## 2. Cadence configuration (single source of truth)

- `EXPECTED_INTERVAL_MIN`: Jena **10 min**, Delhi **5 min**
- `GAP_FACTOR`: **1.5** → gap threshold Jena **15.0 min**, Delhi **7.5 min**
- Defined once in `src/data_quality/timeline_checks.py`; reused by batch and streaming paths.

---

## 3. Quality rules and status priority (deterministic)

Priority (highest first):

1. `DATA_INTEGRITY_FAULT` — missing/invalid/duplicate/out-of-order timestamp
2. `COMMUNICATION_GAP` — elapsed time exceeded the gap threshold
3. `DATA_AVAILABILITY_EVENT` — one or more core values missing
4. `PHYSICAL_SANITY_FAULT` — RH < 0, RH > 100, or non-finite core value
5. `POSSIBLE_FREEZE` — identical-value run spanning the freeze duration
6. `PASS` — none of the above

Individual flags are always preserved alongside `quality_status`.
`ml_eligible = false` for levels 1–4; `true` for `POSSIBLE_FREEZE` and `PASS`.

---

## 4. Event counts — Jena

- `PASS`: **418,859**
- `DATA_AVAILABILITY_EVENT`: **0**
- `COMMUNICATION_GAP`: **5**
- `DATA_INTEGRITY_FAULT`: **0**
- `POSSIBLE_FREEZE`: **1,360**
- `PHYSICAL_SANITY_FAULT`: **0**
- `ml_eligible = true`: **420,219**; `false`: **5**

---

## 5. Event counts — Delhi

- `PASS`: **274,262**
- `DATA_AVAILABILITY_EVENT`: **813**
- `COMMUNICATION_GAP`: **0**
- `DATA_INTEGRITY_FAULT`: **0**
- `POSSIBLE_FREEZE`: **14,653**
- `PHYSICAL_SANITY_FAULT`: **0**
- `ml_eligible = true`: **288,915**; `false`: **813**

---

## 6. Freeze threshold

- Physical duration: **6 hours** (`FREEZE_DURATION_HOURS`, single constant).
- Derived row thresholds: Jena **36** consecutive readings, Delhi **72**.
- A single repeated value is NOT a freeze. NaN and communication-gap rows break runs.
- Flag name is `POSSIBLE_FREEZE` (candidate, never confirmed fault); rows stay ML eligible.

### Jena freeze events

- `temperature`: **0** qualifying run(s)
- `pressure`: **0** qualifying run(s)
- `humidity`: **16** qualifying run(s)
  - run_length=81 from `2010-12-23 20:00:00` to `2010-12-24 09:20:00`
  - run_length=59 from `2011-11-08 01:10:00` to `2011-11-08 10:50:00`
  - run_length=43 from `2011-11-09 04:40:00` to `2011-11-09 11:40:00`
  - run_length=92 from `2011-11-09 22:30:00` to `2011-11-10 13:40:00`
  - run_length=54 from `2011-11-10 17:00:00` to `2011-11-11 01:50:00`
  - run_length=52 from `2012-11-20 03:20:00` to `2012-11-20 11:50:00`
  - run_length=53 from `2012-12-20 02:20:00` to `2012-12-20 11:00:00`
  - run_length=209 from `2013-02-25 17:30:00` to `2013-02-27 04:10:00`
  - run_length=75 from `2013-02-27 23:40:00` to `2013-02-28 12:00:00`
  - run_length=42 from `2013-03-09 04:30:00` to `2013-03-09 11:20:00`
  - ... and 6 more

### Delhi freeze events

- `temperature`: **0** qualifying run(s)
- `pressure`: **0** qualifying run(s)
- `humidity`: **90** qualifying run(s)
  - run_length=80 from `2022-12-19 05:25:00` to `2022-12-19 12:00:00`
  - run_length=102 from `2022-12-20 02:40:00` to `2022-12-20 11:05:00`
  - run_length=144 from `2022-12-20 22:40:00` to `2022-12-21 10:35:00`
  - run_length=139 from `2022-12-21 22:15:00` to `2022-12-22 09:45:00`
  - run_length=143 from `2022-12-23 00:25:00` to `2022-12-23 12:15:00`
  - run_length=163 from `2022-12-25 23:40:00` to `2022-12-26 13:10:00`
  - run_length=147 from `2022-12-26 23:15:00` to `2022-12-27 11:25:00`
  - run_length=108 from `2023-01-02 00:10:00` to `2023-01-02 09:05:00`
  - run_length=74 from `2023-01-03 23:15:00` to `2023-01-04 05:20:00`
  - run_length=145 from `2023-01-04 22:00:00` to `2023-01-05 10:00:00`
  - ... and 80 more

---

## 7. Missing-data behavior

- Missingness is taken from the actual NaN state (identical to Phase 2 flags for Delhi; Jena has none).
- Missing values are never replaced, never converted to zero, never interpolated.
- Any row with a missing core value → `DATA_AVAILABILITY_EVENT`, `ml_eligible = false`.
- The Delhi 42-hour outage rows are therefore availability events, not sensor anomalies.

---

## 8. Gap behavior

- Jena: rows after the 5 structural timeline gaps exceed 15 min → `COMMUNICATION_GAP`.
- Delhi: timeline is strictly 5-minute; no communication gaps expected.
- Gaps are data-availability events (`ml_eligible = false`); nothing is interpolated or filled.

---

## 9. Physical sanity rules

- `RH < 0` → `PHYSICAL_SANITY_FAULT`; `RH > 100` → `PHYSICAL_SANITY_FAULT`.
- Non-finite (`inf`/`-inf`) core values → `PHYSICAL_SANITY_FAULT`.
- NaN is not a sanity fault (it is an availability event).

## 10. Why pressure thresholds are deliberately absent

A large share of Delhi observations falls outside 950–1030 hPa. Per the project
constitution and audit findings this reflects calibration/context, not proven sensor
failure. The Data Quality Layer therefore applies NO pressure thresholds; unusual
pressures keep `PASS`/`POSSIBLE_FREEZE` status and remain ML eligible for contextual
assessment later. Calling them faults here would contradict Decision 002.

## 11. Why 55 °C is not automatically rejected

No station-independent hard temperature limit is justified without calibration data,
and the PS explicitly requires distinguishing genuine extremes from sensor faults.
A 55 °C reading passes this layer (unless missing/impossible co-conditions apply) so the
future ensemble can judge it with temporal, multivariate, and spatial context.

---

## 12. Relationship to Phase 3

- Phase 3 outputs were NOT regenerated and are NOT duplicated here (106-column feature
  files remain the ML input format).
- Intended runtime path: observation → Data Quality Layer → if `ml_eligible` → Context
  Feature Engine (Phase 3 logic) → Detection Models; else → availability/integrity event.
- Phase 3 gap/segment logic is reused conceptually (same cadence constants would apply),
  but no Phase 3 code was rewritten for this phase.

---

## 13. Historical vs real-time operation

- Historical: `python -m src.data_quality.run` validates whole cleaned files at once
  (this report, executed in ~13.5 s).
- Real-time: `StreamingQualityEngine(dataset).check(reading)` applies the same rules
  per observation, keeping only previous timestamp/values, freeze counters, and seen
  timestamps. No FastAPI/WebSocket/frontend (future phases).
- Timestamp integrity passes on the cleaned Phase 2 datasets (duplicates were removed and
  order fixed in Phase 2); duplicate/out-of-order detection is proven by in-memory tests
  and remains active for live streams where such faults can still occur.

---

## 14. Validation results

- Batch validation: see pytest output.
- Determinism: re-running the batch command on identical inputs yields identical outputs
  (covered by `test_quality_output_deterministic` re-validating an in-memory sample twice).
- Pre-existing suites: Phase 1/2/3 tests untouched and still passing (see pytest output).

---

## 15. Existing test results

- `pytest -v tests/` must show all prior 25 tests passing plus the new Phase 2.5 tests.
- No ML, synthetic anomalies, NOAA/spatial, ensemble, root-cause, SHAP, degradation-risk,
  API, WebSocket, or frontend code was implemented in this phase.
