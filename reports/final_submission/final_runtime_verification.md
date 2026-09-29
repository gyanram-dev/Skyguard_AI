# SkyGuard AI — Final Runtime Verification

Pass: final submission hardening + judge-probe regression fix.
Not production-ready. No model, threshold, ensemble, spatial policy, benchmark methodology or
data pipeline was changed.

## 0. Regression fixed in this pass — "No probeable stations"

**Symptom:** the Overview CTA "Test an Observation" led to *"No probeable stations — no
station currently has detector coverage for interactive inference"*, even though `DEL-01`
does have detector coverage.

**Root cause (two independent defects, both real):**

1. **The documented backend start command crashed.** `Backend/src/api/run.py` imported
   `dotenv` unconditionally, but `python-dotenv` (declared in `requirements.txt`) is **not
   installed in `Backend/.venv`**. Running the advertised command
   `Backend\.venv\Scripts\python.exe -m src.api.run` died at import with
   `ModuleNotFoundError: No module named 'dotenv'` — the server never started. Whatever
   answered the browser was therefore a *stale* backend process predating the
   `probe_available` field, so the flag was absent for every station.
   **Fix:** `.env` loading is now optional — a missing optional dependency logs one line and
   the server starts normally (`run.py::_load_env_file`).

2. **The frontend treated an absent field as "no coverage".** The Judge Probe filtered on
   `station.probe_available` and, when the field was missing entirely, rendered a claim
   ("no station currently has detector coverage") that the backend had never made.
   **Fix:** the page now distinguishes three cases:
   - backend **reports** the flag → filter by it (authoritative);
   - backend **does not report** the flag → fall back to the existing authoritative
     `/api/v1/demo/readiness` signal (`probe_available` + `default_station`) instead of
     claiming zero coverage, with an explanatory note;
   - backend **explicitly reports zero** probeable stations → only then the empty state
     "No stations currently have interactive detector coverage."
   Nothing is hardcoded: the fallback station comes from the backend's readiness response.

**Verified after the fix** in the exact user configuration (below): `DEL-01 · Delhi · 9.3°C`
is selectable and both scenarios run.

## 1. Reproduction environment (exactly as a fresh user)

| Item | Value |
| --- | --- |
| Backend command | `Backend\.venv\Scripts\python.exe -m src.api.run` |
| Backend URL | `http://127.0.0.1:8000` (uvicorn banner confirmed) |
| Frontend command | `npm run dev` → `http://localhost:3000/` |
| Frontend API base URL | `http://localhost:8000` — **default fallback**; there is no `Frontend/.env`, `.env.local`, `.env.development` or `.env.production`. `.env.example` documents `VITE_API_BASE_URL=http://localhost:8000` |
| Port mismatch check | Single backend (8000) and single frontend (3000); no duplicate/leftover processes. Browser origin `http://localhost:3000` matches the backend's default CORS allowlist |
| Browser page tested | `http://localhost:3000/judge-probe` |

## 2. Actual API responses observed at runtime

```
GET /api/v1/stations  (14 stations)
  DEL-01  status=healthy          data_available=true  scope=indian_operational  probe_available=true
  JAI-02  status=historical_only  data_available=true  scope=indian_operational  probe_available=false
  probe_available == true for: ['DEL-01']

GET /api/v1/stations/DEL-01
  station.probe_available = true
  station.status          = healthy

POST /api/v1/demo/probe  DEL-01 normal (9.300583 / 971.2725 / 100)
  200 → is_anomalous=false, score=0.727, confidence=1.0, availability=FULL_EVIDENCE,
        threshold=0.978, method=ens_median
        spatial_decision: BASE_NORMAL / NORMAL / influence=none
POST /api/v1/demo/probe  DEL-01 spike-like (temperature +25)
  200 → is_anomalous=true, score=1.000, confidence=1.0,
        root_cause=SPIKE (0.791), runner_up=CROSS
        spatial_decision: BASE_ANOMALOUS / LOCAL_SENSOR_ANOMALY / influence=contradicted
POST /api/v1/demo/probe  JAI-02
  422 → code=insufficient_context (station is context-only)

GET /api/v1/demo/readiness
  {"ready": true, "default_station": "DEL-01", "probe_available": true, ...}

GET /api/v1/alerts?limit=1000
  returned=1000  total=1201  limit=1000   (statuses in the page: 132 anomaly / 868 review)

GET /api/v1/network/summary
  stations_monitored=14  healthy=1  needs_review=0  anomaly=0  offline=0
  network_health_pct=100.0  detector_covered=1  context_only=13
  indian_operational_monitored=14  indian_operational_healthy=1
  observations_indexed=793872  live_capable_stations=5
```

