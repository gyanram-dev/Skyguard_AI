# AWS Data Preprocessing & Standardization Report: Phase 2

**Project**: SIH PS 26073 — AI/ML-Based Anomaly Detection for Automatic Weather Stations
**Phase Status**: Phase 2 Complete (Standardization & Preprocessing Only).
**Safety Check**: No ML models, no synthetic anomalies, no normalization/scaling, no raw file modifications.

---

## 1. Input Files & Raw Data Immutability

| Dataset | Input File Path | Size (Bytes) | SHA-256 Pre-Processing | SHA-256 Post-Processing | Immutability Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Jena Climate | `D:\Sky\jena_climate_2009_2016.csv` | 43,164,220 | `9626d3964f7afb3fa94b6f3d3a0e92fe96e4a4477c31ed9875cc64d6717c129f` | `9626d3964f7afb3fa94b6f3d3a0e92fe96e4a4477c31ed9875cc64d6717c129f` | **PASSED (Identical)** |
| Delhi-NCR AWS | `D:\Sky\AWS_20220401_20241231.csv` | 24,751,027 | `f22119b81268cd010366a868c021fadb70487e766bff86a43434021d320d864e` | `f22119b81268cd010366a868c021fadb70487e766bff86a43434021d320d864e` | **PASSED (Identical)** |

---

## 2. Standardized Core Output Schema
Both datasets were standardized into the project-wide core schema without mixing or resampling:

| Standard Column | Semantic Role | Physical Unit | Present in Jena | Present in Delhi | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `timestamp` | Datetime identifier | ISO-8601 (`YYYY-MM-DD HH:MM:SS`) | Yes | Yes | Parsed strictly without silent coercion |
| `temperature_c` | Surface Air Temperature | °C (Celsius) | Yes | Yes | Original physical values preserved without clipping |
| `pressure_hpa` | Atmospheric Barometric Pressure | hPa / mbar | Yes | Yes | 1 mbar = 1 hPa; numeric values untouched |
| `relative_humidity_pct` | Relative Humidity | % [0-100] | Yes | Yes | Original physical values preserved |
| `source_dataset` | Station/Dataset origin | string metadata | Yes (`jena`) | Yes (`delhi`) | Retains dataset provenance |

---

## 3. Jena Climate Preprocessing Summary
- **Raw Row Count**: **420,551**
- **Processed Row Count**: **420,224**
- **Duplicate Records Handled**: Detected **327** redundant exact duplicate copies (from historical re-appended blocks); removed exactly **327** rows, retaining exactly one valid copy of each timestamp.
- **Chronological Sorting**: Sorted ascending by `timestamp`. Output timeline is strictly unique and monotonic increasing.
- **Genuine Timestamp Gaps**: Preserved exactly as absent observations without interpolation, forward-filling, or synthetic creation. All 5 known gaps (>10 min) remain intact (maximum gap: 3 days 2 hours 20 minutes).
- **Missing Value Preservation**: Remains **0 missing cells** across all core variables.
- **Extreme Observations Preserved**:
  - Temperature range: `[-23.01°C, 37.28°C]` (mean: 9.44°C)
  - Pressure range: `[913.60 hPa, 1015.35 hPa]` (mean: 989.21 hPa)
  - Humidity range: `[12.95%, 100.00%]` (mean: 76.03%)
- **Validation Suite Result**: **11/11 tests passed (100% PASSED)**.

---

## 4. Delhi-NCR AWS Preprocessing Summary
- **Raw Row Count**: **289,728**
- **Processed Row Count**: **289,728** (0 rows dropped).
- **Sampling Cadence**: Strictly uniform 5-minute intervals across all 289,728 rows.
- **Missing Value & Quality Metadata Flags Added**:
  - `temperature_missing`: **807** missing observations flagged
  - `humidity_missing`: **807** missing observations flagged
  - `pressure_missing`: **811** missing observations flagged
  - `any_core_missing`: **813** timestamps with $\ge 1$ missing core variable
  - `missing_core_count`: Exactly **806** timestamps with all 3 missing, **7** with exactly 1 missing, and **288,915** fully complete timestamps.
- **Complete Outage Preservation**: The known 42-hour continuous outage (504 consecutive intervals from `2022-04-05 17:45:00` to `2022-04-07 11:40:00`) remains completely preserved as NaNs with quality flags.
- **Candidate Suspicious Temperatures Preserved**: All **4 candidate negative temperature observations** (down to -37.89°C on April 5, 2022) were preserved unchanged for subsequent anomaly detection phases.
- **Pressure Regimes Preserved**: All **170,313 observations < 950 hPa** and **1,284 observations > 1030 hPa** were preserved completely unaltered without artificial clipping or thresholding.
- **Validation Suite Result**: **14/14 tests passed (100% PASSED)**.

---

## 5. Output Processed Files & Schemas

| Dataset | Output CSV Path | Row Count | Column Count | File Size (Bytes) |
| :--- | :--- | :--- | :--- | :--- |
| Jena Climate (Processed) | `D:\Sky\data\processed\jena_clean.csv` | 420,224 | 5 | 18,402,413 |
| Delhi-NCR AWS (Processed) | `D:\Sky\data\processed\delhi_clean.csv` | 289,728 | 10 | 18,371,572 |

---

## 6. Raw → Processed Transformation Traceability Matrix

| Dataset | Transformation Step | Rationale | Expected Row Impact | Numerical Modification |
| :--- | :--- | :--- | :--- | :--- |
| Jena | Timestamp Parsing (`%d.%m.%Y %H:%M:%S`) | Standardize to ISO-8601 representation | None | None |
| Jena | Core Column Standardization | Match unified project schema | None | None |
| Jena | Deduplicate Exact Copies (327 rows) | Remove historical block re-appending error | 420,551 → 420,224 (-327) | None |
| Jena | Chronological Ascending Sort | Establish strictly monotonic timeline | None | None |
| Jena | Preserve Genuine Gaps | Retain physical logger downtime information | None | None (no interpolation) |
| Delhi | Timestamp Parsing (`%d-%m-%Y %H:%M`) | Standardize to ISO-8601 representation | None | None |
| Delhi | Core Column Standardization | Match unified project schema | None | None |
| Delhi | Preserve Full Timeline | Retain continuous 5-minute sampling structure | None (289,728 → 289,728) | None |
| Delhi | Add Missing Quality Flags | Explicit metadata for communication/sensor outages | None | None (no NaN imputation) |
| Delhi | Preserve Candidate Anomalies | Preserve sub-zero temps and pressure regimes for ML | None | None (no clipping/filtering) |

---

## 7. Observations, Warnings & Candidate Anomalies Status
1. **Candidate Anomaly Classification**: The 4 negative temperature readings in Delhi (around -37.9°C) remain classified as **candidate anomalous observations** for subsequent investigation. The 171,597 observations outside the preliminary 950–1030 hPa range are retained as observations requiring further investigation and are **not** treated as confirmed anomalies, sensor faults, or sensor drift. They were neither dropped nor altered.
2. **Zero Numerical Normalization**: Neither dataset was subjected to standard scaling, min-max scaling, winsorization, or clipping. The data retains its physical meteorological meaning.
3. **Station Separation Maintained**: Datasets remain separate in `data/processed/jena_clean.csv` and `data/processed/delhi_clean.csv` to account for their distinct temporal cadences (10-min vs 5-min) and regional climatology.