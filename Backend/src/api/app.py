"""SkyGuard FastAPI application: versioned routes over frozen artifacts."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api import schemas as S
from src.api.dependencies import API_VERSION, DataStore
from src.api.services import health_service as HS
from src.api.services import evaluation_service as ES
from src.api.services import investigation_service as IV
from src.api.services import network_service as NS
from src.api.services import observation_service as OS
from src.api.services import probe_service as PS
from src.api.services import readiness_service as RS
from src.api.services import station_service as SS
from src.api.services import upload_analysis as UA
from src.api.services import upload_session as US

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
    try:
        STORE = DataStore.load(root)
    except RuntimeError as exc:
        # Startup precheck: one clean line naming the missing artifacts
        # (relative paths only, never machine-specific absolutes).
        logger.error("SkyGuard startup validation failed: %s", exc)
        raise
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
    allow_methods=["GET", "POST"],
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
    try:
        bundle = IV.build_investigation(store, alert)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail=f"No evidence row for '{alert_id}'") from None
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


@app.post("/api/v1/demo/probe", response_model=S.ProbeResponse)
def probe_observation(payload: S.ProbeRequest) -> dict:
    """Interactive inference: one judge-supplied observation, same pipeline."""
    store = get_store()
    try:
        return PS.run_probe(store, payload.station_id, payload.temperature,
                            payload.pressure, payload.humidity)
    except PS.ProbeError as exc:
        return JSONResponse(status_code=exc.status_code,
                            content={"detail": exc.detail, "code": exc.code})


@app.get("/api/v1/evaluation/summary", response_model=S.EvaluationSummary)
def evaluation_summary() -> dict:
    """Frozen benchmark + runtime evidence (read-only, never recomputed)."""
    store = get_store()
    try:
        return ES.load_evidence(store.root)
    except RuntimeError as exc:
        return JSONResponse(status_code=503,
                            content={"detail": str(exc), "code": "artifacts_unavailable"})


@app.get("/api/v1/demo/readiness", response_model=S.ReadinessResponse)
def demo_readiness() -> dict:
    """Lightweight judge-demo capability check (no ML inference)."""
    return RS.check(get_store())


def _upload_error(exc: US.UploadError):
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.detail, "code": exc.code})


@app.post("/api/v1/analyze/upload", response_model=S.UploadResponse)
async def analyze_upload(file: UploadFile = File(...)) -> dict:
    """Ingest a judge-supplied station CSV (parse + mapping proposal)."""
    get_store()
    try:
        content = await file.read()
        return US.create_session(file.filename or "upload.csv", content)
    except US.UploadError as exc:
        return _upload_error(exc)


@app.post("/api/v1/analyze/{session_id}/confirm", response_model=S.DQPreview)
def analyze_confirm(session_id: str, payload: S.ConfirmRequest) -> dict:
    """Confirm mapping/units and return the data-quality preview."""
    get_store()
    try:
        US.confirm_session(session_id, payload.mapping.model_dump(),
                           payload.units.model_dump(), payload.station_label)
        return UA.dq_preview(session_id)
    except US.UploadError as exc:
        return _upload_error(exc)


@app.post("/api/v1/analyze/{session_id}/run", response_model=S.AnalysisResult)
def analyze_run(session_id: str) -> dict:
    """Run uploaded-dataset analysis (statistical + DQ + multivariate)."""
    get_store()
    try:
        return UA.run_analysis(session_id)
    except US.UploadError as exc:
        return _upload_error(exc)


@app.get("/api/v1/analyze/{session_id}", response_model=S.AnalysisResult)
def analyze_result(session_id: str) -> dict:
    """Stored analysis result for navigation re-fetch (no recompute)."""
    get_store()
    try:
        return UA.get_result(session_id)
    except US.UploadError as exc:
        return _upload_error(exc)


@app.get("/api/v1/live/status")
def live_status() -> dict:
    """Live ingestion state (mode, source, fetch times, episodes)."""
    get_store()
    from src.api.services import live_service as LV

    manager = LV.get_manager()
    snap = manager.snapshot()
    if snap["state"] == "LIVE_UNAVAILABLE" and manager.status == "IDLE":
        return {"state": "LIVE_UNAVAILABLE", "mode": manager.config.mode,
                "detail": ("Live ingestion is idle. Start CONTROLLED_LIVE "
                           "for the scripted demo or configure LIVE_IMD."),
                "source": None, "stations": [], "last_attempt": None,
                "last_success": None, "last_error": "",
                "open_episodes": 0, "inference_latency": {}}
    return snap


@app.get("/api/v1/live/stations")
def live_stations() -> dict:
    """Per-station live state (history depth, latest observation, quality)."""
    get_store()
    from src.api.services import live_service as LV

    manager = LV.get_manager()
    stations = []
    for sid, hist in manager.histories.items():
        latest = hist.latest()
        stations.append({"station_id": sid, "history_rows": len(hist),
                         "warm_state": hist.warm_state(),
                         "latest_timestamp": latest.timestamp.isoformat()
                         if latest else None,
                         "latest": {"temperature_c": latest.temperature_c,
                                    "pressure_hpa": latest.pressure_hpa,
                                    "relative_humidity_pct":
                                        latest.relative_humidity_pct}
                         if latest else None})
    return {"mode": manager.config.mode, "stations": stations}


@app.get("/api/v1/live/alerts")
def live_alerts(station_id: str | None = Query(None),
                limit: int = Query(100, ge=1, le=1000)) -> dict:
    """Persisted live alert episodes (operational, never replay alerts)."""
    get_store()
    from src.api.services import live_service as LV

    return {"mode": LV.get_manager().config.mode,
            "episodes": LV.get_manager().store.episodes(station_id, limit)}


@app.get("/api/v1/live/observations/{station_id}")
def live_observations(station_id: str,
                      limit: int = Query(200, ge=1, le=1000)) -> dict:
    """Persisted live observations for one station (newest first)."""
    get_store()
    from src.api.services import live_service as LV

    return {"station_id": station_id, "mode": LV.get_manager().config.mode,
            "observations": LV.get_manager().store.observations(
                station_id, limit)}


@app.post("/api/v1/live/start")
async def live_start() -> dict:
    """Start live ingestion from server configuration (allowlist only)."""
    get_store()
    from src.api.services import live_service as LV
    from src.live import config as LC

    manager = LV.get_manager()
    if manager.config.mode == LC.CONTROLLED_LIVE:
        return await LV.start_controlled_demo()
    return await manager.start()


@app.post("/api/v1/live/stop")
async def live_stop() -> dict:
    """Stop the live ingestion loop gracefully."""
    get_store()
    from src.api.services import live_service as LV

    return await LV.get_manager().stop()


@app.post("/api/v1/live/demo/start")
async def live_demo_start() -> dict:
    """Start the CONTROLLED LIVE DEMO (scripted, never IMD data)."""
    get_store()
    from src.api.services import live_service as LV

    return await LV.start_controlled_demo()


@app.websocket("/api/v1/live")
async def live_replay(websocket: WebSocket) -> None:
    """Accelerated historical replay over WebSocket (no live sensors)."""
    from src.api.replay.engine import ReplaySession

    try:
        store = get_store()
    except HTTPException:
        await websocket.close(code=1011)
        return
    await websocket.accept()
    await ReplaySession(store, websocket).handle()
