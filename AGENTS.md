# SkyGuard AI — Engineering Constitution

## Project

SkyGuard AI is an SIH 2026 software project for:

PS 26073 — AI/ML-Based Intelligent Anomaly Detection for Automatic Weather Stations

Primary objective:

Build a context-aware AWS sensor-trust system that determines whether an observation is trustworthy using:

1. data integrity
2. temporal context
3. multivariate consistency
4. spatial consistency
5. station history

The system must detect anomalies, distinguish sensor faults from genuine meteorological events where possible, minimize false alarms, explain decisions, classify likely root causes, and support real-time operation.

---

# NON-NEGOTIABLE ENGINEERING RULES

## 1. Work phase-by-phase

Never implement multiple future phases at once.

Before changing code:

1. inspect the existing implementation
2. inspect tests
3. inspect reports
4. inspect current phase status
5. understand the existing architecture
6. modify only the current phase

After implementation:

1. run tests
2. inspect generated outputs
3. review code for unnecessary complexity
4. update documentation
5. stop at the phase boundary

---

## 2. Never destroy previous work

Existing completed phases are authoritative unless a concrete bug is demonstrated.

Do NOT rewrite or replace previous phases merely because a cleaner implementation is possible.

Prefer additive, backward-compatible changes.

---

## 3. Data scientific integrity

Never delete an observation simply because it is unusual.

This project detects sensor anomalies.

Therefore preserve unusual but physically possible observations.

Never silently:

- interpolate
- forward-fill
- backward-fill
- clip
- winsorize
- normalize raw observations
- replace missing values
- fabricate readings

unless a later phase explicitly requires a controlled transformation.

---

## 4. Raw data is immutable

Never modify the original datasets.

Raw inputs:

- jena_climate_2009_2016.csv
- AWS_20220401_20241231.csv

Always preserve SHA-256 integrity.

---

## 5. Important scientific decisions

Jena:

- used for temporal/seasonal behavior
- single station
- NOT suitable for spatial-consistency claims

Delhi-NCR AWS:

- real Indian AWS observations
- useful for Indian validation and anomaly investigation

NOAA ISD multi-station Indian data:

- required later for spatial consistency
- use 5–10 Indian stations
- compare current station against nearby stations
- simple distance-weighted neighborhood is preferred
- do NOT build a GNN unless future evidence justifies it

---

## 6. Pressure rule

Do NOT use the preliminary Delhi 950–1030 hPa range as a hard anomaly threshold.

Many observations fall outside this range.

Those observations are retained.

Do not call them confirmed faults or sensor drift without evidence.

---

## 7. Suspicious temperature rule

The approximately -37.9°C Delhi readings are retained as candidate anomalous observations.

They are NOT ground-truth labels.

---

## 8. Feature causality

All real-time feature calculations must be causal.

For timestamp t:

- current observation may be used
- previous observations may be used
- future observations may NEVER be used

Rolling baselines, trends, deviations and temporal features must not leak future information.

---

## 9. Missing-data rule

Missing values are meaningful.

Never convert missingness to zero.

Preserve missingness explicitly.

Use quality flags where appropriate.

---

## 10. Gap rule

Do not let rolling windows cross structural timestamp gaps.

Use segment boundaries.

A communication/data-availability event should be separated from a sensor anomaly.

---

## 11. Architecture direction

Target architecture:

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
Anomaly decision
↓
Root-Cause Classifier
↓
SHAP explanation
↓
Sensor Degradation Risk Indicator
↓
Live alert/dashboard

---

## 12. Model philosophy

Do not add ML models just to make the project sound advanced.

Preferred progression:

1. deterministic data quality
2. statistical baseline
3. Isolation Forest
4. temporal LSTM Autoencoder
5. multivariate consistency
6. spatial consistency
7. calibrated ensemble
8. root-cause classification
9. explainability

Each addition must have a measurable reason.

---

## 13. Ensemble score rule

Never average heterogeneous raw scores directly.

Component outputs must be normalized/calibrated against appropriate validation distributions before combination.

---

## 14. Root-cause rule

Root-cause classifier must have:

- Spike
- Frozen
- Drift
- Cross-Variable
- Unknown/Mixed

Never force a low-confidence prediction into a known class.

---

## 15. Evaluation rule

Never report fabricated performance.

Report:

- Precision
- Recall
- F1
- FPR
- FNR
- root-cause macro F1
- confusion matrix
- inference latency
- throughput
- generalization performance

Where possible compare:

in-distribution
vs.
held-out parameter ranges
vs.
unseen anomaly combinations

---

## 16. Coding style

Prefer:

- Python
- Pandas
- NumPy
- scikit-learn
- TensorFlow/Keras only when required
- FastAPI later
- React later

Use:

- small focused modules
- type hints where useful
- deterministic functions
- explicit names
- snake_case
- minimal abstractions

Do NOT create frameworks inside the project.

Do NOT add libraries without a concrete need.

---

## 17. Review standard

After every phase ask:

- Is this scientifically justified?
- Is this required by the PS?
- Is this supported by the blueprint?
- Does it introduce leakage?
- Does it duplicate existing functionality?
- Can it run in real time?
- Can we explain it to a judge?
- Are the reported metrics actually measured?

If the answer is no, reconsider the implementation.

---

## 18. Phase boundary

A phase is complete only when:

- implementation works
- tests pass
- output is inspected
- report is updated
- no future phase has been silently implemented

STOP at the requested phase.