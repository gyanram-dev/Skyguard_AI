# SkyGuard AI — Persistent Project Context

## Project Identity

Project:
SkyGuard AI

Hackathon:
Smart India Hackathon 2026

Problem Statement:
PS 26073

Title:
AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations

Organization:
Ministry of Earth Sciences / IMD

Theme:
Disaster Management

---

# Core Problem

The system must detect abnormal, inconsistent, faulty or suspicious AWS observations while distinguishing genuine meteorological events from sensor/data problems.

Core variables:

- Temperature
- Atmospheric Pressure
- Relative Humidity

Important desired capabilities:

- real-time anomaly detection
- spike detection
- frozen sensor detection
- drift detection
- communication/data-quality detection
- temporal/seasonal reasoning
- multivariate consistency
- spatial consistency
- confidence
- explainability
- root-cause classification
- sensor health/degradation trend
- optional corrected/inferred values

---

# Core Product Positioning

Do NOT position SkyGuard as:

"We built an anomaly detector using Isolation Forest and LSTM."

Position it as:

"A context-aware sensor-trust system."

The system asks:

"How trustworthy is this observation given the station's temporal behavior, agreement between its sensors, what nearby stations are seeing, and the station's historical reliability?"

---

# Blueprint Architecture

AWS stream
↓
Data Quality Layer
↓
Context Feature Engine
├── Temporal context
├── Multivariate context
├── Spatial context
└── Station history
↓
Detection Ensemble
├── Statistical baseline
├── Isolation Forest
├── LSTM Autoencoder
├── Multivariate consistency
└── Spatial consistency
↓
Calibrated Ensemble Score
↓
Anomalous?
├── No → Valid Observation
└── Yes
     ↓
Root-Cause Classifier
     ↓
SHAP + Severity
     ↓
Sensor Degradation Risk Indicator
     ↓
Live Alert / Dashboard

---

# Dataset Roles

## 1. Jena Climate

File:

jena_climate_2009_2016.csv

Processed:

data/processed/jena_clean.csv

Features:

data/features/jena_features.csv

Role:

Temporal-pattern training/validation.

Characteristics:

- 420,224 processed rows
- 10-minute cadence
- one station/location
- real seasonal and diurnal weather behavior

Do NOT use Jena to claim spatial consistency.

---

## 2. Delhi-NCR AWS

Raw:

AWS_20220401_20241231.csv

Processed:

data/processed/delhi_clean.csv

Features:

data/features/delhi_features.csv

Role:

Real Indian AWS validation and anomaly investigation.

Characteristics:

- 289,728 processed rows
- 5-minute cadence
- real Indian observations
- missing-data events exist
- known 42-hour outage
- four suspicious negative temperature observations

Preserve unusual values.

---

## 3. NOAA ISD

NOT YET IMPLEMENTED.

Future role:

Spatial consistency.

Plan:

- 5–10 Indian stations
- real coordinates
- simultaneous timestamps
- weighted nearest-neighbor comparison
- compare station observation to neighborhood expectation

Preferred approach:

simple distance-weighted baseline

NOT:

GNN

unless later evidence justifies it.

---

# Completed Phases

## Phase 1 — Data Audit

STATUS: COMPLETE

Key findings:

Jena:

- 420,551 raw rows
- 327 duplicate timestamps / redundant duplicate rows
- 2 out-of-order blocks
- 5 genuine timeline gaps
- no core missing values

Delhi:

- 289,728 raw rows
- 5-minute cadence
- missing core observations
- 42-hour complete outage
- 4 suspicious negative temperatures
- large pressure regimes outside preliminary analysis range

Scientific rule:

Those pressure regimes are NOT confirmed sensor faults.

---

# Phase 2 — Preprocessing

STATUS: COMPLETE

Jena:

420,551
→
420,224

Removed:

327 redundant duplicate copies

Preserved:

- genuine gaps
- all numerical observations
- extremes

Delhi:

289,728
→
289,728

Added:

- temperature_missing
- humidity_missing
- pressure_missing
- any_core_missing
- missing_core_count

No interpolation.

No imputation.

No clipping.

No normalization.

Raw SHA-256 hashes confirmed unchanged.

---

# Phase 3 — Feature Engineering

STATUS: COMPLETE

Outputs:

data/features/jena_features.csv
data/features/delhi_features.csv

