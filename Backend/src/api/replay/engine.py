"""Replay engine: benchmark rows -> shared scoring -> WebSocket events.

Orchestration only: every streamed value is produced by the shared
single-row core (src.api.services.scoring), the same implementation the
judge probe uses. No model code, no thresholds, no synthetic rows here.

Backpressure: each row is scored (in a worker thread, event loop stays
responsive), then the loop waits out the requested interval. When
inference outlasts the interval the next row follows immediately and the
reported effective speed reflects what was actually achieved.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import math
import time
from pathlib import Path

import pandas as pd
from fastapi import WebSocket, WebSocketDisconnect

from src.api.replay import alerts as RA
from src.api.replay import protocol as P
from src.api.replay import source as SRC
from src.api.services import scoring as SC
from src.detection.station_statistical import load_detector
from src.root_cause import confidence as CF

logger = logging.getLogger("skyguard.replay")

STATUS_IDLE = "idle"
STATUS_PREPARING = "preparing"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_STOPPED = "stopped"
STATUS_COMPLETED = "completed"

# Replay is never live: every event carries this explicit label.
SOURCE_MODE = "HISTORICAL_REPLAY"

# Calibrated station detectors replay a station's ENTIRE real history (tens of
# thousands of 30-minute observations). No offered replay speed could stream
# that in a sitting (the protocol tops out at 3600x, i.e. 0.5 s per
# observation), so a station-detector session defaults to a bounded window of
# real observations. Callers can still request an explicit `limit`.
STATISTICAL_REPLAY_LIMIT = 60

_NEIGHBOR_CACHE: dict[tuple[str, str], list[str]] = {}


def scored_temp(sensor, pos: int) -> float | None:
    """Row temperature for spatial context (None when missing)."""
    try:
        value = float(sensor["temperature_c"].iloc[pos])
    except (TypeError, ValueError, IndexError):
        return None
    return None if math.isnan(value) else value


def graph_neighbors(root: str | Path, backend_id: str) -> list[str]:
    """Audited selected neighbors for a station (<=600 km, up to 3).

    Reads the frozen neighbor graph written by `src.spatial.run`. Stations
    without neighbors inside the configured radius get an empty list: their
    spatial evidence is then honestly UNAVAILABLE instead of comparing
    against stations hundreds of kilometres away.
    """
    key = (str(Path(root).resolve()), backend_id)
    if key in _NEIGHBOR_CACHE:
        return _NEIGHBOR_CACHE[key]
    selected: list[str] = []
    path = Path(root) / "data" / "noaa" / "metadata" / "neighbor_graph.csv"
    try:
        if path.is_file():
            frame = pd.read_csv(path)
            mask = ((frame["target_station"].astype(str) == backend_id)
                    & (frame["selected"].astype(str).str.lower() == "true"))
            selected = sorted(frame.loc[mask, "neighbor_station"].astype(str))
    except Exception as exc:  # noqa: BLE001 - empty graph is honest
        logger.warning("neighbor graph unavailable: %s", exc)
    _NEIGHBOR_CACHE[key] = selected
    return selected


class ReplaySession:
    """One WebSocket connection's replay lifecycle."""

    def __init__(self, store, websocket: WebSocket) -> None:
        self._store = store
        self._root = getattr(store, "root", ".") or "."
        self._ws = websocket
        self._status = STATUS_IDLE
        self._task: asyncio.Task | None = None
        self._stop = False
        self._paused = False
        self._resume = asyncio.Event()
        self._speed = 10
        self._station_id: str | None = None
        self._split = SRC.DEFAULT_SPLIT
        self._limit: int | None = None
        self._ds = ""
        self._city = ""
        self._seq = 0
        self._processed = 0
        self._anomalies = 0
        self._alerts_recorded = 0
        self._cadence_min = 0.0
        self._ema_elapsed: float | None = None
        self._started_at = 0.0

    async def handle(self) -> None:
        """Command loop; owns cleanup on disconnect."""
        await self._ws.send_json(P.connection_event())
        try:
            while True:
                try:
                    raw = await self._ws.receive_json()
                except WebSocketDisconnect:
                    break
                except Exception:  # noqa: BLE001 - malformed frame, stay open
                    try:
                        await self._ws.send_json(P.error_event(
                            P.INVALID_COMMAND, "Message must be a JSON object."))
                    except Exception:  # noqa: BLE001 - socket may be gone
                        break
                    continue
                try:
                    action, params = P.parse_client_message(raw)
                except P.ProtocolError as exc:
                    await self._ws.send_json(P.error_event(exc.code, exc.detail))
                    continue
                await self._dispatch(action, params)
        finally:
            await self._teardown()

    async def _dispatch(self, action: str, params: dict) -> None:
        if action == "start":
            await self._cmd_start(params)
        elif action == "pause":
            await self._cmd_pause()
        elif action == "resume":
            await self._cmd_resume()
        elif action == "stop":
            await self._cmd_stop()
        elif action == "speed":
            await self._cmd_speed(int(params["value"]))

    def _busy(self) -> bool:
        return self._status in (STATUS_PREPARING, STATUS_RUNNING, STATUS_PAUSED)

    async def _cmd_start(self, params: dict) -> None:
        if self._busy():
            await self._ws.send_json(P.error_event(
                P.ALREADY_RUNNING, "A replay is already active; stop it first."))
            return
        station_id = params["station_id"]
        entry = next((m for m in self._store.mapping
                      if m["frontend_station_id"] == station_id), None)
        if entry is None or not entry.get("backend_station_id"):
            await self._ws.send_json(P.error_event(
                P.UNKNOWN_STATION,
                f"Station '{station_id}' is not available for replay."))
            return
        backend_id = entry["backend_station_id"]
        statistical = load_detector(self._root, backend_id)
        if backend_id != "delhi" and statistical is None:
            await self._ws.send_json(P.error_event(
                P.UNKNOWN_STATION,
                f"Station '{station_id}' is not available for replay."))
            return
        self._station_id = station_id
        self._ds = backend_id
        self._city = entry.get("city", "")
        # A station-specific statistical replay streams the station's real
        # history, so it reports HISTORICAL rather than a benchmark split.
        self._split = ("HISTORICAL" if statistical is not None
                       else params["split"])
        self._speed = params["speed"]
        limit = params["limit"]
        if statistical is not None and limit is None:
            limit = STATISTICAL_REPLAY_LIMIT
        self._limit = limit
        self._seq = 0
        self._processed = 0
        self._anomalies = 0
        self._alerts_recorded = 0
        self._cadence_min = (statistical.cadence_min if statistical is not None
                             else float(SRC.cadence_minutes(backend_id)))
        self._ema_elapsed = None
        self._stop = False
        self._paused = False
        self._resume.set()
        self._status = STATUS_PREPARING
        await self._ws.send_json(P.replay_state_event(
            STATUS_PREPARING, station_id, self._split, self._speed))
        if statistical is None:
            self._task = asyncio.create_task(self._replay())
        else:
            self._task = asyncio.create_task(self._replay_statistical(statistical))

    async def _cmd_pause(self) -> None:
        if self._status != STATUS_RUNNING:
            await self._ws.send_json(P.error_event(
                P.NOT_RUNNING, "Nothing is running to pause."))
            return
        self._paused = True
        self._resume.clear()
        self._status = STATUS_PAUSED
        await self._ws.send_json(self._state_event())

    async def _cmd_resume(self) -> None:
        if self._status != STATUS_PAUSED:
            await self._ws.send_json(P.error_event(
                P.NOT_RUNNING, "Nothing is paused to resume."))
            return
        self._paused = False
        self._resume.set()
        self._status = STATUS_RUNNING
        await self._ws.send_json(self._state_event())

    async def _cmd_stop(self) -> None:
        if not self._busy():
            await self._ws.send_json(P.error_event(
                P.NOT_RUNNING, "Nothing is running to stop."))
            return
        self._stop = True
        self._paused = False
        self._resume.set()

    async def _cmd_speed(self, value: int) -> None:
        self._speed = value
        if self._busy():
            await self._ws.send_json(self._state_event())

    def _state_event(self) -> dict:
        return P.replay_state_event(
            self._status, self._station_id, self._split, self._speed,
            sequence=self._seq, processed=self._processed,
            anomalies=self._anomalies,
            effective_speed=self._effective_speed())

    def _effective_speed(self) -> float | None:
        if not self._ema_elapsed or self._ema_elapsed <= 0:
            return None
        if not self._cadence_min:
            return None
        return round(self._cadence_min * 60.0 / self._ema_elapsed, 2)

    async def _replay(self) -> None:
        started = time.perf_counter()
        frames: dict | None = None
        try:
            source = await asyncio.to_thread(
                SRC.load_source, self._store, self._ds, self._split)
            sensor = source[["timestamp", "temperature_c", "pressure_hpa",
                             "relative_humidity_pct"]]
            if self._limit is not None:
                sensor = sensor.head(self._limit).reset_index(drop=True)
            frames = await asyncio.to_thread(SC.build_frames, self._store,
                                             self._ds, sensor)
            if self._stop:
                return
            self._status = STATUS_RUNNING
            self._started_at = time.perf_counter()
            await self._ws.send_json(self._state_event())
            cadence_s = self._cadence_min * 60.0
            stamps = sensor["timestamp"].astype(str).tolist()
            for pos in range(len(sensor)):
                if self._stop:
                    return
                while self._paused and not self._stop:
                    await self._resume.wait()
                if self._stop:
                    return
                tick = time.perf_counter()
                scored = await asyncio.to_thread(
                    SC.score_position, frames, self._ds, pos,
                    spatial_ts=stamps[pos],
                    spatial_temp=scored_temp(sensor, pos))
                elapsed = time.perf_counter() - tick
                self._ema_elapsed = elapsed if self._ema_elapsed is None else (
                    0.9 * self._ema_elapsed + 0.1 * elapsed)
                self._seq += 1
                self._processed += 1
                reading = self._reading_event(stamps[pos], scored)
                await self._ws.send_json(reading)
                if scored["verdict"]["is_anomalous"]:
                    self._anomalies += 1
                    await self._ws.send_json(self._alert_event(stamps[pos], scored))
                interval = cadence_s / max(1, self._speed)
                await self._wait(max(0.0, interval - elapsed))
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._status = STATUS_COMPLETED
            await self._ws.send_json(P.complete_event(
                self._station_id or "", self._split, self._processed,
                self._anomalies, duration_ms,
                effective_speed=self._effective_speed()))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - client gets a code, never a trace
            logger.exception("Replay failure: %s", exc)
            try:
                await self._ws.send_json(P.error_event(
                    P.INTERNAL_ERROR, "Replay failed unexpectedly."))
            except Exception:  # noqa: BLE001 - socket may be gone
                pass
            self._status = STATUS_IDLE
        finally:
            if self._stop and self._status != STATUS_COMPLETED:
                self._status = STATUS_STOPPED
                try:
                    await self._ws.send_json(self._state_event())
                except Exception:  # noqa: BLE001 - socket may be gone
                    pass
            frames = None
            gc.collect()

    async def _replay_statistical(self, detector) -> None:
        """Replay real GHCNh history through the calibrated detector.

        Same orchestration as the ensemble path (worker-thread scoring,
        pause/stop/speed, reading + alert events); only the scorer differs.
        """
        started = time.perf_counter()
        try:
            sensor = await asyncio.to_thread(
                SRC.load_noaa_source, self._store, self._ds)
            if self._limit is not None:
                sensor = sensor.head(self._limit).reset_index(drop=True)
            neighbors = await asyncio.to_thread(
                self._neighbor_values, sensor)
            results = await asyncio.to_thread(
                detector.score_frame, sensor, neighbors)
            if self._stop:
                return
            self._status = STATUS_RUNNING
            await self._ws.send_json(self._state_event())
            cadence_s = self._cadence_min * 60.0
            for pos, result in enumerate(results):
                if self._stop:
                    return
                while self._paused and not self._stop:
                    await self._resume.wait()
                if self._stop:
                    return
                tick = time.perf_counter()
                self._seq += 1
                self._processed += 1
                await self._ws.send_json(
                    self._statistical_reading_event(result))
                if result["anomaly"]:
                    self._anomalies += 1
                    self._persist_alert(result)
                    await self._ws.send_json(
                        self._statistical_alert_event(result))
                elapsed = time.perf_counter() - tick
                self._ema_elapsed = elapsed if self._ema_elapsed is None else (
                    0.9 * self._ema_elapsed + 0.1 * elapsed)
                interval = cadence_s / max(1, self._speed)
                await self._wait(max(0.0, interval - elapsed))
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._status = STATUS_COMPLETED
            await self._ws.send_json(P.complete_event(
                self._station_id or "", self._split, self._processed,
                self._anomalies, duration_ms,
                effective_speed=self._effective_speed(),
                alerts_recorded=self._alerts_recorded))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - client gets a code, never a trace
            logger.exception("Replay failure: %s", exc)
            try:
                await self._ws.send_json(P.error_event(
                    P.INTERNAL_ERROR, "Replay failed unexpectedly."))
            except Exception:  # noqa: BLE001 - socket may be gone
                pass
            self._status = STATUS_IDLE
        finally:
            if self._stop and self._status != STATUS_COMPLETED:
                self._status = STATUS_STOPPED
                try:
                    await self._ws.send_json(self._state_event())
                except Exception:  # noqa: BLE001 - socket may be gone
                    pass

    def _neighbor_values(self, sensor) -> list[dict] | None:
        """Per-row compatible neighbor observations for spatial context.

        Only the station's audited selected neighbors participate (neighbor
        graph, <=600 km). No neighbors inside that radius -> None, so the
        spatial layer reports UNAVAILABLE rather than a distant comparison.
        """
        try:
            from src.spatial import decision as SD

            frames = {nid: self._store.noaa_obs[nid]
                      for nid in graph_neighbors(self._root, self._ds)
                      if nid in getattr(self._store, "noaa_obs", {})}
            if not frames:
                return None
            selected = sorted(frames)
            rows: list[dict] = []
            for stamp in sensor["timestamp"].astype(str).tolist():
                target = stamp + "+00:00"
                temp_vals = SD.gather_neighbor_values(
                    target, frames, selected, "temperature_c")
                rh_vals = SD.gather_neighbor_values(
                    target, frames, selected, "relative_humidity_pct")
                rows.append({"temperature": temp_vals, "humidity": rh_vals})
            return rows
        except Exception as exc:  # noqa: BLE001 - absence stays honest
            logger.warning("spatial context unavailable: %s", exc)
            return None

    def _persist_alert(self, result: dict) -> None:
        """Store one replay anomaly in the replay alert store (durable).

        Persistence never breaks the stream: a storage failure is logged and
        the anomaly still reaches the client.
        """
        try:
            RA.record_anomaly(self._root, result, backend_id=self._ds,
                              city=self._city, station_id=self._station_id)
            self._alerts_recorded += 1
        except Exception as exc:  # noqa: BLE001 - stream must survive
            logger.error("replay alert persistence failed: %s", exc)

    def _statistical_reading_event(self, result: dict) -> dict:
        """One real observation + its unified detection result.

        `type` is the frontend contract (unchanged); `event_type` is the
        documented replay contract (OBSERVATION / ANOMALY_DETECTED /
        REPLAY_COMPLETE), plus the required flat severity/confidence/reason.
        """
        observation = {
            "temperature_c": result["temperature"],
            "relative_humidity_pct": result["relative_humidity"],
            "pressure_hpa": result["pressure"],
        }
        detection = {
            "anomaly": result["anomaly"],
            "score": result.get("anomaly_score"),
            "severity": result["severity"],
            "confidence": result["confidence"],
            "confidence_basis": result.get("confidence_basis"),
            "detector": result["detector"],
            "method": result.get("detector_method"),
            "trigger": result.get("trigger"),
            "pattern_estimate": result.get("pattern_estimate"),
            "primary_reason": result["primary_reason"],
            "contributing_factors": result["contributing_factors"],
        }
        return {
            "type": "reading",
            "event_type": "OBSERVATION",
            "station_id": self._station_id,
            "city": self._city,
            "timestamp": result["timestamp"],
            "sequence": self._seq,
            "source_mode": SOURCE_MODE,
            "data_mode": SC.DATA_MODE,
            "observation": observation,
            "observations": observation,
            "detection": detection,
            "severity": result["severity"],
            "confidence": result["confidence"],
            "reason": result["primary_reason"],
            "data_quality": result["data_quality"],
            "anomaly": {"detected": result["anomaly"],
                        "score": result.get("anomaly_score"),
                        "severity": result["severity"],
                        "confidence": result["confidence"],
                        "method": result["detector"]},
            "root_cause": {"class": result["primary_reason"],
                            "confidence": None, "runner_up": None},
            "trigger": result.get("trigger"),
            "evidence": {"contributing_factors": result["contributing_factors"],
                         "spatial": result["spatial_context"],
                         "freeze": result.get("freeze")},
            "spatial_decision": (result["spatial_context"].get("decision")
                                 if result["spatial_context"].get("available")
                                 else None),
            "explanation": {"text": result["primary_reason"], "features": []},
        }

    def _statistical_alert_event(self, result: dict) -> dict:
        """ANOMALY_DETECTED: durable replay alert with its full reason.

        `status` stays the frontend contract value (anomaly/review) so the UI
        badge reads a real anomaly; the durable store state is reported
        separately as `record_status`.
        """
        alert_id = RA.alert_id(str(self._station_id), str(result["timestamp"]),
                               str(result["detector"]))
        return {
            "type": "alert",
            "event_type": "ANOMALY_DETECTED",
            "alert_id": alert_id,
            "station_id": self._station_id,
            "city": self._city,
            "timestamp": result["timestamp"],
            "sequence": self._seq,
            "status": "anomaly",
            "record_status": RA.RECORD_STATUS,
            "event": result["severity"],
            "score": result.get("anomaly_score"),
            "severity": result["severity"],
            "confidence": result["confidence"],
            "detector": result["detector"],
            "observation": {
                "temperature_c": result["temperature"],
                "relative_humidity_pct": result["relative_humidity"],
                "pressure_hpa": result["pressure"],
            },
            "detection": {
                "anomaly": True,
                "score": result.get("anomaly_score"),
                "severity": result["severity"],
                "confidence": result["confidence"],
                "detector": result["detector"],
                "trigger": result.get("trigger"),
                "primary_reason": result["primary_reason"],
            },
            "reason": result["primary_reason"],
            "root_cause": result["primary_reason"],
            "data_quality": result["data_quality"],
            "spatial_decision": (result["spatial_context"].get("decision")
                                 if result["spatial_context"].get("available")
                                 else None),
            "source_mode": SOURCE_MODE,
            "data_mode": "HISTORICAL_REPLAY",
            "summary": (f"{result['severity']} on {self._station_id} at "
                        f"{result['timestamp']}: {result['primary_reason']}."),
        }

    async def _wait(self, delay: float) -> None:
        """Interruptible interval wait (stop/pause react promptly)."""
        end = time.perf_counter() + delay
        while True:
            if self._stop or self._paused:
                return
            remaining = end - time.perf_counter()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.1, remaining))

    def _reading_event(self, timestamp: str, scored: dict) -> dict:
        ens = scored["ensemble"]
        verdict = scored["verdict"]
        dq = scored["data_quality"]
        obs = scored["observations"]
        return {
            "type": "reading",
            "station_id": self._station_id,
            "city": self._city,
            "timestamp": timestamp,
            "sequence": self._seq,
            "data_mode": SC.DATA_MODE,
            "observations": {
                "temperature_c": obs["temperature_c"],
                "relative_humidity_pct": obs["relative_humidity_pct"],
                "pressure_hpa": obs["pressure_hpa"],
            },
            "data_quality": {"status": dq["status"], "ml_eligible": dq["ml_eligible"]},
            "anomaly": {"detected": verdict["is_anomalous"], "score": ens["median"],
                        "confidence": verdict["confidence"],
                        "availability": ens["availability"],
                        "threshold": ens["threshold"],
                        "severity": verdict["severity"],
                        "trigger": verdict["trigger"],
                        "method": verdict["method"]},
            "severity": verdict["severity"],
            "confidence": verdict["confidence"],
            "confidence_basis": verdict["confidence_basis"],
            "trigger": verdict["trigger"],
            "root_cause": {"class": scored["root_cause"]["class"],
                           "confidence": scored["root_cause"]["confidence"],
                           "runner_up": scored["root_cause"]["runner_up"],
                           "basis": scored["root_cause"].get("basis")},
            "evidence": {
                "statistical": scored["evidence"]["statistical"],
                "isolation_forest": scored["evidence"]["isolation_forest"],
                "lstm": scored["evidence"]["lstm"],
                "multivariate": scored["evidence"]["multivariate"],
                "spatial": scored["evidence"]["spatial"],
                "seasonal": scored["evidence"]["seasonal"],
                "freeze": scored["freeze"],
            },
            "spatial_decision": scored["spatial_decision"],
            "explanation": scored["explanation"],
        }

    def _alert_event(self, timestamp: str, scored: dict) -> dict:
        ens = scored["ensemble"]
        verdict = scored["verdict"]
        freeze = scored["freeze"]
        rc = scored["root_cause"]
        rc_class = rc["class"]
        status = "review" if rc_class in (None, CF.UNKNOWN) else "anomaly"
        event = rc_class if rc_class not in (None, CF.UNKNOWN) else "Anomaly"
        score = ens["median"]
        if score is not None and ens["threshold"] is not None:
            score_text = (f"ensemble score {score:.3f} "
                          f"(threshold {ens['threshold']:.3f}, "
                          f"{ens['availability']})")
        else:
            score_text = "no ensemble verdict (insufficient evidence)"
        freeze_note = ""
        if freeze.get("confirmed"):
            freeze_note = (f" Freeze confirmation: {freeze['variable']} unchanged "
                           f"for {freeze['run_hours']:.1f} h "
                           f"({freeze['run_rows']} identical readings).")
        return {
            "type": "alert",
            "alert_id": f"replay:{self._ds}:{self._split}:{self._seq}",
            "station_id": self._station_id,
            "city": self._city,
            "timestamp": timestamp,
            "sequence": self._seq,
            "status": status,
            "event": event,
            "score": score,
            "threshold": ens["threshold"],
            "severity": verdict["severity"],
            "trigger": verdict["trigger"],
            "root_cause": rc_class,
            "root_cause_basis": rc.get("basis"),
            "confidence": rc["confidence"],
            "runner_up": rc["runner_up"],
            "freeze": freeze,
            "spatial_decision": scored["spatial_decision"],
            "data_mode": SC.DATA_MODE,
            "summary": (f"{event} on {self._station_id} at {timestamp}: "
                        f"{score_text}.{freeze_note}"),
        }

    async def _teardown(self) -> None:
        """Disconnect cleanup: stop the loop and release replay frames."""
        self._stop = True
        self._resume.set()
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutting down
                pass
        self._status = STATUS_IDLE
        gc.collect()
