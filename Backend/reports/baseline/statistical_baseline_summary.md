# SkyGuard AI — Traditional Statistical QC Baseline: Phase 4

**Project**: SIH 2026 PS 26073 — AI/ML-Based Anomaly Detection for Automatic Weather Stations
**Phase status**: Phase 4 complete (traditional QC comparison baseline; NOT an AI model).
**Safety check**: No ML, no synthetic anomalies, no input modifications, strictly causal.

---

## 1. Objective

Provide the conventional rolling-statistics reference that answers “would traditional QC
flag this observation?”, so future context-aware detectors can be measured against it
(baseline-vs-system comparison for the PPT). No detection accuracy is claimed here:
no labeled ground truth exists yet.

---

## 2. Why this is a traditional QC baseline (not AI)

- Fixed rolling moments and Tukey bounds; nothing is learned, fitted, or trained.
- Thresholds (|z| > 3.0, 1.5×IQR) are textbook conventions, documented as configuration.
- It is the comparison point, not the SkyGuard decision.

---

## 3. Datasets used (read-only)

| Dataset | Feature input | Quality input | Rows | Hash unchanged |
| :--- | :--- | :--- | ---: | :--- |
| Jena | `data/features/jena_features.csv` | `data/quality/jena_quality.csv` | 420,224 | **PASSED** |
| Delhi | `data/features/delhi_features.csv` | `data/quality/delhi_quality.csv` | 289,728 | **PASSED** |

Raw CSVs, `data/processed/`, and all other watched files were also hash-verified unchanged.

---

## 4. Two-hour causal window

- Primary baseline horizon: **2 hours** of previous observations (< t), same segment only.
- Jena (10-min cadence): **12** previous rows.
- Delhi (5-min cadence): **24** previous rows.
- Window sizes reuse `CADENCE_HORIZONS['2h']` from Phase 3 (no duplicated constants).

---

## 5. Z-score method

- Reuses Phase 3 `*_prev_mean_2h` / `*_prev_std_2h` directly (already causal, segment-contained).
- `z = (x - prev_mean_2h) / prev_std_2h`; std ≤ 1e-9 or missing → z = NaN (never forced).
- Flag threshold: **|z| > 3.0** (conventional configuration, not tuned, not optimal-claimed).

---

## 6. IQR method

- Causal rolling Q1/Q3 over the same 2h window (new minimal calculation; Phase 3 has no quartiles).
- Tukey bounds with factor **1.5**; 1 = outside, 0 = inside, NaN = insufficient history.
- Zero-width IQR still compares honestly (equal → 0, different → 1); NaN only for missing history.
- Both views are preserved side-by-side for future Z-vs-IQR-vs-ML comparisons.

---

## 7. Gap/segment and missing-data handling

- Windows never cross `segment_id` boundaries; new segments return NaN until history refills.
- Missing current values → NaN scores/flags; missing history → NaN; nothing imputed or zero-filled.
- Observations are never deleted or modified (55 °C stays 55 °C even when flagged).

---

## 8. Data-quality integration

- Rows with `ml_eligible = false` → `baseline_status = DATA_QUALITY_EXCLUDED`, all scores/flags NaN.
- Communication gaps therefore never become statistical anomalies in this layer.
- `POSSIBLE_FREEZE` is ML-eligible and processed normally when history allows.

---

## 9. Baseline flag counts

| Metric | Jena | Delhi |
| :--- | ---: | ---: |
| `rows` | 420,224 | 289,728 |
| `usable_rows` | 420,152 | 288,403 |
| `insufficient_history_rows` | 67 | 512 |
| `excluded_by_data_quality_rows` | 5 | 813 |
| `missing_input_rows` | 0 | 0 |
| `temperature_zscore_flags` | 21,585 | 10,109 |
| `pressure_zscore_flags` | 16,834 | 11,541 |
| `humidity_zscore_flags` | 25,211 | 12,819 |
| `temperature_iqr_flags` | 62,382 | 31,552 |
| `pressure_iqr_flags` | 55,743 | 30,396 |
| `humidity_iqr_flags` | 66,354 | 35,284 |
| `zscore_any_flag_rows` | 53,191 | 28,289 |
| `iqr_any_flag_rows` | 141,307 | 72,872 |
| `same_variable_both_views_rows` | 51,089 | 27,330 |
| `combined_baseline_flags` | 142,965 | 73,650 |
| `combined_flag_rate_usable` | 0.34027 | 0.255372 |
| `combined_flag_rate_all` | 0.340211 | 0.254204 |

High flag counts are reported descriptively; they are NOT precision/recall claims.
No 950–1030 hPa rule exists anywhere in this layer: pressure flags come only from
causal statistical context (proven by source-scan test).

---

## 10. Limitations and no-ground-truth statement

- No production anomaly labels exist, so accuracy/precision/recall/F1 are NOT reported.
- Thresholds are conventional, not calibrated for AWS faults; calibration is a later phase.
- Point-wise rolling rules have no multivariate/spatial context by design (that is the
  future ML gap this baseline exists to demonstrate).

---

## 11. Output schema and validation

- Columns (19): `timestamp`, `source_dataset`, `temperature_c`, `pressure_hpa`, `relative_humidity_pct`, `temperature_zscore_baseline`, `pressure_zscore_baseline`, `humidity_zscore_baseline`, `temperature_zscore_flag`, `pressure_zscore_flag`, `humidity_zscore_flag`, `temperature_iqr_flag`, `pressure_iqr_flag`, `humidity_iqr_flag`, `statistical_flags_available`, `statistical_anomaly_count`, `statistical_baseline_flag`, `statistical_baseline_reason`, `baseline_status`.
- Schema documented in `reports/baseline/baseline_schema.json`.
- Structural validation (schema, row counts, observation passthrough, exclusion consistency,
  flag/count consistency, segment-start safety) passed for both datasets.

---

## 12. Reproduction

- Command: `python -m src.baseline.run` (executed in ~18.3 s).
- Deterministic: identical inputs produce identical outputs (tested).
- No ML, synthetic anomalies, NOAA/spatial, ensemble, root-cause, SHAP, API, or frontend implemented.