**Judge Probe browser result (localhost:3000):** station selector shows
`DEL-01 · Delhi · 9.3°C`; normal run → `TRUSTED OBSERVATION / NORMAL`; spike-like run →
`ANOMALY DETECTED / SENSOR ANOMALY · Root cause SPIKE · 79% · score 1.000`, spatial
interpretation `LOCAL_SENSOR_ANOMALY`. No console errors.

## 3. Alert count — what "1000" actually was

| Question | Answer |
| --- | --- |
| Alert count source | `store.alerts`, built from consecutive flagged runs in the frozen DEL-01 ensemble outputs (`src/api/services/anomaly_service.py`) |
| Displayed before the fix | "1000 active / 1 resolved / 1001 total" |
| Was 1000 a real active count? | **No.** `GET /api/v1/alerts` caps at `limit` (default 100, max 1000). The frontend requested 1000, so the cap — not a total — was being shown, and it was mislabelled as "active" |
| Real stored total | **1201** (1055 `review` + 146 `anomaly`); the page shows the most recent 1000 |
| Extra row | the "1 resolved" row is a **persisted controlled-live episode**, not a historical alert |
| Duplicates / stale SQLite | none — no data was deleted or modified |
| Fix | `GET /api/v1/alerts` now also returns `returned`, `total`, `limit`. The Alerts page shows **"1000 shown of 1201 stored"** with a note that counts describe the loaded window, and the sidebar badge shows the stored total (1201). The hero CTA no longer carries a numeric badge, because a bare number next to "View Active Alerts" would imply a total the API cannot prove |

## 4. Health KPI calculation — why 14 appeared "healthy"

| Question | Answer |
| --- | --- |
| How computed | `src/api/services/network_service.py::summarize` over each station's state from `_station_state` |
| Why 14 were healthy | `_station_state` returned a hardcoded `status: "healthy"` for every NOAA/GHCNh station. Those 13 stations carry real historical observations but **no detector covers them**, so no health verdict exists for them |
| Was that misleading? | Yes — a missing capability was presented as a healthy verdict |
| Fix | Context-only stations now report `status: "historical_only"`; the four operational buckets (`healthy`/`needs_review`/`anomaly`/`offline`) are computed **only over detector-covered stations**, and `context_only`, `detector_covered` and `indian_operational_context_only` were added. `network_health_pct` is now over detector-covered stations only |
| New result | 14 monitored → **1 detector-covered (healthy) + 13 historical-only + 0 offline**; the invariant `healthy + needs_review + anomaly + offline + context_only == stations_monitored` holds and is asserted in `tests/test_api.py` |
| Frontend | New `historical` display status ("Historical only") across map pins, badges, stations list, network-health distribution and filters; KPIs now read *Stations Monitored / Detector-covered / Needs Review / Historical Only / Network Health* with explicit notes |
| Invented score? | No — no new health score was created; the existing detector status is simply scoped to the stations it actually covers |

## 5. Backend tests

Run with the user's interpreter (`.venv`):

```
Backend\.venv\Scripts\python.exe -m pytest -q
→ 1 failed, 368 passed, 24 warnings in 1056.16s (0:17:36)
```

Run with the fully-provisioned system interpreter:

```
Backend\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_probe.py
  tests/test_indian_network.py tests/test_live_ingestion.py tests/test_evidence_states.py
→ 75 passed
python -m pytest tests/test_noaa_acquisition.py → 11 passed
```

The single failure is **not** a code regression:

```
tests/test_noaa_acquisition.py::test_deterministic_processed_output
  ImportError: Unable to find a usable engine; tried using: 'pyarrow', 'fastparquet'.
```

`pyarrow` is **missing from `.venv`** but present in the system interpreter, where the whole
NOAA acquisition module passes (11/11). It is a `.venv` provisioning gap of the same class as
the `python-dotenv` issue above — and `pyarrow` is not declared in `requirements.txt` at all,
even though `src/noaa/process.py` reads parquet. The NOAA reprocessing path is not used by
the demo or serving path.

The suite also now asserts `healthy <= detector_covered` and that `detector_covered` equals
the number of stations reporting `probe_available`, so context-only stations can never be
counted as healthy again.

