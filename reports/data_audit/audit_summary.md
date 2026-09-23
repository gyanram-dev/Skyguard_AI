# AWS Data Audit Summary Report: Phase 1 — Evidence-Based Audit

**Problem Statement**: SIH PS 26073 — AI/ML-Based Anomaly Detection for Automatic Weather Stations
**Status**: Phase 1 Complete (Audit Only). No raw data modified, cleaned, or imputed.

---

## 1. Raw Data Integrity & Checksum Verification

| Dataset | File Path | File Size (Bytes) | Pre-Audit SHA-256 | Post-Audit SHA-256 | Integrity Maintained |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Jena Climate | `D:\Sky\jena_climate_2009_2016.csv` | 43,164,220 | `9626d3964f7a...` | `9626d3964f7a...` | **PASSED (Identical)** |
| Delhi-NCR AWS | `D:\Sky\AWS_20220401_20241231.csv` | 24,751,027 | `f22119b81268...` | `f22119b81268...` | **PASSED (Identical)** |

---

## 2. Dataset Inventory & Schema

| Attribute | Jena Climate (2009–2016) | Delhi-NCR AWS (2022–2024) |
| :--- | :--- | :--- |
| **Raw File Name** | `jena_climate_2009_2016.csv` | `AWS_20220401_20241231.csv` |
| **Total Rows** | 420,551 | 289,728 |
| **Total Columns** | 15 | 10 |
| **Timestamp Column** | `Date Time` | `Date_Time_IST` |
| **Start Timestamp** | `2009-01-01 00:10:00` | `2022-04-01 00:00:00` |
| **End Timestamp** | `2017-01-01 00:00:00` | `2024-12-31 23:55:00` |
| **Timezone Reference** | No explicit offset in headers/strings (Jena, Germany / CET-CEST) | Indian Standard Time (IST, UTC+05:30) indicated in column header |
| **Expected Interval** | 10 minutes | 5 minutes |
| **Dominant Cadence** | 0 days 00:10:00 (420,218 occurrences) | 0 days 00:05:00 (289,727 occurrences) |

---

## 3. Core Meteorological Variables Audit

### A. Source Columns & Unit Mapping

| Variable Role | Jena Column | Jena Unit | Delhi Column | Delhi Unit |
| :--- | :--- | :--- | :--- | :--- |
| Air Temperature | `T (degC)` | degC | `Air_Temp` | °C (standard Celsius) |
| Atmospheric Pressure | `p (mbar)` | mbar (hPa) | `Atm_Pres` | hPa / mbar |
| Relative Humidity | `rh (%)` | % | `Rel_Hum` | % |

### B. Empirical Distributions & Descriptive Statistics

| Dataset | Variable | Missing Count (%) | Min | 1% | 25% | Median | Mean | 75% | 99% | Max | Std Dev |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Jena | `T (degC)` | 0 (0.0%) | -23.01 | -10.09 | 3.36 | 9.42 | 9.45 | 15.47 | 28.44 | 37.28 | 8.42 |
| Jena | `p (mbar)` | 0 (0.0%) | 913.60 | 966.89 | 984.20 | 989.58 | 989.21 | 994.72 | 1007.74 | 1015.35 | 8.36 |
| Jena | `rh (%)` | 0 (0.0%) | 12.95 | 35.13 | 65.21 | 79.30 | 76.01 | 89.40 | 99.40 | 100.00 | 16.48 |
| Delhi | `Air_Temp` | 807 (0.2785%) | -37.89 | 7.02 | 19.94 | 26.77 | 25.25 | 30.66 | 40.74 | 46.79 | 7.81 |
| Delhi | `Atm_Pres` | 811 (0.2799%) | 834.92 | 849.23 | 907.17 | 936.67 | 935.56 | 972.78 | 1008.32 | 1086.67 | 39.66 |
| Delhi | `Rel_Hum` | 807 (0.2785%) | 9.68 | 15.59 | 49.33 | 70.19 | 66.81 | 86.26 | 100.00 | 100.00 | 23.84 |

---

## 4. Duplicate & Chronological Order Audit

### A. Duplicate Analysis
- **Jena Climate**:
  - Completely duplicated rows: **654** rows.
  - Unique duplicate timestamps: **327** timestamps (total rows involved = **654**).
  - Row identity check: **100% of duplicated timestamp records are exact identical row copies** across all 15 columns (`identical_values = True`).
