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

from fastapi import WebSocket, WebSocketDisconnect

from src.api.replay import protocol as P
from src.api.replay import source as SRC
from src.api.services import scoring as SC
from src.root_cause import confidence as CF

logger = logging.getLogger("skyguard.replay")

STATUS_IDLE = "idle"
STATUS_PREPARING = "preparing"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_STOPPED = "stopped"
STATUS_COMPLETED = "completed"


def scored_temp(sensor, pos: int) -> float | None:
    """Row temperature for spatial context (None when missing)."""
    try:
        value = float(sensor["temperature_c"].iloc[pos])
    except (TypeError, ValueError, IndexError):
        return None
    return None if math.isnan(value) else value


class ReplaySession:
    """One WebSocket connection's replay lifecycle."""

    def __init__(self, store, websocket: WebSocket) -> None:
        self._store = store
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
        if entry is None or entry.get("backend_station_id") not in ("jena", "delhi"):
            await self._ws.send_json(P.error_event(
                P.UNKNOWN_STATION,
                f"Station '{station_id}' is not available for replay."))
            return
        self._station_id = station_id
        self._ds = entry["backend_station_id"]
        self._city = entry.get("city", "")
        self._split = params["split"]
        self._speed = params["speed"]
        self._limit = params["limit"]
        self._seq = 0
        self._processed = 0
        self._anomalies = 0
        self._ema_elapsed = None
        self._stop = False
        self._paused = False
        self._resume.set()
        self._status = STATUS_PREPARING
        await self._ws.send_json(P.replay_state_event(
            STATUS_PREPARING, station_id, self._split, self._speed))
        self._task = asyncio.create_task(self._replay())

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
        cadence_s = SRC.cadence_minutes(self._ds) * 60.0 if self._ds else None
        if not cadence_s:
            return None
        return round(cadence_s / self._ema_elapsed, 2)

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
            cadence_s = SRC.cadence_minutes(self._ds) * 60.0
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
                if scored["ensemble"]["is_anomalous"]:
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
            "anomaly": {"detected": ens["is_anomalous"], "score": ens["median"],
                        "confidence": ens["confidence"],
                        "availability": ens["availability"],
                        "threshold": ens["threshold"],
                        "method": ens["method"]},
            "root_cause": {"class": scored["root_cause"]["class"],
                           "confidence": scored["root_cause"]["confidence"],
                           "runner_up": scored["root_cause"]["runner_up"]},
            "evidence": {
                "statistical": scored["evidence"]["statistical"],
                "isolation_forest": scored["evidence"]["isolation_forest"],
                "lstm": scored["evidence"]["lstm"],
                "multivariate": scored["evidence"]["multivariate"],
                "spatial": scored["evidence"]["spatial"],
            },
            "spatial_decision": scored["spatial_decision"],
            "explanation": scored["explanation"],
        }

    def _alert_event(self, timestamp: str, scored: dict) -> dict:
        ens = scored["ensemble"]
        rc = scored["root_cause"]
        rc_class = rc["class"]
        status = "review" if rc_class in (None, CF.UNKNOWN) else "anomaly"
        event = rc_class if rc_class not in (None, CF.UNKNOWN) else "Anomaly"
        score = ens["median"] or 0.0
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
            "root_cause": rc_class,
            "confidence": rc["confidence"],
            "runner_up": rc["runner_up"],
            "spatial_decision": scored["spatial_decision"],
            "data_mode": SC.DATA_MODE,
            "summary": (f"{event} on {self._station_id} at {timestamp}: "
                        f"ensemble score {score:.3f} "
                        f"(threshold {ens['threshold']:.3f}, "
                        f"{ens['availability']})."),
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
