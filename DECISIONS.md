# SkyGuard AI — Architecture & Scientific Decisions

## Decision 001 — Preserve anomalous-looking observations

We are building an anomaly detector.

Therefore unusual observations must not be deleted during preprocessing.

Reason:
Deleting anomalies before detection creates biased training/evaluation data.

---

## Decision 002 — Do not use 950–1030 hPa as a Delhi fault threshold

A large fraction of Delhi observations fall outside that preliminary range.

Reason:
An unusual pressure value does not automatically imply sensor failure.

Decision:
Preserve pressure values and use contextual reasoning later.

---

## Decision 003 — Jena is temporal, not spatial

Jena is a single station.

Decision:
Use it for temporal/seasonal modeling.

Spatial consistency requires separate multi-station data.

---

## Decision 004 — NOAA ISD will provide spatial context

Future spatial layer will use multiple Indian stations.

Preferred implementation:
distance-weighted nearest-neighbor baseline.

Reason:
simple, explainable, fast, defensible.

Avoid unnecessary GNN complexity.

---

## Decision 005 — Data Quality before ML

Communication gaps and timestamp corruption are different from sensor anomalies.

Decision:

Data Quality Layer
→
ML only receives eligible observations

---

## Decision 006 — Causal features only

No future information may influence a feature for timestamp t.

This is required for valid offline evaluation and real-time deployment.

---

## Decision 007 — No raw global normalization during preprocessing

Raw physical measurements retain physical meaning.

Model-specific scaling/calibration happens later.

---

## Decision 008 — Synthetic anomalies are for benchmark ground truth

Historical suspicious observations are not automatically labels.

Controlled injection provides known ground truth for evaluating:

- detection
- root cause
- generalization

---

## Decision 009 — Unknown/Mixed root cause

A classifier must be able to say:

UNKNOWN / MIXED ANOMALY

rather than forcing a low-confidence class.

---

## Decision 010 — Ensemble scores must be calibrated

Isolation Forest score, LSTM reconstruction error and other signals have different numerical scales.

Normalize each component before combining.

---

## Decision 011 — Edge story is LSTM-only

Only the LSTM Autoencoder is a future TensorFlow Lite edge candidate.

Do not claim Isolation Forest or SHAP runs on ESP32.

---

## Decision 012 — Honest predictive-maintenance language

We use:

Sensor Degradation Risk Indicator

not:

Predictive Maintenance

unless an actual prognostics model is built and validated.