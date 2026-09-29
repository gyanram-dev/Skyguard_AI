# SkyGuard AI — Judge Demo Script

Target: a judge who knows nothing about the project understands the problem, the data, the
decision and the explanation in ~90 seconds. All values below were observed in a live run
against the real backend (see `final_runtime_verification.md`).

## Before you start (once)

```bash
# Terminal 1 — backend (loads frozen artifacts + models; ~20 s)
cd Backend
python -m src.api.run                     # http://127.0.0.1:8000

# Terminal 2 — frontend
cd Frontend
npm run dev                               # http://localhost:3000
```

The frontend reads `VITE_API_BASE_URL` (default `http://localhost:8000`). The backend's
CORS default allows `localhost:3000` and `localhost:5173`; add your port to
`SKYGUARD_ALLOWED_ORIGINS` if you serve the UI elsewhere.

Nothing in the demo needs IMD credentials. Live IMD is intentionally **not configured** and
the product says so.

---

## STEP 1 — Open the Overview

Judge immediately sees, above the fold:

- **SKYGUARD AI — AI-Powered AWS Anomaly Detection**
- "Detect faulty weather sensors without mistaking genuine extreme weather for sensor
  failure."
- "Context-aware quality control for Temperature, Pressure and Relative Humidity
  observations."
- **Operating source:** `LIVE UNAVAILABLE` with the honest reason
  (`LIVE_SOURCE_MODE=DISABLED`, no IMD endpoint).
- The **India station network** strip: **14 Indian stations · 793,872 observations indexed ·
  5 live-capable · 0 anomalies**.
- The Soft-3D India map with the real station pins.

Say: *"SkyGuard answers one question — can this observation be trusted?"*

## STEP 2 — Click "Test an Observation"

Primary CTA in the hero. Lands on **Test an Observation**. The station selector contains
only stations with detector coverage (`DEL-01`), with a note that 13 other stations carry
historically-sourced contextual observations only. No fake dropdown options, no dead ends.

## STEP 3 — Run a normal observation

Press **5. Run SkyGuard** with the prefilled latest reading (9.3 °C / 971.3 hPa / 100 %).

Expected result:

- **TRUSTED OBSERVATION → NORMAL**
- Anomaly score **0.727**, Confidence **100 %**, Threshold **0.978**, method `ens_median`,
  Full evidence
- **WHY?** — ✓ Temporal behaviour consistent · ✓ Multivariate relationship consistent ·
  ✓ Spatial context consistent
- Temporal / Multivariate / Spatial / Model evidence sections with real component numbers.

## STEP 4 — Run the spike scenario

Click **Spike-like** (badged **CONTROLLED**), then **Run SkyGuard**.

Expected result:

- **ANOMALY DETECTED → SENSOR ANOMALY**
- **Root cause: SPIKE · 79 % confidence**
- Anomaly score **1.000**, Confidence 100 %
- **SPATIAL EVIDENCE → Interpretation: `LOCAL_SENSOR_ANOMALY`**
  ("Target disagrees with nearby stations: local sensor anomaly is the supported reading.")
- Model evidence: Isolation Forest and LSTM raw + calibrated values.

Say: *"A sudden +25 °C change is flagged, and the spatial layer says it is one bad sensor,
not regional weather."*

## STEP 5 — Open the investigation

Use the **Open alerts queue** / **Open investigations** links, then open an alert with a
root cause (for example the DEL-01 SPIKE alert at 16:10). The Investigation shows:

- Header: **DEL-01 · SPIKE · Anomaly**, score 1.000, RC confidence 95 %, source
  `HISTORICAL_ALERT`
- **What was observed?** (T / RH / P, DQ `PASS`, evaluation eligible)
- **Temporal evidence — temperature, 24 h** chart (missing points stay gaps)
- **Why this needs review**: numbered statistical / Isolation Forest / LSTM / ensemble /
  multivariate / NOAA-spatial evidence items
- **Root cause & confidence**, SHAP contributions (when present), provenance, operator
  recommendation.

Say: *"This is why the model flagged it — not a black box."*

## STEP 6 — Show the network / spatial context

Back on the Overview, the **Spatial context** card sits beside the map for the selected
station, and the **Real Weather or Sensor Fault?** section states the two outcomes:
`POSSIBLE REGIONAL EVENT` (neighbours agree) vs `LOCAL SENSOR ANOMALY` (only the target
deviates). When spatial evidence is missing it reads **SPATIAL CONTEXT UNAVAILABLE** —
never a green tick.

## STEP 7 — Open Alerts (triage)

Alerts is a compact operational queue: **"What needs attention?"** — *N* active, *N*
resolved, *N* total. Each row shows station, sensor, source badge (HISTORICAL / REPLAY /
CONTROLLED LIVE), event, root cause, anomaly score, confidence, duration, detected time,
state and status. Filters: **All · Active · Resolved · Historical · Replay · Live · Root
cause**.

Say: *"Alerts tells me what to look at first — nothing more."*

## STEP 8 — Show Investigation (analysis)

Investigations is visibly different: **"Why did SkyGuard decide this?"** — an evidence
workspace entry point listing the analysis sections (observation/decision, root cause,
sensor history, statistical/IF/LSTM evidence, multivariate, spatial, SHAP, DQ & provenance,
episode timeline, operator recommendation).

Say: *"Alerts is triage; Investigations is analysis."*

## STEP 9 — Start the replay

On the Overview, section **Real-time / replay visibility** (badged with the live source
state), press **Start** (10×, DEL-01, OOD split).

Observed: status → `Replay running`; the observation counter and Normal counter increase as
streamed observations are scored; any anomalies are listed under **Current replay
anomalies** with a **Review →** action into the replay investigation.

Say: *"The same pipeline runs as a stream — this is the real-time path without live
credentials."*

## STEP 10 — Stop the replay

Press **Stop**. Observed: status returns to `Replay idle`, the Start button reappears and
the panel returns to a clean operational state. No orphaned sessions.

---

## Optional additions if time allows

- **Network Health** — station composition, per-station status table.
- **Station detail** (e.g. click a pin → station) — identity, source, scope, observations,
  data quality, "Can I trust this station?" health factors and recent alerts.
- **Live** — shows `OFFLINE / NOT_CONFIGURED`, the disabled provider button and the
  **Start controlled live demo** action (labelled as scripted, not IMD).
- **Evaluation** — frozen benchmark and runtime evidence, read-only.
- **Analyze Data** — upload a CSV; this is the only place an optional
  operator-approved correction is available.

## Things not to claim

- Live IMD connectivity (not configured here).
- Predictive maintenance / degradation forecasting (not implemented).
- Edge/ESP32 deployment of the ensemble (not implemented).
- Automatic self-healing corrections on live data.
