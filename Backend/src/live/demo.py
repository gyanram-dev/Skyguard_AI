"""Controlled-live end-to-end demo runner (PATNA-TEST-01).

Drives a LiveManager through the scripted scenario without sleeps:
warm-up -> spike alert -> recovery/resolution -> source stop -> stale
flag on a silent station -> duplicate suppression -> restart restore.
Writes ``reports/phase23/live_demo_run.json``. Controlled traffic only;
never IMD data.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from src.live import config as LC
from src.live import manager as LM
from src.live import obs as LO
from src.live import sources as LS


def main() -> dict:
    root = Path(".")
    out_dir = root / "reports" / "phase23"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(root / "data" / "live" / "demo_run.sqlite")

    config = LC.LiveConfig()
    config.mode = LC.CONTROLLED_LIVE
    config.expected_cadence_min = 5.0
    config.poll_interval_s = 5.0
    config.retry_base_s = 0.01

    base = LO.utcnow().replace(second=0, microsecond=0)
    from src.api.services import live_service as LV

    script = LV.build_demo_script(base)
    manager = LM.LiveManager(config=config, db_path=db_path)

    import asyncio

    source = LS.ControlledLiveSource(script=script)
    manager.source = source
    manager.source_name = source.name
    manager.status = LM.RUNNING
    while not source.exhausted:
        asyncio.run(manager.poll_once())
    # Source exhausted: one more poll observes the stopped source.
    asyncio.run(manager.poll_once())

    # Silent station proves source-silence detection.
    stale_ob = LO.CanonicalObservation(
        station_id="STALE-STATION",
        timestamp=base - dt.timedelta(hours=3),
        temperature_c=29.0, pressure_hpa=1005.0,
        relative_humidity_pct=55.0, source="CONTROLLED",
        source_station_id="STALE-STATION",
        source_observation_id="stale-1", pressure_basis="station_level",
        received_at=base - dt.timedelta(hours=3),
        raw_timestamp=(base - dt.timedelta(hours=3)).isoformat())
    manager._ingest(stale_ob)
    manager._check_silence()

    # Duplicate re-ingest changes nothing.
    before = len(manager.store.episodes("PATNA-TEST-01"))
    for ob in script:
        manager._ingest(ob)
    after = len(manager.store.episodes("PATNA-TEST-01"))

    # Restart restore from the same database file.
    revived = LM.LiveManager(config=config, db_path=db_path)
    restored = [e["alert_id"] for e in revived.tracker.open_episodes()]

    episodes = manager.store.episodes("PATNA-TEST-01")
    observations = manager.store.observations("PATNA-TEST-01", limit=1000)
    lat = sorted(manager.latencies_ms)
    import statistics

    payload = {
        "label": "CONTROLLED LIVE DEMO (scripted, not IMD data)",
        "station": "PATNA-TEST-01",
        "cadence_min": 5.0,
        "observations_ingested": len(observations),
        "script_length": len(script),
        "episodes": episodes,
        "episodes_before_duplicates": before,
        "episodes_after_duplicates": after,
        "silence_flagged": sorted(manager._silence_flagged),
        "restart_restored_open": restored,
        "inference_latency_ms": {
            "n": len(lat),
            "p50": round(statistics.median(lat), 2) if lat else None,
            "p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 2)
            if lat else None,
            "max": round(max(lat), 2) if lat else None},
        "fetch_latency_ms": {"note": "controlled feed: no network fetch"},
        "generated_utc": LO.utcnow().isoformat(),
    }
    (out_dir / "live_demo_run.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")
    asyncio.run(manager.stop())
    return payload


if __name__ == "__main__":
    started = time.perf_counter()
    payload = main()
    print(f"episodes={len(payload['episodes'])} "
          f"obs={payload['observations_ingested']} "
          f"stale={payload['silence_flagged']} "
          f"p50={payload['inference_latency_ms']['p50']}ms "
          f"p95={payload['inference_latency_ms']['p95']}ms "
          f"({time.perf_counter() - started:.1f}s)")