- **Delhi-NCR AWS**:
  - Completely duplicated rows: **0**.
  - Duplicate timestamps: **0**.
  - Timeline uniqueness: Completely unique timestamps throughout.

### B. Out-of-Order Blocks & Transitions
- **Jena Climate**:
  - Detected **2 negative timestamp transitions** in raw row sequence:
    1. **Row 78766**: `01.07.2010 00:10:00` follows `02.07.2010 00:00:00` (step delta = `-1 day 00:10:00`). Block spans 144 records (an entire 24h day of July 1, 2010).
    2. **Row 274565**: `20.03.2014 11:00:00` follows `21.03.2014 17:20:00` (step delta = `-2 days 17:40:00`). Block spans 183 records.
  - **Key Structural Finding**: `144 + 183 = 327 rows`. The two out-of-order blocks are **the exact source** of the 327 duplicate rows in Jena, caused by accidental duplicate appending during historical data compilation.
- **Delhi-NCR AWS**:
  - Out-of-order transitions: **0** (strictly monotonic chronological ordering preserved).

---

## 5. Timeline Gap Audit (Cadence Deviations)

- **Jena Climate** (evaluated on sorted, deduplicated series):
  - Total gaps > 10 min: **5** gaps (accounting for **544** missing observations).
  - Gaps inventory:
    1. `2009-10-08 09:40:00` to `10:10:00` (30 min duration, 2 missing steps).
    2. `2013-05-16 08:50:00` to `09:10:00` (20 min duration, 1 missing step).
    3. `2014-07-30 08:00:00` to `08:20:00` (20 min duration, 1 missing step).
    4. `2014-09-24 17:00:00` to `2014-09-25 09:00:00` (16 hours duration, 95 missing steps).
    5. `2016-10-25 10:30:00` to `2016-10-28 12:50:00` (3 days 2 hours 20 minutes duration, 445 missing steps).
- **Delhi-NCR AWS**:
  - Total gaps > 5 min: **0**.
  - Timeline is completely continuous across all 289,728 rows (no missing timestamps).

---

## 6. Missing Data Audit (Observation Cells)

### A. Jena Climate:
- Zero missing values across all 15 columns. All missingness is manifested strictly as timestamp gaps.

### B. Delhi-NCR AWS:
- **Core Variables Missing Counts**:
  - `Air_Temp`: **807** (0.2785%)
  - `Rel_Hum`: **807** (0.2785%)
  - `Atm_Pres`: **811** (0.2799%)
- **Joint Missingness Breakdown**:
  - All three core variables missing: **806** timestamps
  - Exactly one core variable missing: **7** timestamps (5 Atm_Pres isolated, 1 Air_Temp isolated, 1 Rel_Hum isolated)
  - Exactly two core variables missing: **0** timestamps
  - Complete observations (all 3 present): **288,915** timestamps
- **Consecutive Missing Runs**:
  - `Air_Temp`: **31 runs**, shortest = **1**, longest = **504 steps** (42.0 hours from `2022-04-05 17:45:00` to `2022-04-07 11:40:00`).
  - `Atm_Pres`: **33 runs**, shortest = **1**, longest = **504 steps** (42.0 hours from `2022-04-05 17:45:00` to `2022-04-07 11:40:00`).
  - `Rel_Hum`: **32 runs**, shortest = **1**, longest = **504 steps** (42.0 hours from `2022-04-05 17:45:00` to `2022-04-07 11:40:00`).

---

## 7. Candidate Suspicious Observations (Delhi-NCR AWS)

> [!WARNING]
> In accordance with Phase 1 scientific principles, the following observations are flagged as **candidate anomalies** for investigation. They are **NOT** automatically classified as sensor faults or deleted.

### A. Candidate Suspicious Temperatures (Air_Temp < 0°C in Delhi)

Found exactly **4 observations** with sub-zero temperatures (ranging from **-37.89°C** to **-5.49°C**):

| Row Index | Timestamp | Temperature (°C) | Previous Temp (°C) | Next Temp (°C) | Pressure (hPa) | RH (%) | Delta From Prev (°C) | Delta To Next (°C) | Context / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1162 | `2022-04-05 00:50:00` | **-37.88** | 25.62 | 25.99 | NaN | 26.5 | -63.51 | +63.87 | Spike down from +25°C; Pres is NaN |
| 1171 | `2022-04-05 01:35:00` | **-5.49** | 22.67 | 21.54 | NaN | 27.6 | -28.16 | +27.03 | Isolated sub-zero pulse; Pres is NaN |
| 1173 | `2022-04-05 01:45:00` | **-37.89** | 21.54 | 5.19 | NaN | 27.6 | -59.43 | +43.08 | Isolated sub-zero pulse; Pres is NaN |
| 1262 | `2022-04-05 09:10:00` | **-37.87** | nan | nan | NaN | 26.8 | +nan | +nan | Preceded by NaN run |

