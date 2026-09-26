# SkyGuard API Architecture (Phase 12)

Inference/serving layer over frozen Phase 1–11 artifacts. No retraining,
no threshold changes, no calibration, no tuning anywhere in `src/api`.

## Layout

- `src/api/app.py` — FastAPI app, versioned routes, CORS, logging, errors.
- `src/api/schemas.py` — explicit Pydantic v2 response models.
- `src/api/dependencies.py` — `DataStore`: startup loading + validation of
  every artifact (fail fast with exact causes), cached indexed frames.
- `src/api/services/` — read-only logic: stations, historical replay,
  alerts, investigation, network, health.
- `src/api/run.py` — `python -m src.api.run` (uvicorn programmatically);
  `uvicorn src.api.app:app` also works.
- `data/api/station_mapping.json` — frontend ↔ backend station mapping.

## Data flow

Frozen CSVs/joblibs/keras → `DataStore.load()` at startup (lifespan) →
indexed dicts/frames → request handlers do indexed lookups only. Model
artifacts (IF, LSTM + scalers, ensemble calibration, root-cause +
explainers) are LOADED at startup; `model_status` reports `loaded` only
on successful load, else `unavailable` (never fake data, never silent).

## Historical replay

No physical real-time stream exists. `HistoricalReplay` exposes the
latest timestamp per source and reads backward. Every response carries
`data_mode: "historical_replay"`. A future streaming adapter replaces
`observation_service.py` without schema changes.

## Performance

Indexed timestamp dicts, startup caching, no per-request scans, no
training in handlers, SHAP reused from Phase 11 artifacts (parsed
`shap_top5` strings; no recomputation per request).

## Errors

404 unknown station/alert or station without backend data; 422 invalid
variable/query; 503 datastore unavailable; 500 structured JSON without
stack traces. CORS restricted to `SKYGUARD_ALLOWED_ORIGINS`
(default `http://localhost:3000,http://localhost:5173`).