## 6. Frontend checks

| Check | Result |
| --- | --- |
| `npx tsc --noEmit` | Clean (exit 0) |
| `npm run build` (vite + nitro) | Success |
| `npx eslint` on all changed files | 0 errors (one pre-existing `react-refresh/only-export-components` warning in `common.tsx`) |
| `npx eslint .` whole repo | Still ~960 pre-existing `prettier/prettier` CRLF errors in untouched files on this Windows checkout |
| Map pin styling | Historical-only stations render a neutral grey pin (`--pin: var(--muted-foreground)`), not the green healthy fallback |

## 7. End-to-end browser flow (verified, no console errors)

```
Overview → Test an Observation → DEL-01 selectable
        → normal run → TRUSTED OBSERVATION / NORMAL
        → spike-like run → SENSOR ANOMALY / SPIKE (79%) / LOCAL_SENSOR_ANOMALY
Overview → View Active Alerts → /alerts (triage queue)
        → alert opens (/alerts/:id, triage review)
        → Open investigation → /investigations/:id (evidence workspace, 6 numbered evidence items)
```

Map pins: `DEL-01 → healthy`, all 13 others → `historical`, 14 pins total.

## 8. Known limitations (honest)

1. **Live IMD is not configured** (`LIVE_SOURCE_MODE=DISABLED`); controlled-live is scripted
   and labelled as such.
2. **Detector coverage is one station (`DEL-01`).** The other 13 Indian stations provide
   historical observations and are explicitly marked "Historical only" — they are never
   probed and never reported healthy.
3. **Freeze/drift per-station evidence is not exposed**; the station health panel shows those
   factors as *Unavailable*.
4. **Freeze/drift detection is weaker than spike/cross-variable**; the UI says
   "Detects" / "Monitors" and makes no quantitative claim.
5. **Confidence is evidence coverage**, not a calibrated probability.
6. **Optional corrected values** exist only in the CSV upload workflow; probe/live/replay say
   so.
7. **Predictive degradation forecasting** is not implemented and not claimed.
   An evidence-based maintenance-review flag (trailing-30d alert episodes →
   `MAINTENANCE_REVIEW_RECOMMENDED` / `ELEVATED_WATCH` / `NO_ACTION_INDICATED` /
   `NOT_APPLICABLE`) is exposed on station detail and shown under Sensor health.
   DEL-01 currently reports `MAINTENANCE_REVIEW_RECOMMENDED` (82 episodes / 30d).
8. **No edge/ESP32 deployment** exists and none is implied.
9. **`Backend/.venv` is not fully provisioned.** It is missing `python-dotenv` and
   `pyarrow` (both now declared in `requirements.txt`; `pyarrow==25.0.1` was added
   in this pass for the `src/noaa/process.py` parquet path). The server starts
   without `dotenv`. For a fully clean environment: `pip install -r requirements.txt`.
   Neither gap affects the demo or serving path.
10. **`GET /api/v1/alerts` is capped at 1000**; counts beyond that are surfaced as a page,
    not a total.
11. Repo-wide lint fails on pre-existing CRLF line endings across untouched files.

## 9. Final-pass measured runs (PS example, TestClient, 2026-09-29)

```
POST /api/v1/demo/probe  DEL-01  55.0°C / 1008.0 hPa / 72% RH
  → is_anomalous=true, score=0.99996
  → root_cause=SPIKE (confidence 0.82), runner_up=CROSS
  → spatial_decision=BASE_ANOMALOUS / LOCAL_SENSOR_ANOMALY / contradicted
  → recommended_action="Inspect the temperature sensor and its calibration; …"
POST /api/v1/demo/probe  DEL-01  9.3°C / 971.3 hPa / 100% RH
  → is_anomalous=false, score=0.729, contextual NORMAL
  → recommended_action="No action indicated; …"
  → seasonal reference: same-hour median 26.0°C over 1006 earlier days
     (deviation −16.7°C, descriptive reference only)
GET /api/v1/stations/DEL-01
  → maintenance=MAINTENANCE_REVIEW_RECOMMENDED (82 episodes / 30d)
```

The PS example (§32) runs through the real pipeline with no hardcoded
answer: 55°C + abnormal context → ANOMALY / SPIKE / confidence /
evidence / SHAP / calibration-review action, with neighbours contradicting
(LOCAL_SENSOR_ANOMALY).

## 10. Not claimed

This pass does not claim production readiness.