Both:

106 columns

Feature categories:

1. Core observations and provenance
2. Quality/completeness context
3. Timeline gap/segment metadata
4. Cyclical temporal encoding
5. First-order dynamics
6. Frozen sensor/stability indicators
7. Causal rolling baselines
8. Local deviation metrics
9. Temporal trend slopes
10. Multivariate inconsistency metrics

Implemented concepts:

- elapsed time
- gap detection
- segment IDs
- causal rolling mean
- causal rolling std
- causal rolling median
- causal MAD
- robust local deviations
- slopes/trends
- rate of change
- absolute rate
- zero-delta ratios
- rolling stability
- cyclical hour/day-of-year features
- multivariate deviation metrics

Strict rule:

Rolling baselines use previous observations only.

Feature windows:

Jena:
- 30m = 3 rows
- 2h = 12 rows
- 6h = 36 rows

Delhi:
- 30m = 6 rows
- 2h = 24 rows
- 6h = 72 rows

No cross-segment rolling.

No future leakage.

Anti-leakage test passed.

---

# Current Validation

Current full test status:

25 tests passed.

Includes:

- audit tests
- preprocessing tests
- feature tests
- determinism
- segment containment
- anti-data-leakage

Feature pipeline command:

python -m src.features.run

Full tests:

pytest -v tests/

---

# Current Important Files

src/preprocessing/
src/features/

data/processed/
data/features/

reports/preprocessing/
reports/features/

tests/

---

# CURRENT STATE

Phase 1 ✅
Phase 2 ✅
Phase 3 ✅

Current next architectural requirement:

PHASE 2.5 — DATA QUALITY LAYER

This has NOT been implemented yet.

Do NOT rollback Phase 3.

---

# Phase 2.5 Objective

Build a deterministic Data Quality Gate BEFORE ML.

Responsibilities:

- timestamp validation
- duplicate detection
- out-of-order detection
- communication-gap detection
- missing-data availability events
- possible frozen sensor detection
- impossible RH sanity checks
- ML eligibility

Important distinction:

Data Quality Layer:
"Did the observation arrive correctly?"

ML layer:
"Is this physically/contextually suspicious?"

---

# Phase 2.5 Important Rules

Do NOT hard-code:

Delhi pressure < 950 = fault

Do NOT hard-code normal temperature ranges.

Do NOT reject 55°C merely because it is extreme.

Do NOT call unusual pressure regimes sensor drift.

Possible freeze should be:

POSSIBLE_FREEZE

not confirmed fault.

Proposed physical freeze threshold:

6 hours

Jena:
36 consecutive identical readings

Delhi:
72 consecutive identical readings

Possible freeze remains ML eligible.

Communication gaps are data availability events.

Physical sanity faults are not ML eligible.

---

# Next Major Phases

After Phase 2.5:

1. Statistical baseline
2. Controlled synthetic anomaly generation
3. Isolation Forest
4. NOAA multi-station spatial consistency
5. LSTM Autoencoder
6. Calibrated ensemble
7. Root-cause classifier + Unknown
8. SHAP
9. Sensor degradation risk
10. Real-time replay/API/WebSocket
11. Dashboard/demo

Do not implement all phases together.

---

# Synthetic Fault Benchmark

Planned anomaly classes:

- Spike
- Frozen
- Drift
- Communication gap
- Cross-variable inconsistency

Potential additional controlled faults may include:

- sudden drop
- noise

Communication gaps belong primarily to the Data Quality Layer, not the ML detector.

Evaluation must include held-out parameter ranges.

Example:

TRAIN:
- spike amplitude 15–25°C
- frozen duration 3–10 readings
- slow drift

TEST:
- spike amplitude 30–45°C
- frozen duration 15–30 readings
- faster drift
- unseen combinations

Never claim perfect generalization without measuring it.

---

# Non-Negotiable Scientific Principles

1. Do not delete anomalies during preprocessing.
2. Do not manufacture labels from suspicious historical observations.
3. Synthetic anomalies are controlled benchmark experiments, not fake weather data.
4. Do not call exploratory thresholds confirmed faults.
5. Do not use future values in real-time features.
6. Do not use Jena for spatial claims.
7. Use NOAA for spatial validation later.
8. Do not overengineer.
9. Measure before claiming improvement.
10. Never fabricate metrics.