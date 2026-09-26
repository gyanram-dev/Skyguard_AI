"""SkyGuard FastAPI application: versioned routes over frozen artifacts."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api import schemas as S
from src.api.dependencies import API_VERSION, DataStore
from src.api.services import health_service as HS
from src.api.services import investigation_service as IV
from src.api.services import network_service as NS
from src.api.services import observation_service as OS
from src.api.services import station_service as SS

logger = logging.getLogger("skyguard.api")

STORE: DataStore | None = None


def get_store() -> DataStore:
    """Request-time accessor; 503 when artifacts failed to load."""
    if STORE is None:
        raise HTTPException(status_code=503, detail="Backend datastore unavailable")
    return STORE


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load and validate every artifact once; fail fast with causes."""
    global STORE
    root = Path(os.environ.get("SKYGUARD_DATA_ROOT", ".")).resolve()
    STORE = DataStore.load(root)
    logger.info("SkyGuard API ready (data_mode=%s)", OS.DATA_MODE)
    yield
    STORE = None


app = FastAPI(title="SkyGuard API", version=API_VERSION, lifespan=lifespan)

ALLOWED_ORIGINS = [o.strip() for o in
                   os.environ.get("SKYGUARD_ALLOWED_ORIGINS",
                                  "http://localhost:3000,http://localhost:5173").split(",")
                   if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    """Lightweight structured access log (no sensitive content)."""
    started = time.perf_counter()
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        logger.exception("unhandled failure: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Unexpected backend failure",
                                                      "code": "internal_error"})
    duration_ms = round((time.perf_counter() - started) * 1000.0, 1)
    logger.info("%s %s -> %s (%sms)", request.method, request.url.path, status, duration_ms)
    return response


@app.get("/health", response_model=S.HealthResponse)
def health() -> dict:
    """Simple infrastructure check (unversioned)."""
    return HS.report(get_store())


@app.get("/api/v1/health", response_model=S.HealthResponse)
def health_v1() -> dict:
    """Versioned health check with per-model load status."""
    return HS.report(get_store())


def _station_state(store: DataStore, entry: dict) -> dict:
    """Status + snapshot for one mapping entry (no fabricated values)."""
    if not entry.get("backend_station_id"):
        return {"status": "offline", "data_available": False, "last_updated": None,
                "snapshot": None}
    backend_id = entry["backend_station_id"]
    if entry["source_dataset"] == "noaa_ghcnh":
        snap = SS.noaa_snapshot(store, backend_id)
        if snap is None:
            return {"status": "offline", "data_available": False, "last_updated": None,
                    "snapshot": None}
        return {"status": "healthy", "data_available": True,
                "last_updated": snap["timestamp"], "snapshot": snap}
    snap = SS.pipeline_snapshot(store, backend_id)
    return {"status": SS.pipeline_status(snap["ens"]), "data_available": True,
            "last_updated": snap["timestamp"], "snapshot": snap}


@app.get("/api/v1/stations", response_model=S.StationListResponse)
def list_stations() -> dict:
    """Station summaries with explicit historical-replay labeling."""
    store = get_store()
    stations = []
    for entry in store.mapping:
        state = _station_state(store, entry)
        snap = state["snapshot"]
        summary: dict = {"station_id": entry["frontend_station_id"], "city": entry["city"],
                         "latitude": entry.get("latitude"), "longitude": entry.get("longitude"),
                         "status": state["status"],
                         "data_available": state["data_available"],
                         "data_mode": OS.DATA_MODE, "last_updated": state["last_updated"]}
        if snap is not None and entry["source_dataset"] != "noaa_ghcnh":
            obs, ens = snap["obs"], snap["ens"]
            summary.update({"temperature": SS._num(obs["temperature_c"]),
                            "humidity": SS._num(obs["relative_humidity_pct"]),
                            "pressure": SS._num(obs["pressure_hpa"])})
            if ens is not None:
                summary.update({"anomaly_score": SS._num(ens["ens_median"]),
                                "confidence": SS.EVIDENCE_COMPLETENESS.get(
                                    str(ens["availability"]))})
        elif snap is not None:
            obs, spatial = snap["obs"], snap["spatial"]
            summary.update({"temperature": SS._num(obs["temperature_c"]),
                            "humidity": SS._num(obs["relative_humidity_pct"]),
                            "pressure": SS._num(obs["altimeter_setting_hpa"])})
            score, _ = SS.noaa_max_score(spatial)
            summary.update({"anomaly_score": score, "confidence": None})
        stations.append(summary)
    return {"data_mode": OS.DATA_MODE, "stations": stations}


