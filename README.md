# SkyGuard AI

Context-aware weather-station sensor-trust system (SIH 2026, PS 26073):
detect abnormal Automatic Weather Station observations, distinguish sensor
faults from genuine weather, explain decisions, and classify likely root
causes — served through a FastAPI backend and a React dashboard.

Current data mode is **historical replay**: the backend replays validated
historical observations through the frozen inference pipeline. It is not a
physical live AWS connection, and the UI labels it honestly.

## Architecture

```
Historical AWS / benchmark observations
        ↓
FastAPI backend (Backend/)
  Data Quality → Context Features → Detection Ensemble
  (statistical, Isolation Forest, LSTM) → Calibrated Score
  + Freeze confirmation (deterministic, measured) → Root-Cause Classifier
  → SHAP explanation
        ↓  REST /api/v1/*  +  POST /api/v1/demo/probe  +  WS /api/v1/live
React dashboard (Frontend/)
  Overview, Stations, Alerts, Investigations,
  Network Health, Judge Probe, Evaluation
```

One inference pipeline serves REST, the judge probe, and the replay stream.

## Requirements

- Backend: Python 3.14 with fastapi, uvicorn, pandas, numpy, scikit-learn,
  tensorflow (CPU), shap, joblib, pydantic, websockets, httpx, pytest.
- The generated ML/data artifacts expected under `Backend/` (see
  `Backend/src/api/dependencies.py` `REQUIRED_FILES`). They are git-ignored
  and must be produced by the project pipeline; the server fails fast with a
  clear message when they are absent.
- Frontend: Node.js (recent LTS) and npm.

## Clean checkout startup (Phase 21B)

```sh
git clone <remote> Skyguard_AI
cd Skyguard_AI
cd Backend
pip install -r requirements.txt
cd ../Frontend
npm install
```

Demo artifacts (`data/`, `models/` under `Backend/`) are git-ignored
frozen pipeline outputs. Reproduce them with the project pipeline on the
source machine, then verify against
`Backend/reports/phase21b_go1_artifact_manifest.json` (path, purpose,
version, sha256 per serving-required artifact). No download URL is
invented: artifacts travel with the demo machine, never fetched blindly.
Benchmark evaluation tables are NOT required to serve.

```sh
cd Backend
python -m src.api.run
```

## Backend setup

```sh
cd Backend
pip install -r requirements.txt
python -m src.api.run
```

Optional environment (see `Backend/.env.example`):

```sh
set SKYGUARD_HOST=127.0.0.1
set SKYGUARD_PORT=8000
set SKYGUARD_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
set SKYGUARD_DATA_ROOT=.
```

The server listens on `http://localhost:8000` by default. On startup it
validates every required artifact and refuses to serve when any are missing
(`SkyGuard startup validation failed: ...`).

## Frontend setup

```sh
cd Frontend
npm install
```

Copy `.env.example` to `.env` and point it at the backend:

```sh
VITE_API_BASE_URL=http://localhost:8000
```

## Starting backend

```sh
cd Backend
python -m src.api.run
```

Health check: `GET http://localhost:8000/health` (also `/api/v1/health`).
Demo readiness: `GET http://localhost:8000/api/v1/demo/readiness`.

## Starting frontend

Development:

```sh
cd Frontend
npm run dev
```

Open the printed localhost URL (default port 3000, covered by backend CORS).

Production build + preview:

```sh
cd Frontend
npm run build
npm run preview
```

## Judge demo flow

1. Open Overview — confirm **Demo Ready** in the replay bar.
2. Start Historical Replay (DEL-01, OOD, 10×) — watch streamed observations.
3. Open a streamed anomaly — inspect evidence, root cause, confidence.
4. Open Judge Probe — run a normal observation, then a spike-like one.
   For DEL-01 the probe also shows the spatial interpretation (base
   detector result + neighbor agreement → local-sensor vs possible-
   regional reading). Flags are never cleared by spatial agreement.
5. Open Evaluation — show held-out OOD, root-cause, and runtime evidence.

Nothing auto-starts; every result is computed by the backend pipeline.

## Live ingestion (Phase 23)

- Judge-safe path (no credentials): open the **Live** page → **Start
  controlled live demo** (`POST /api/v1/live/demo/start`). Shows
  `CONTROLLED LIVE` for scripted PATNA-TEST-01 traffic — never IMD data.
- Authorized IMD polling: `IMD_SOURCE_MODE=LIVE_IMD` (+ allowlist,
  poll interval, `IMD_CA_BUNDLE` for the emSign/CCA chain), then
  `POST /api/v1/live/start`. Status: `GET /api/v1/live/status`;
  stations, episodes, and observations under `/api/v1/live/*`.
- Live alerts persist in SQLite (`Backend/data/live/`, git-ignored)
  and are separate from historical replay alerts.

## Freeze (stuck-signal) detection

Benchmark FROZEN fault injections run 1-5 hours, shorter than the data-quality
6-hour candidate gate, so the frozen ensemble alone missed most frozen
episodes. A deterministic freeze confirmation (`Backend/src/detection/freeze.py`)
now joins every serving path (probe/replay ensemble, calibrated station
detectors, live inference): >= 6 consecutive identical readings observed
causally at the row itself, relative humidity at 0/100 excluded (real clean
data contains multi-hour saturated runs), with documented presentation
severity and an evidence-strength confidence margin. It never changes the
ensemble score itself; when a freeze is confirmed the root-cause class is
assigned by rule (`root_cause.basis = freeze_rule` or `freeze_rule_override`).

Reproduce the measured benchmark evaluation (frozen predictions + labels, no
inference re-run):

```sh
cd Backend
python -m src.detection.run_freeze_evaluation
```

Outputs `Backend/reports/detection/freeze_evaluation.{json,md}` (mirrored to
the root `reports/` tree). Measured: FROZEN event recall 5/30 -> 29/30
(Delhi generalisation, 0 added background flags) and 11/30 -> 30/30
(Jena generalisation, +102 background rows, 168 -> 181 per 10k).

Station detail pages also report a descriptive signal-health indicator over a
trailing 90-day window (confirmed flatline runs; explicitly not a failure
prediction or remaining-useful-life estimate).

## Testing

Backend (from `Backend/`):

```sh
python -m pytest tests/ -q
```

Expected: all tests pass except two known environment failures
(`test_raw_inventory_presence`, `test_deterministic_processed_output`),
which depend on the original author's machine paths and pandas-version
byte-identical reprocessing — unrelated to serving.

Frontend (from `Frontend/`):

```sh
npx eslint src/lib src/components src/routes src/hooks
npx tsc --noEmit
npm run build
```

## Known limitations

- Historical replay, not a physical live AWS connection.
- Benchmark faults are controlled/injected, not natural failures.
- Root-cause accuracy varies by fault type and degrades on OOD input.
- LSTM/SHAP computation can increase per-reading inference latency.
- Replay supports detector-covered stations (DEL-01, JENA-01).
- NOAA spatial data is contextual evidence, not ground truth.
- No Docker/cloud deployment is provided in this repository.
