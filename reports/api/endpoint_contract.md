# Endpoint Contract (Phase 12)

All routes return JSON validated by Pydantic models in `src/api/schemas.py`.
Every response carries `data_mode: "historical_replay"` where applicable.

## GET /health

Infrastructure check. `{status, service: "skyguard-api", version,
data_mode, model_status: {statistical, isolation_forest, lstm_autoencoder,
ensemble, root_cause}}`. Status is `ok` only when every model loaded.

## GET /api/v1/health

Versioned health check (same schema as /health).

## GET /api/v1/stations

`{data_mode, stations: [{station_id, city, latitude, longitude, status,
data_available, data_mode, temperature, humidity, pressure,
anomaly_score, confidence, last_updated}]}`. Status: healthy | review |
anomaly | offline. Offline entries (AMD-06, HYD-07) carry nulls, never
fabricated values. NOAA stations report observations + spatial scores;
`confidence` is evidence completeness (FULL 1.0 / PARTIAL 0.67), not a
probability.

## GET /api/v1/stations/{station_id}

`{station, observations{temperature_c, relative_humidity_pct,
pressure_hpa}, data_quality{status, ml_eligible, flags}, anomaly{detected,
score, method, confidence}, root_cause{class, confidence},
spatial_context{available, neighbor_count, context_level}}`. Root cause is
null unless the frozen Phase 11 output provides a valid value. 404 for
unknown IDs and stations without backend data.

## GET /api/v1/stations/{station_id}/history?variable=&hours=

variable ∈ temperature | humidity | pressure (else 422); hours ∈ 1..168.
`{station_id, variable, hours, data_mode, points: [{timestamp, variable}]}`.
Missing values are null (never interpolated).

## GET /api/v1/alerts?limit=

Detected ensemble events (ID/OOD) with measured summaries, timestamp
descending. `limit` ∈ 1..1000 (default 100). Each alert: `{alert_id,
station_id, timestamp, status (anomaly|review), event, anomaly_score
(max ens_median over flagged rows), root_cause, root_cause_confidence
(mean over diagnosed rows), summary}`.

## GET /api/v1/alerts/{alert_id}

`{alert, observations, evidence[{title, detail, source}], history
(24h temperature), root_cause, explanation{text, features[{name, value,
contribution, direction}]}, ensemble_method: "ens_median"}`. SHAP wording
is associative ("contribution"), never causal. 404 for unknown IDs.

## GET /api/v1/network/summary

`{stations_monitored, healthy, needs_review, anomaly, offline,
network_health_pct, data_mode, last_updated}` — all counts computed from
backend states.