@app.get("/api/v1/stations/{station_id}", response_model=S.StationDetailResponse)
def station_detail(station_id: str) -> dict:
    """Single-station snapshot: observations, quality, anomaly, diagnosis, context."""
    store = get_store()
    entry = SS.get_mapping(store, station_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown station '{station_id}'")
    state = _station_state(store, entry)
    if not state["data_available"]:
        raise HTTPException(status_code=404, detail=f"No backend data for '{station_id}'")
    info: dict = {"station_id": station_id, "city": entry["city"], "status": state["status"],
                  "data_mode": OS.DATA_MODE, "last_updated": state["last_updated"]}
    if entry.get("latitude") is not None:
        info["coordinates"] = {"latitude": entry["latitude"], "longitude": entry["longitude"]}
    snap = state["snapshot"]
    if entry["source_dataset"] == "noaa_ghcnh":
        obs, spatial = snap["obs"], snap["spatial"]
        score, _ = SS.noaa_max_score(spatial)
        neighbor_count = int(spatial["available_neighbor_count"]) if spatial is not None else 0
        context_level = str(spatial["temp_context"]) if spatial is not None else "UNAVAILABLE"
        return {"station": info,
                "observations": {"temperature_c": SS._num(obs["temperature_c"]),
                                 "relative_humidity_pct": SS._num(obs["relative_humidity_pct"]),
                                 "pressure_hpa": SS._num(obs["altimeter_setting_hpa"])},
                "data_quality": {"status": "PASS", "ml_eligible": True, "flags": []},
                "anomaly": {"detected": False, "score": score, "method": "spatial",
                            "confidence": None},
                "root_cause": {"class": None, "confidence": None},
                "spatial_context": {"available": spatial is not None,
                                    "neighbor_count": neighbor_count,
                                    "context_level": context_level}}
    obs, ens = snap["obs"], snap["ens"]
    quality = {"status": "UNKNOWN", "ml_eligible": False, "flags": []}
    anomaly = {"detected": False, "score": None, "method": "ensemble", "confidence": None}
    root_cause: dict = {"class": None, "confidence": None}
    if ens is not None:
        quality = {"status": str(ens["data_quality_status"]),
                   "ml_eligible": bool(int(ens["evaluation_eligible"])), "flags": []}
        anomaly = {"detected": bool(int(ens["ens_median_flag"])),
                   "score": SS._num(ens["ens_median"]), "method": "ensemble",
                   "confidence": SS.EVIDENCE_COMPLETENESS.get(str(ens["availability"]))}
        rc_row = snap["rc"]
        if rc_row is not None and str(rc_row.get("predicted_class", "")) not in ("", "None", "nan"):
            root_cause = {"class": str(rc_row["predicted_class"]),
                          "confidence": SS._num(rc_row.get("confidence"))}
    spatial = {"available": entry["backend_station_id"] == "delhi",
               "neighbor_count": 0, "context_level": "UNAVAILABLE"}
    return {"station": info,
            "observations": {"temperature_c": SS._num(obs["temperature_c"]),
                             "relative_humidity_pct": SS._num(obs["relative_humidity_pct"]),
                             "pressure_hpa": SS._num(obs["pressure_hpa"])},
            "data_quality": quality, "anomaly": anomaly, "root_cause": root_cause,
            "spatial_context": spatial}


@app.get("/api/v1/stations/{station_id}/history", response_model=S.HistoryResponse)
def station_history(station_id: str, variable: str = Query("temperature"),
                    hours: int = Query(24, ge=1, le=168)) -> dict:
    """Timestamp/value pairs for the trailing window (missingness preserved)."""
    store = get_store()
    if variable not in ("temperature", "humidity", "pressure"):
        raise HTTPException(status_code=422,
                            detail=f"Invalid variable '{variable}' (temperature|humidity|pressure)")
    entry = SS.get_mapping(store, station_id)
    if entry is None or not entry.get("backend_station_id"):
        raise HTTPException(status_code=404, detail=f"No backend data for '{station_id}'")
    points = SS.history_series(store, entry, variable, hours)
    return {"station_id": station_id, "variable": variable, "hours": hours,
            "data_mode": OS.DATA_MODE, "points": points}


@app.get("/api/v1/alerts", response_model=S.AlertListResponse)
def list_alerts(limit: int = Query(100, ge=1, le=1000)) -> dict:
    """Detected anomaly events, timestamp descending (frozen pipeline output)."""
    store = get_store()
    return {"data_mode": OS.DATA_MODE, "alerts": store.alerts[:limit]}


@app.get("/api/v1/alerts/{alert_id}", response_model=S.AlertDetailResponse)
def alert_detail(alert_id: str) -> dict:
    """Full investigation bundle for one alert."""
    store = get_store()
    alert = store.alert_index.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Unknown alert '{alert_id}'")
    bundle = IV.build_investigation(store, alert)
    return {"alert": {k: alert.get(k) for k in
                      ("alert_id", "station_id", "timestamp", "status", "event",
                       "anomaly_score", "root_cause", "root_cause_confidence", "summary")},
            "observations": bundle["observations"], "evidence": bundle["evidence"],
            "history": bundle["history"], "root_cause": bundle["root_cause"],
            "explanation": bundle["explanation"], "ensemble_method": "ens_median"}


@app.get("/api/v1/network/summary", response_model=S.NetworkSummary)
def network_summary() -> dict:
    """Network counts computed from backend station states."""
    store = get_store()
    states = []
    for entry in store.mapping:
        state = _station_state(store, entry)
        states.append({"status": state["status"], "last_updated": state["last_updated"]})
    return NS.summarize(store, states)
