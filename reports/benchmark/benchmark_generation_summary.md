# SkyGuard AI — Controlled Fault-Injection Benchmark: Phase 5

**Project**: SIH 2026 PS 26073 — AI/ML-Based Anomaly Detection for Automatic Weather Stations
**Phase status**: Phase 5 complete (benchmark generation only; NO model trained).
**Nature**: controlled fault-injection benchmark on real weather observations — NOT fake weather data.

---

## 1. Objective and ground-truth methodology

- Known sensor faults (spike, frozen, drift, cross-variable, gaps, spike+drift combos) were
  injected into COPIES of Phase 2 processed data with seeded, recorded operations.
- Injected rows are ground truth (`ground_truth_anomaly = 1`) because the operation is controlled.
- Non-injected background rows (`ground_truth_anomaly = 0`) are NOT proven normal: they are
  non-injected background observations that may contain natural anomalies (e.g. the four known
  Delhi sub-zero readings and pressure regimes, which were deliberately NOT labeled).
- Clean pre-injection values are preserved separately in `ground_truth/*_injected_values.csv`
  (evaluation-only; never model inputs).

---

## 2. Sources, hashes, splits

- `jena`: `data/processed/jena_clean.csv` SHA-256 `36835cd1615a4655…`, 420,224 rows, 10-min cadence.
  - `train`: rows [0, 252134), 252,134 rows, `2009-01-01 00:10:00` → `2013-10-17 22:50:00`.
  - `test_in_distribution`: rows [252134, 336179), 84,045 rows, `2013-10-17 23:00:00` → `2015-05-25 06:20:00`.
  - `test_generalization`: rows [336179, 420224), 84,045 rows, `2015-05-25 06:30:00` → `2017-01-01 00:00:00`.
- `delhi`: `data/processed/delhi_clean.csv` SHA-256 `019de716920f3a09…`, 289,728 rows, 5-min cadence.
  - `train`: rows [0, 173836), 173,836 rows, `2022-04-01 00:00:00` → `2023-11-25 14:15:00`.
  - `test_in_distribution`: rows [173836, 231782), 57,946 rows, `2023-11-25 14:20:00` → `2024-06-13 19:05:00`.
  - `test_generalization`: rows [231782, 289728), 57,946 rows, `2024-06-13 19:10:00` → `2024-12-31 23:55:00`.

---

## 3. Parameter ranges (TRAIN/ID vs disjoint OOD)

| Fault | TRAIN / ID | OOD (disjoint) |
| :--- | :--- | :--- |
| SPIKE temp (°C abs) | 15–25 | 30–45 |
| SPIKE pressure (hPa abs) | 8–15 | 20–35 |
| SPIKE humidity (pp abs) | 15–25 | 30–45 |
| FROZEN (readings) | 3–10 | 15–30 |
| DRIFT temp (°C/h) | 0.5–1.5 | 2.0–4.0 |
| DRIFT pressure (hPa/h) | 1–3 | 5–8 |
| DRIFT humidity (pp/h) | 2–5 | 8–12 |
| CROSS duration (readings) | 3–10 | 15–30 (stronger rates) |
| GAP (minutes) | 30–120 | 120–360 |

- Spike durations 1–3 readings; drift TRAIN/ID 6–12 h, OOD 4–8 h; combos = OOD drift + OOD spike.
- TRAIN/ID contain single fault types only; OOD adds 20 SPIKE_PLUS_DRIFT combinations per dataset.
- Separation buffer between independent events: max event duration + 2 h per split.

---

## 4. Event counts and combinations

- `jena`: **380** sensor-fault events + **60** gap events, **7,004** injected rows, **0** skips.
- `delhi`: **380** sensor-fault events + **60** gap events, **12,118** injected rows, **0** skips.
- Combination events (OOD only, `fault_type = SPIKE_PLUS_DRIFT`, `fault_components = [SPIKE, DRIFT]`): 20 per dataset by target; shortfalls reported below.

---

## 5. Skipped candidates and row counts

- No skips: all event targets were placed with valid non-overlapping locations.

---

## 6. Communication gaps, reproducibility, validation

- Gap rows are genuinely absent (no NaN placeholders, no fill); manifests record start/end/duration/removed counts.
- Seed **26073** (SeedSequence-spawned per-dataset streams); re-running the command reproduces identical manifests, labels, values, and datasets (tested).
- Pipeline validation enforced: parameter ranges, OOD disjointness, split containment, non-overlap, buffer separation, RH bounds, label alignment (see manifest `event_validation`/`frame_validation`).
- All Phase 1–4 inputs hash-verified byte-identical before and after generation.

---

## 7. Reproduction

- Command: `python -m src.benchmark.run` (executed in ~15.0 s).
- NO Isolation Forest, LSTM, scoring, root-cause, SHAP, ensemble, NOAA/spatial, API, or frontend was implemented.
