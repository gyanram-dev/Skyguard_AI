"""Live ingestion manager: one background loop, many stations.

Poll cycle: fetch (worker thread, bounded timeout) -> dedupe by
observation identity -> causal history insert -> shared inference ->
episode tracking -> SQLite persistence. Per-cycle retries use bounded
exponential backoff and then yield to the schedule (no infinite retry
loop). Station silence past cadence x multiples raises a
DATA_SOURCE_STALE availability event — never a sensor anomaly.
"""

from __future__ import annotations

import asyncio
import logging
import time

from src.live import alerts as LA
from src.live import config as LC
from src.live import history as LH
from src.live import inference as LI
from src.live import obs as LO
from src.live import sources as LS
from src.live import store as LST

logger = logging.getLogger("skyguard.live_manager")

IDLE = "IDLE"
RUNNING = "RUNNING"
STOPPED = "STOPPED"
ERROR = "ERROR"
LIVE_UNAVAILABLE = "LIVE_UNAVAILABLE"
NOT_CONFIGURED = "NOT_CONFIGURED"
CONFIGURED = "CONFIGURED"
CONNECTION_FAILED = "CONNECTION_FAILED"
CONNECTED = "CONNECTED"
CONTROLLED = "CONTROLLED"


class LiveManager:
    """Owns sources, histories, episodes and persistence for live modes."""

    def __init__(self, config: LC.LiveConfig | None = None,
                 db_path: str | None = None) -> None:
        self.config = config or LC.LiveConfig()
        self.store = LST.LiveStore(db_path or self.config.db_path)
        self.histories: dict[str, LH.StationHistory] = {}
        self.tracker = LA.EpisodeTracker()
        self.tracker.restore(self.store.open_episodes())
        self.status = IDLE
        self.provider_status = self._initial_provider_status()
        self.source: LS.ObservationSource | None = None
        self.source_name = ""
        self.last_attempt: str | None = None
        self.last_success: str | None = None
        self.last_error: str = ""
        self.consecutive_failures = 0
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._silence_flagged: set[str] = set()
        self.latencies_ms: list[float] = []

    # ---- lifecycle ----

    def history_for(self, station_id: str) -> LH.StationHistory:
        if station_id not in self.histories:
            self.histories[station_id] = LH.StationHistory(
                station_id, maxlen=self.config.history_maxlen)
        return self.histories[station_id]

    def _initial_provider_status(self) -> str:
        if self.config.mode == LC.CONTROLLED_LIVE:
            return CONTROLLED
        if self.config.mode == LC.LIVE_IMD:
            return (CONFIGURED if self.config.provider == "IMD_WIS2"
                    and self.config.base_url else NOT_CONFIGURED)
        if self.config.mode == LC.LIVE_ARG:
            return (CONFIGURED if self.config.describe()["arg_configured"]
                    else NOT_CONFIGURED)
        return NOT_CONFIGURED

    async def start(self, source: LS.ObservationSource | None = None) -> dict:
        """Start the loop (idempotent). Returns a safe status snapshot."""
        if self._task is not None and not self._task.done():
            return self.snapshot()
        source = source or self._default_source()
        if source is None:
            self.provider_status = self._initial_provider_status()
            return {"state": LIVE_UNAVAILABLE, "status": self.provider_status,
                    "provider_status": self.provider_status,
                    "detail": _unavailable_detail(self.config)}
        self.source = source
        self.source_name = source.name
        self._stop.clear()
        self.status = RUNNING
        self._task = asyncio.create_task(self._loop())
        logger.info("Live manager started (source=%s)", source.name)
        return self.snapshot()

    async def stop(self) -> dict:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._task = None
        self.status = STOPPED
        return self.snapshot()

    def _default_source(self) -> LS.ObservationSource | None:
        mode = self.config.mode
        if mode == LC.CONTROLLED_LIVE:
            return None  # caller injects the scripted source
        if mode == LC.LIVE_IMD:
            if self.provider_status == NOT_CONFIGURED:
                return None
            return LS.IMDWIS2Adapter(
                stations=self.config.stations or None,
                timeout_s=self.config.timeout_s, base_url=self.config.base_url,
                ca_bundle=self.config.ca_bundle,
                headers=self.config.request_headers,
                client_cert=self.config.client_certificate,
                client_key=self.config.client_key)
        if mode == LC.LIVE_ARG:
            return LS.IMDArgSource()
        return None

    # ---- polling ----

    async def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                tick = time.perf_counter()
                await self.poll_once()
                elapsed = time.perf_counter() - tick
                await self._sleep(max(0.0, self.config.poll_interval_s - elapsed))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - loop survives, state recorded
            logger.exception("Live loop failure")
            self.status = ERROR
        finally:
            if self.status == RUNNING:
                self.status = STOPPED

    async def _sleep(self, delay: float) -> None:
        end = time.perf_counter() + delay
        while not self._stop.is_set():
            remaining = end - time.perf_counter()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.5, remaining))

    async def poll_once(self) -> dict:
        """One fetch→score→persist cycle (also the unit of testing)."""
        if self.source is None:
            return {"state": LIVE_UNAVAILABLE, "fetched": 0}
        self.last_attempt = LO.utcnow().isoformat()
        try:
            fetched = await asyncio.to_thread(self._fetch_with_retry)
        except LS.SourceError as exc:
            return self._record_failure(exc.code, exc.detail)
        self.consecutive_failures = 0
        self.provider_status = (
            CONNECTED if self.config.mode == LC.LIVE_IMD else
            CONTROLLED if self.source.name == "CONTROLLED" else
            NOT_CONFIGURED)
        self.last_success = LO.utcnow().isoformat()
        self.last_error = ""
        processed = 0
        for ob in fetched:
            if self._ingest(ob):
                processed += 1
        self._check_silence()
        self.store.set_source_status(
            self.source_name, RUNNING, self.last_success, self.last_attempt,
            "", {"stations": sorted(self.histories)})
        return {"state": RUNNING, "fetched": len(fetched),
                "processed": processed}

    def _fetch_with_retry(self) -> list:
        assert self.source is not None
        attempts = 0
        while True:
            try:
                return self.source.fetch_new()
            except LS.SourceError:
                attempts += 1
                if attempts > self.config.max_retries:
                    raise
                time.sleep(min(self.config.retry_base_s * (2 ** (attempts - 1)),
                               60.0))

    def _record_failure(self, code: str, detail: str) -> dict:
        self.consecutive_failures += 1
        self.provider_status = CONNECTION_FAILED
        safe_detail = self.config.redact(detail)
        self.last_error = f"{code}: {safe_detail}"
        logger.warning("Live fetch failed (%s)", code)
        self.store.set_source_status(
            self.source_name or "unknown", ERROR, self.last_success,
            self.last_attempt or LO.utcnow().isoformat(), self.last_error)
        return {"state": ERROR, "code": code, "fetched": 0}

    # ---- ingest ----

    def _ingest(self, ob: LO.CanonicalObservation) -> bool:
        """Persist + score one observation. False = duplicate, no inference."""
        now = LO.utcnow().isoformat()
        if not self.store.save_observation(ob, LO.VALID, now):
            return False
        history = self.history_for(ob.station_id)
        row_state = history.add(ob)
        if row_state == LO.DUPLICATE:
            return False
        if row_state == LO.OUT_OF_ORDER:
            self.store.save_quality_event(
                ob.station_id, ob.timestamp.isoformat(), LO.OUT_OF_ORDER,
                "Late arrival kept out of issued decisions.")
            self.store.save_observation(ob, LO.OUT_OF_ORDER, now)
            return True
        if row_state == LO.MISSING:
            self.store.save_quality_event(
                ob.station_id, ob.timestamp.isoformat(), LO.MISSING,
                "All core variables missing; preserved, not scored.")
            return True
        scored = LI.score_station(history, self.histories,
                                  self.config.expected_cadence_min)
        self._silence_flagged.discard(ob.station_id)
        event = self.tracker.observe(ob.station_id, scored)
        if event is not None and event["action"] in ("opened", "extended"):
            self.store.upsert_episode(event["episode"], scored)
            self.store.link_observation(event["episode"]["alert_id"],
                                        ob.obs_id,
                                        ob.timestamp.isoformat(),
                                        scored.get("anomaly_score"))
        elif event is not None and event["action"] == "resolved":
            self.store.upsert_episode(event["episode"], scored)
        self.latencies_ms.append(float(scored.get("inference_ms") or 0.0))
        if len(self.latencies_ms) > 2000:
            del self.latencies_ms[:1000]
        return True

    def _check_silence(self) -> None:
        """Flag stations silent past cadence x multiples (availability,
        never anomaly)."""
        now = LO.utcnow()
        limit_s = (self.config.expected_cadence_min * 60.0
                   * self.config.stale_after_multiples)
        for sid, hist in self.histories.items():
            latest = hist.latest()
            if latest is None or sid in self._silence_flagged:
                continue
            if (now - latest.timestamp).total_seconds() > limit_s:
                self._silence_flagged.add(sid)
                self.store.save_quality_event(
                    sid, now.isoformat(), LO.DATA_SOURCE_STALE,
                    f"No observation for over {limit_s / 60.0:.0f} minutes "
                    f"(expected every {self.config.expected_cadence_min:.0f}).")

    def snapshot(self) -> dict:
        import statistics

        lat = sorted(self.latencies_ms)
        perf = {}
        if lat:
            perf = {"n": len(lat), "p50_ms": round(statistics.median(lat), 2),
                    "p95_ms": round(lat[min(len(lat) - 1,
                                             int(len(lat) * 0.95))], 2)}
        return {
            "state": self.status if self.source is not None else LIVE_UNAVAILABLE,
            "mode": self.config.mode,
            "status": self.provider_status,
            "provider_status": self.provider_status,
            "source": self.source_name or None,
            "stations": sorted(self.histories),
            "last_attempt": self.last_attempt,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "detail": (_unavailable_detail(self.config)
                       if self.source is None
                       and self.provider_status == NOT_CONFIGURED
                       else "Provider configured; live ingestion has not been started."
                       if self.source is None else None),
            "open_episodes": len(self.tracker.open_episodes()),
            "inference_latency": perf,
        }


def _unavailable_detail(config: LC.LiveConfig) -> str:
    if config.mode == LC.DISABLED:
        return ("Live ingestion is disabled (LIVE_SOURCE_MODE=DISABLED). "
                "Enable CONTROLLED_LIVE for the scripted demo or LIVE_IMD "
                "with IMD_BASE_URL for configured WIS2 polling.")
    if config.mode == LC.CONTROLLED_LIVE:
        return ("CONTROLLED_LIVE needs an injected scripted source; start it "
                "from the controlled-live demo.")
    return ("Live provider configuration is missing. Set LIVE_PROVIDER and "
            "IMD_BASE_URL before starting live ingestion.")
