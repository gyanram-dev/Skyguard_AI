# SkyGuard AI — Frontend ↔ Backend Integration Status

Backend MVP (station detector, registry, unified result, replay, alert
persistence, WebSocket, API) is unchanged by this task; this document records
what the existing frontend now consumes, and what remains.

## 1. Connected contracts (no new client abstractions)

One API client already existed (`Frontend/src/lib/api.ts`, `lib/live.ts`).
Everything below reuses it.

| UI surface            | Endpoint                                   | Verified                          |
| --------------------- | ------------------------------------------ | --------------------------------- |
| Overview metrics      | `GET /api/v1/network/summary`               | 14 stations, 793,872 observations, 11/14 detector-covered, 5 live-capable |
| Overview + map        | `GET /api/v1/stations`                      | 14 stations, 10 with `capability.detector` |
| Station detail        | `GET /api/v1/stations/{station_id}`         | MUM-03: `PARTIAL`, detector `Statistical Baseline`, cadence `30 min`, `altimeter_qnh_hpa`, RH provenance |
| Alerts triage         | `GET /api/v1/alerts`                        | 1201 stored (frozen operational feed) |
| Alert detail          | `GET /api/v1/alerts/{alert_id}`             | detail bundle 200                  |
| Replay stream         | `WS /api/v1/live`                           | see §3                             |

`GET /api/v1/live/alerts` is the operational *live* feed (empty while live
ingestion is `DISABLED`); the Live page reports that honestly instead of a
fake LIVE state.

## 2. Replay addressing (real station, not Delhi-only)

`ReplayControls` used to hardcode `DEL-01`. The replay station list is now
built from the backend response: every station with `probe_available` **or**
`capability.detector.detector_available` (11 stations: Delhi + 10 calibrated).
A calibrated station shows a fixed `HISTORICAL` split because the backend
replays that station's own real history; the ensemble stations keep ID/OOD.

## 3. Two real detector payload shapes, rendered honestly

`lib/liveView.ts` is the single place that knows the difference:

* `ensemble` — Delhi's frozen statistical + Isolation Forest + LSTM evidence
  (component fields, threshold).
* `station-statistical` — calibrated station verdict (severity, confidence,
  `confidence_basis`, primary reason, contributing factors, spatial context).

Ensemble-only fields are optional in the types, so a calibrated replay never
renders an invented component, threshold or confidence. Severity/confidence/
reason/factors are shown only when the backend sent them; spatial context shows
`UNAVAILABLE` → "Spatial context unavailable for this station." and never
"nearby stations normal".

## 4. WebSocket behaviour

Every server message carries `type` (existing contract) and `event_type`
(`CONNECTION` / `REPLAY_STATE` / `OBSERVATION` / `ANOMALY_DETECTED` /
`REPLAY_COMPLETE` / `ERROR`). Client fixes made during integration:

* `OBSERVATION` advances the running totals (`processed`), so the control bar
  reports progress instead of a permanent "waiting for first observation".
* `ANOMALY_DETECTED` counts distinct `alert_id`s into the anomaly total.
* `REPLAY_COMPLETE` sets the session status to `completed`, so the controls
  leave the busy state and the card reports completion.

## 5. Backend corrections required by the integration

* `ReplaySession` now resolves calibrated stations (registry-backed) instead of
  rejecting anything but Delhi, and defaults a station-detector session to a
  bounded window of real observations (`STATISTICAL_REPLAY_LIMIT = 60`): a
  station owns tens of thousands of 30-minute observations, and the protocol
  tops out at 3600× (0.5 s/observation), so an unbounded stream could never
  finish in a sitting. Callers may still pass an explicit `limit`.
* Station `capability_notes` no longer claims "no detector models cover it" for
  a station that has a calibrated detector; the purely contextual stations keep
  that note.
* The interactive probe error now distinguishes "calibrated detector runs
  during historical replay" from "no detector models cover it".
* Network summary gained explicit aliases (`historical_only`, `full_tpr`,
  `partial`, `live_capable`) alongside the existing measured counts.

## 6. Verified end-to-end (Mumbai, MUM-03)

Browser: Overview → replay station `MUM-03` → speed 900× → Start.

```
REPLAY_STATE      preparing → running
OBSERVATION       60 real GHCNh observations (2022-01-02 …, 30-minute cadence)
ANOMALY_DETECTED  29 (severity Low, confidence 35–52%, SPIKE/CROSS reasons)
REPLAY_COMPLETE   processed 60, anomalies 29, alerts_recorded 29
```

Each alert showed station, timestamp, severity, score, confidence and the
backend's primary reason, e.g.
`SPIKE: abrupt 8.5 robust-deviation jump within 2h; max|z|=2.20`.
The replay workspace rendered detector verdict, contributing factors,
data-quality evidence and `Spatial context unavailable — no neighbour values
invented.` A reload shows "This replay investigation is no longer available in
the current replay session." — no fabricated evidence.

## 7. Remaining blockers

1. `network/summary.detector_covered` keeps its original meaning (stations
   whose verdict is available without a replay = 1). It is a real measured
   count, but alongside `partial = 10` it understates coverage. The UI computes
   detector coverage as `full_tpr + partial`; a dedicated, unambiguous field
   would be better than deriving it in the browser.
2. Persisted replay alerts (SQLite under `data/replay/`, 67 unique MUM-03
   records; re-running the same window updates rather than duplicates) have no
   read endpoint. They are durable and inspectable in-process, but after a page
   reload the UI cannot list or re-open them.
3. Mumbai and Hyderabad have no compatible neighbour within the audited 600 km
   radius, so their spatial context is honestly `UNAVAILABLE` by design.
