"""Live operational service: manager ownership + controlled demo script.

One process-wide LiveManager (lazy). The controlled-live demo
(PATNA-TEST-01, 5-minute cadence: warm-up normals, spike, recovery,
source stop) is built here from plain canonical observations — never
presented as IMD data.
"""

from __future__ import annotations

import datetime as dt
import logging

from src.live import config as LC
from src.live import manager as LM
from src.live import obs as LO
from src.live import sources as LS

logger = logging.getLogger("skyguard.live_service")

MANAGER: LM.LiveManager | None = None

DEMO_STATION = "PATNA-TEST-01"
DEMO_CADENCE_MIN = 5.0


def get_manager() -> LM.LiveManager:
    global MANAGER
    if MANAGER is None:
        MANAGER = LM.LiveManager()
    return MANAGER


def reset_manager(config: LC.LiveConfig | None = None,
                  db_path: str | None = None) -> LM.LiveManager:
    """Test/demo hook: replace the process manager (closes nothing shared)."""
    global MANAGER
    MANAGER = LM.LiveManager(config=config, db_path=db_path or ":memory:")
    return MANAGER


def build_demo_script(start: dt.datetime | None = None) -> list:
    """PATNA-TEST-01 controlled scenario (chronological, causal)."""
    base = start or dt.datetime(2026, 9, 29, 0, 0, tzinfo=dt.timezone.utc)
    script: list[LO.CanonicalObservation] = []

    def obs(i: int, temp, pres: float = 1005.0, rh: float = 55.0):
        return LO.CanonicalObservation(
            station_id=DEMO_STATION,
            timestamp=base + dt.timedelta(minutes=DEMO_CADENCE_MIN * i),
            temperature_c=temp, pressure_hpa=pres,
            relative_humidity_pct=rh, source="CONTROLLED",
            source_station_id=DEMO_STATION,
            source_observation_id=f"demo-{i:04d}",
            pressure_basis="station_level",
            latitude=25.6, longitude=85.1667, elevation=57,
            received_at=base + dt.timedelta(minutes=DEMO_CADENCE_MIN * i),
            raw_timestamp=(base + dt.timedelta(
                minutes=DEMO_CADENCE_MIN * i)).isoformat())

    for i in range(30):  # warm-up + steady normals (2h+ of context)
        script.append(obs(i, 29.0 + (i % 3) * 0.2))
    script.append(obs(30, 29.1))
    script.append(obs(31, 47.5))  # spike
    script.append(obs(32, 29.2))  # recovery
    script.append(obs(33, 29.0))
    return script


async def start_controlled_demo() -> dict:
    """Start CONTROLLED_LIVE with the demo script (judge-safe fallback)."""
    manager = get_manager()
    if manager.status == LM.RUNNING:
        return manager.snapshot()
    source = LS.ControlledLiveSource(script=build_demo_script())
    manager.config.mode = LC.CONTROLLED_LIVE
    manager.config.expected_cadence_min = DEMO_CADENCE_MIN
    out = await manager.start(source)
    out["demo"] = {"station": DEMO_STATION, "label": "CONTROLLED LIVE DEMO",
                   "note": "Scripted observations, not IMD data."}
    return out
