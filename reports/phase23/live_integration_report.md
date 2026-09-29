# Phase 23 — Live observation ingestion report

Starting commit: `b4c027e`. Go 1 and Go 2 are intact (no logic
reopened; one additive optional schema field, additive spatial keys).

## 1. Architecture

```
IMD WIS2 / IMD ARG / CONTROLLED script
    -> ObservationSource.fetch_new (transport + parse + units only)
    -> CanonicalObservation (missing=None, basis-tagged pressure)
    -> LiveManager poll loop (single task, worker-thread fetch)
    -> SQLite dedupe (obs identity) -> StationHistory (causal deque)
    -> shared DQ (prepare_split) -> shared statistical baseline
    -> shared Go-2 spatial decide_context -> heuristic pattern
    -> EpisodeTracker (open/extend/resolve) -> SQLite episodes
    -> /api/v1/live/* + Live dashboard page
```

CSV, replay, probe and live converge on the same frozen modules
(`prepare_split`, `build_statistical_baseline`, `decide_context`,
pattern estimator). No second detector exists: Delhi/Jena IF/LSTM/RC
artifacts are not applied to unvalidated live stations (reported
unavailable, as for uploads).

## 2. Source adapter

`Backend/src/live/sources.py::ObservationSource` (fetch/describe).
`IMDWIS2Source` reuses the audited client + normalizer (bounded pages,
high-water-mark dedupe, per-station capability gate). `IMDArgSource`
is a configuration contract (env endpoint, TLS always on, disabled
until configured). `ControlledLiveSource` releases scripted rows
causally, labeled CONTROLLED everywhere.

## 3. IMD capability mapping (Phase 21A audit, authoritative)

PATNA/DELHI/KOLKATA: temperature only. BENGALURU/PUNE: temperature +
station pressure. Humidity: unavailable everywhere (dewpoint never
converted). MSL pressure never substitutes. Cadence ~3-hourly SYNOP.

## 4. Live state machine

IDLE -> RUNNING (start) -> STOPPED (graceful) / ERROR (recorded,
loop survives). Per-station rows: VALID/MISSING/INVALID/OUT_OF_ORDER/
DUPLICATE; buffer depth: WARMING_UP (<12) / INSUFFICIENT_EVIDENCE
(<12 LSTM rows) / VALID. Silence past cadence x 3 -> DATA_SOURCE_STALE
quality event (never an anomaly). Source fetch: RUNNING/ERROR with
last attempt/success/error (no secrets).

## 5. Persistence

SQLite WAL (`data/live/skyguard_live.sqlite`, git-ignored):
observations (PK obs_id), quality_events, alert_episodes
(started/last_seen/count/status/resolved/score/evidence JSON),
alert_observations, source_status. Schema contains no
reference-outcome columns (asserted in tests). Open episodes reload
on restart (proven in demo + test_22).

## 6. Causal history

Per-station deque (default 500); inserts keep chronological order;
duplicates ack without inference; arrivals older than newest-3 are
OUT_OF_ORDER and never rewrite issued decisions. Only rows present at
decision time are scored. LSTM lookback never synthesized.

## 7. DQ behavior

Frozen `prepare_split` rules on the causal frame; missing preserved;
warm-up verdicts instead of NORMAL; INSUFFICIENT_EVIDENCE when no
statistical evidence is measurable (missing score is never normal).

## 8. Alert behavior

Episodes keyed station+family, continuation window 1h, resolve after
2 normals. Records: alert_id (`live-` hash), observation/detection
timestamps, decision, score, evidence, spatial interpretation, pattern,
source, DQ state. Evidence terminology follows Go 1 (no calibrated
"confidence"). Replay alerts stay ephemeral and separate.

## 9. Controlled live test (PATNA-TEST-01, 5-min cadence)

`reports/phase23/live_demo_run.json` (fresh run 2026-09-29): 34
observations ingested; spike z=112.38 opened episode
`ANOMALY_WITHOUT_SPATIAL_CONFIRMATION` (no live neighbors — honest),
RESOLVED after 2 recovery rows; duplicate re-ingest added 0 episodes;
STALE-STATION silence flagged; restart restored open state.
Warm-up shown honestly (11 WARMING_UP rows before scoring).

## 10. Real IMD test

BLOCKED: `get_stations(limit=1)` from this environment fails
(`connection_failed`, unreachable in ~0.5s). Adapter implemented,
capabilities explicit, access pending network/authorization. CONTROLLED
LIVE demonstrated instead; nothing synthesized as IMD.

## 11. Performance (demo, 35 scored rows)

Inference (observation-to-decision, includes DQ+statistical+spatial):
p50 54 ms, p95 87 ms, max 89 ms. Fetch: N/A (controlled feed, no
network). Memory bounded (deque cap 500, latency ring 2000, single
task, no per-station threads). Real-time claims require deployment
measurement; not claimed here.

## 12. Limitations

No live neighbors yet (single-station feeds -> spatial UNAVAILABLE by
rule); ML detectors cover Delhi/Jena only; 3-hourly SYNOP cadence
limits timeliness; SQLite single-node; IP whitelisting may apply to
ARG.

## 13. Exact configuration (env, all optional)

IMD_SOURCE_MODE (DISABLED default), IMD_API_BASE_URL, IMD_ARG_BASE_URL,
IMD_ARG_API_KEY (presence only), IMD_TIMEOUT_SECONDS=30,
IMD_POLL_INTERVAL_SECONDS=60, IMD_MAX_RETRIES=5,
IMD_RETRY_BASE_SECONDS=2, IMD_STATION_ALLOWLIST, IMD_EXPECTED_CADENCE_
MIN=180, IMD_STALE_MULTIPLES=3, IMD_HISTORY_MAXLEN=500,
IMD_DB_PATH, IMD_CA_BUNDLE (TLS chain).

## 14. How to run controlled live

`POST /api/v1/live/demo/start` (or Demo button on the Live page);
watch CONTROLLED LIVE DEMO on `/live`. Backend-only equivalent:
`python -m src.live.demo` from `Backend/`.

## 15. How to enable authorized IMD

Set `IMD_SOURCE_MODE=LIVE_IMD`, allowlist WIGOS stations,
`IMD_POLL_INTERVAL_SECONDS`, provide `IMD_CA_BUNDLE` for the
emSign/CCA chain; `POST /api/v1/live/start`. For ARG additionally
`IMD_ARG_BASE_URL` (+ key if required) and any IP whitelisting.
