# AWS Feature Engineering & Validation Report: Phase 3

**Project**: SIH PS 26073 — AI/ML-Based Anomaly Detection for Automatic Weather Stations
**Phase Status**: Phase 3 Complete (Causal Temporal & Multivariate Feature Generation).
**Safety Check**: STRICT CAUSALITY VERIFIED. ZERO FUTURE DATA LEAKAGE.

---

## 1. Compliance and Scope Declaration

- **No anomaly labels were generated in Phase 3.**
- **No synthetic anomalies were generated in Phase 3.**
- **No machine-learning model was trained in Phase 3.**
- **No global normalization or scaling was fitted across rows.**
- **No interpolation or NaN filling occurred.**

---

## 2. Input Datasets & Immutability Verification

| Dataset | Input File Path | Rows | SHA-256 Before | SHA-256 After | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Jena Clean | `data/processed/jena_clean.csv` | 420,224 | `36835cd1615a46558d1cdb570ff27aa2b7c0c9ba373bd067841b9503ee18021d` | `36835cd1615a46558d1cdb570ff27aa2b7c0c9ba373bd067841b9503ee18021d` | **PASSED (Identical)** |
| Delhi Clean | `data/processed/delhi_clean.csv` | 289,728 | `019de716920f3a093aca1f4b772ab6fadcfc6621cf02421a37acbe5c53f08766` | `019de716920f3a093aca1f4b772ab6fadcfc6621cf02421a37acbe5c53f08766` | **PASSED (Identical)** |

---

## 3. Sampling-Aware Window Horizons

Semantic physical time horizons are converted to dataset-specific row windows based on native sampling cadences without cross-resampling:

| Physical Time Horizon | Jena Row Window (10-min cadence) | Delhi Row Window (5-min cadence) | Purpose in PS 26073 |
| :--- | :--- | :--- | :--- |
| **30 Minutes** | 3 rows | 6 rows | Micro-scale rate of change, sharp impulse/spike detection |
| **2 Hours** | 12 rows | 24 rows | Local baseline, short-term volatility, frozen sensor detection |
| **6 Hours** | 36 rows | 72 rows | Diurnal trend, synoptic drift, multivariate deviation |

---

## 4. Feature Architecture & Categories

Total features generated: **106 columns** organized logically into 10 groups:
1. **Core Observations & Provenance** (5 cols): `timestamp`, `source_dataset`, `temperature_c`, `pressure_hpa`, `relative_humidity_pct`.
2. **Quality & Completeness Context** (7 cols): `temperature_missing`, `humidity_missing`, `pressure_missing`, `any_core_missing`, `missing_core_count`, `valid_core_count`, `all_core_valid`.
3. **Timeline Gap & Segment Metadata** (3 cols): `elapsed_minutes_since_prev`, `gap_before`, `segment_id`.
4. **Cyclical Temporal Encodings** (4 cols): `hour_sin`, `hour_cos`, `day_of_year_sin`, `day_of_year_cos`.
5. **First-Order Dynamics** (9 cols): delta, rate-per-hour, absolute rate-per-hour for temperature, pressure, and humidity.
6. **Frozen Sensor & Stability Indicators** (9 cols): zero delta indicator, 2h zero-delta ratio, and 2h rolling std for each core variable.
7. **Causal Rolling Baselines** (36 cols): mean, std, median, MAD over previous 30m, 2h, and 6h windows ($< t$).
8. **Local Deviation Metrics** (18 cols): raw deviation from median and robust standardized deviation for each variable across 30m, 2h, and 6h.
9. **Temporal Trend Slopes** (9 cols): causal linear regression slopes over 30m, 2h, and 6h.
10. **Multivariate Inconsistency** (6 cols): maximum absolute robust deviation and deviation range across the core triad across 30m, 2h, and 6h.

---

## 5. Strict Anti-Data-Leakage Verification

An automated perturbation experiment was conducted for both datasets:
- An arbitrary observation at index $k = 50$ was perturbed with a +50.0 shock.
- Features were recomputed on the perturbed series.
- **Jena Anti-Leakage Outcome**: **PASSED** (Max difference across all prior timestamps $t < k$: `0.0e+00`).
- **Delhi Anti-Leakage Outcome**: **PASSED** (Max difference across all prior timestamps $t < k$: `0.0e+00`).
- **Conclusion**: Changing future observations has zero effect on historical or current feature values. Causality is strictly proven.

---

## 6. Gap & Segment Containment

- **Jena Climate**: All 5 structural timestamp gaps were detected. Immediately following each gap, the rolling baselines evaluate to `NaN` because observations from the preceding segment are strictly quarantined.
- **Delhi-NCR AWS**: The 42-hour outage (504 rows) is preserved with `any_core_missing = 1`, and rolling windows traversing the outage evaluate to `NaN` until sufficient valid history is accumulated.

---

## 7. Output Datasets Summary

| Dataset | File Path | Row Count | Column Count | Execution Time |
| :--- | :--- | :--- | :--- | :--- |
| Jena Features | `data/features/jena_features.csv` | 420,224 | 106 | ~83.8s total |
| Delhi Features | `data/features/delhi_features.csv` | 289,728 | 106 | ~83.8s total |