### B. Candidate Suspicious Pressure Regimes (Atm_Pres < 950 or > 1030 hPa)

- **Total candidate observations**: **171,597** (59.2269%)
  - Below 950 hPa: **170,313** observations (minimum = **834.92 hPa**)
  - Above 1030 hPa: **1,284** observations (maximum = **1086.67 hPa**)
- **Regime Structuring**: Grouped contiguous observations into **629 distinct regimes**.
- **Interpretation**: The high frequency of observations < 950 hPa (median = 936.7 hPa) indicates a persistent sensor offset or station elevation calibration factor (~600–700m effective pressure altitude vs Delhi actual ~216m) combined with large seasonal/diurnal swings down to 835 hPa (which would mimic 1500m elevation) and periodic spikes up to 1086 hPa (exceeding Earth surface historical records). Grouping into regimes is essential for distinguishing persistent sensor calibration drift from transient pressure shocks.

---

## 8. Candidate Multivariate Anomalies

Evaluated using robust step-delta standardized Z-scores ($Z_{\Delta} = |\Delta - \text{median}| / \text{IQR}$).
Flagged candidate anomalies where one variable displays an extreme single-step jump ($Z_{\Delta} > 8$) while the other two remain strictly quiescent ($Z_{\Delta} \le 2$):
- **Isolated Temperature Jumps**: **38** observations
- **Isolated Pressure Jumps**: **211** observations
- **Isolated Humidity Jumps**: **75** observations
- **Total Candidate Multivariate Inconsistencies**: **324** observations (detailed in `delhi_multivariate_candidates.csv`).

---

## 9. Scientific Distinction: Data Integrity vs Candidate Anomalies

| Finding | Category | Nature | Proposed Phase 2 Treatment |
| :--- | :--- | :--- | :--- |
| Jena 327 duplicate rows | **Confirmed Data Integrity Issue** | Re-appended identical historical blocks | Safe deduplication / removal of duplicate block in preprocessed copy |
| Jena out-of-order blocks | **Confirmed Data Integrity Issue** | Appending chronology error | Chronological sorting of timeline |
| Jena 5 timestamp gaps | **Confirmed Data Integrity Issue** | Station power/logger downtime | Gap-aware time-series indexing / mask generation |
| Delhi missing observation runs | **Confirmed Data Integrity Issue** | AWS communication/sensor outage | Missingness masking (no naive zero-filling) |
| Delhi sub-zero temps (-37.9°C) | **Candidate Sensor Anomaly** | Extreme impossible temperature spike | Sensor fault flag (spurious electrical reading/open circuit) |
| Delhi <950 hPa pressure regime | **Candidate Sensor Anomaly / Drift** | Sensor calibration offset & drift | Baseline offset adjustment & drift tracking |
| Delhi >1080 hPa pressure spikes | **Candidate Sensor Anomaly** | Unphysical barometric spike | High-pressure anomaly flag |
| Single-variable jumps (Delhi) | **Candidate Multivariate Anomaly** | Physically uncoupled step shock | Multivariate anomaly flag |

---

## 10. Audit Artifacts Produced

- `reports/data_audit/audit_summary.md` (This document)
- `reports/data_audit/jena_audit.json` (Serialized Jena metrics)
- `reports/data_audit/delhi_audit.json` (Serialized Delhi metrics)
- `reports/data_audit/jena_duplicates.csv` (Jena duplicate timestamps breakdown)
- `reports/data_audit/jena_gaps.csv` (Jena timestamp gaps > 10 min)
- `reports/data_audit/jena_out_of_order.csv` (Jena out-of-order transitions)
- `reports/data_audit/delhi_missing_runs.csv` (Delhi consecutive missing runs)
- `reports/data_audit/delhi_suspicious_temperature.csv` (Delhi negative temperature records)
- `reports/data_audit/delhi_suspicious_pressure.csv` (Delhi candidate pressure regimes)
- `reports/data_audit/delhi_multivariate_candidates.csv` (Delhi candidate multivariate anomalies)