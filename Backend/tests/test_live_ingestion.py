"""Phase 23 live-ingestion tests: adapters, history, inference, alerts."""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from src.live import alerts as LA
from src.live import config as LC
from src.live import history as LH
from src.live import inference as LI
from src.live import manager as LM
from src.live import obs as LO
from src.live import sources as LS


def _utc(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 9, 29, hour, minute, tzinfo=dt.timezone.utc)


def _ob(station: str, ts: dt.datetime, temp=None, pres=None, rh=None,
        source: str = "CONTROLLED", basis: str = "station_level",
        oid: str = "") -> LO.CanonicalObservation:
    return LO.CanonicalObservation(
        station_id=station, timestamp=ts, temperature_c=temp,
        pressure_hpa=pres, relative_humidity_pct=rh, source=source,
        source_station_id=station, source_observation_id=oid or
        f"{station}-{ts.isoformat()}", pressure_basis=basis,
        received_at=ts, raw_timestamp=ts.isoformat())


def _manager(**over) -> LM.LiveManager:
    config = LC.LiveConfig()
    config.expected_cadence_min = 5.0
    config.retry_base_s = 0.01
    for key, value in over.items():
        setattr(config, key, value)
    return LM.LiveManager(config=config, db_path=":memory:")


def _feature(wigos: str, name: str, value, units: str, rid: str,
             phen: str) -> dict:
    return {"id": rid, "properties": {
        "id": rid, "wigos_station_identifier": wigos, "name": name,
        "value": value, "units": units, "phenomenonTime": phen,
        "reportTime": phen, "reportId": "R1"}}


# 1. Source adapter parses a valid observation.
def test_1_adapter_parses_valid():
    from src.data_sources.imd_wis2 import normalizer as WN

    features = [_feature("0-20000-0-43295", "air_temperature", 29.5,
                         "Celsius", "r1", "2026-09-29T00:00:00Z"),
                _feature("0-20000-0-43295", "non_coordinate_pressure",
                         1005.0, "hPa", "r2", "2026-09-29T00:00:00Z")]
    records = [WN.parse_record(f) for f in features]
    out = WN.normalize_group("BENGALURU", "Bengaluru",
                             "2026-09-29T00:00:00+00:00", records)
    assert out.temperature_c == 29.5
    assert out.pressure_hpa == 1005.0
    assert out.relative_humidity_pct is None


# 2. Unit normalization (Fahrenheit, Pascal).
def test_2_unit_normalization():
    from src.data_sources.imd_wis2 import normalizer as WN

    assert WN.to_celsius(32.0, "Fahrenheit", "air_temperature") == pytest.approx(0.0)
    assert WN.to_hpa(101300.0, "Pa", "non_coordinate_pressure") == pytest.approx(1013.0)
    with pytest.raises(WN.NormalizationError):
        WN.to_celsius(10.0, "Kelvin", "air_temperature")


# 3. Timezone handling (UTC preserved, naive assumed UTC).
def test_3_timezone():
    assert LO.parse_utc_instant("2026-09-29T00:00:00Z").tzinfo is not None
    assert LO.parse_utc_instant("2026-09-29 05:30:00").isoformat() == \
        "2026-09-29T05:30:00+00:00"


# 4. Missing RH stays missing (never manufactured).
def test_4_missing_rh():
    source = LS.IMDWIS2Source(stations=["PATNA"])
    features = [_feature("0-20000-0-42492", "air_temperature", 30.0,
                         "Celsius", "r1", "2026-09-29T00:00:00Z"),
                _feature("0-20000-0-42492", "dewpoint_temperature", 24.0,
                         "Celsius", "r2", "2026-09-29T00:00:00Z")]
    from src.data_sources.imd_wis2 import normalizer as WN

    records = [WN.parse_record(f) for f in features]
    out = source._normalize("PATNA", records)
    assert len(out) == 1
    assert out[0].relative_humidity_pct is None


# 5. Pressure basis preserved per audited capability.
def test_5_pressure_basis():
    source = LS.IMDWIS2Source(stations=["PATNA", "BENGALURU"])
    from src.data_sources.imd_wis2 import normalizer as WN

    patna = source._normalize("PATNA", [WN.parse_record(
        _feature("0-20000-0-42492", "pressure_reduced_to_mean_sea_level",
                 1008.0, "hPa", "r1", "2026-09-29T00:00:00Z"))])
    assert patna[0].pressure_hpa is None
    assert patna[0].pressure_basis == "unavailable"
    beng = source._normalize("BENGALURU", [WN.parse_record(
        _feature("0-20000-0-43295", "non_coordinate_pressure",
                 1005.0, "hPa", "r1", "2026-09-29T00:00:00Z"))])
    assert beng[0].pressure_hpa == 1005.0
    assert beng[0].pressure_basis == "station_level"


# 6. Duplicate observation ignored (idempotent, single inference).
def test_6_duplicate_ignored():
    manager = _manager()
    ob = _ob("S1", _utc(0), temp=29.0, pres=1005.0, rh=55.0)
    assert manager._ingest(ob) is True
    assert manager._ingest(ob) is False
    assert len(manager.store.observations("S1")) == 1


# 7. Out-of-order arrivals handled without rewriting decisions.
def test_7_out_of_order():
    hist = LH.StationHistory("S1")
    for hour in range(6):
        assert hist.add(_ob("S1", _utc(hour), temp=29.0)) == LO.VALID
    assert hist.add(_ob("S1", _utc(0, 30), temp=29.1)) == LO.OUT_OF_ORDER
    assert hist.add(_ob("S1", _utc(5, 30), temp=29.2)) == LO.VALID
    stamps = [o.timestamp for o in hist._rows]
    assert stamps == sorted(stamps)


# 8. Causal history only (frame chronological, neighbors bounded).
def test_8_causal_history():
    hist = LH.StationHistory("S1")
    for i in range(5):
        hist.add(_ob("S1", _utc(i), temp=29.0 + i * 0.1))
    frame = hist.frame()
    assert (pd_timestamp(frame) == sorted(pd_timestamp(frame)))
    vals = LI._neighbor_values(_utc(4, 30), {"S1": hist}, "S1", "temperature_c")
    assert vals == {}
    other = LH.StationHistory("S2")
    other.add(_ob("S2", _utc(4), temp=28.0))
    vals = LI._neighbor_values(_utc(4, 30), {"S1": hist, "S2": other},
                               "S1", "temperature_c")
    assert vals == {"S2": 28.0}


def pd_timestamp(frame):
    import pandas as pd

    return pd.to_datetime(frame["timestamp"]).tolist()


# 9. Warm-up state instead of NORMAL.
def test_9_warmup_state():
    hist = LH.StationHistory("S1")
    for i in range(3):
        hist.add(_ob("S1", _utc(i), temp=29.0))
    assert hist.warm_state() == LO.WARMING_UP
    scored = LI.score_station(hist, {"S1": hist}, 5.0)
    assert scored["verdict"] == LO.WARMING_UP
    assert scored["base_decision"] == "BASE_INSUFFICIENT"


# 10. LSTM stays unavailable without manufactured history.
def test_10_lstm_insufficient():
    hist = LH.StationHistory("S1")
    for i in range(5):
        hist.add(_ob("S1", _utc(i), temp=29.0))
    assert hist.lstm_available() is False
    scored = LI.score_station(hist, {"S1": hist}, 5.0)
    assert scored["ml_models"]["available"] is False


# 11. Source timeout surfaces as structured error.
def test_11_source_timeout():
    class Dead(LS.ObservationSource):
        name = "DEAD"

        def fetch_new(self):
            raise LS.SourceError("timeout", "request timed out")

    manager = _manager(max_retries=1)
    manager.source = Dead()
    manager.source_name = "DEAD"
    out = asyncio.run(manager.poll_once())
    assert out["state"] == LM.ERROR
    assert out["code"] == "timeout"


# 12. Retries are bounded (no infinite loop).
def test_12_bounded_retry():
    calls = {"n": 0}

    class Flaky(LS.ObservationSource):
        name = "FLAKY"

        def fetch_new(self):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise LS.SourceError("connection_failed", "down")
            return []

    manager = _manager(max_retries=3)
    manager.source = Flaky()
    manager.source_name = "FLAKY"
    out = asyncio.run(manager.poll_once())
    assert out["state"] == LM.RUNNING
    assert calls["n"] == 3


# 13. Source silence becomes a stale availability event.
def test_13_stale_detection():
    manager = _manager()
    hist = manager.history_for("S1")
    old = _utc(0) - dt.timedelta(minutes=200)
    hist.add(_ob("S1", old, temp=29.0))
    manager._check_silence()
    assert "S1" in manager._silence_flagged


# 14. Heartbeat fields track fetch health.
def test_14_heartbeat():
    manager = _manager()
    manager.source = LS.ControlledLiveSource(
        script=[_ob("S1", _utc(0), temp=29.0)])
    manager.source_name = "CONTROLLED"
    asyncio.run(manager.poll_once())
    assert manager.last_success is not None
    assert manager.last_attempt is not None
    assert manager.snapshot()["last_success"] is not None


# 15+16. Shared scorer + shared spatial layer (no forks).
def test_15_16_shared_pipeline():
    import inspect

    source = inspect.getsource(LI)
    assert "prepare_split" in source
    assert "build_statistical_baseline" in source
    assert "decide_context" in source
    assert "live_scoring" not in source.replace("shared", "")


# 17. Future neighbors cannot influence live spatial evidence.
def test_17_future_neighbor_rejected():
    hist = LH.StationHistory("S1")
    other = LH.StationHistory("S2")
    for i in range(13):
        hist.add(_ob("S1", _utc(i), temp=29.0))
    # Neighbor exists only in the future: unusable at decision time.
    other.add(_ob("S2", _utc(12) + dt.timedelta(hours=5), temp=29.0))
    vals = LI._neighbor_values(_utc(12), {"S1": hist, "S2": other},
                               "S1", "temperature_c")
    assert vals == {"S2": None}


# 18. Reference-outcome fields absent from the live path.
def test_18_no_truth_in_live_path():
    import inspect

    import src.live.alerts as live_alerts
    import src.live.inference as live_inference
    import src.live.manager as live_manager
    import src.live.store as live_store

    for module in (live_inference, live_manager, live_alerts, live_store,
                   LS, LH, LO):
        lowered = inspect.getsource(module).lower()
        for token in ("injection_id", "fault_type", "ground_truth",
                      "event_results", "end_to_end_diagnosis"):
            assert token not in lowered, f"{module.__name__}: {token}"


# 19-21. Alert opened from inference, extended (not duplicated), resolved.
def test_19_20_21_alert_lifecycle():
    from src.api.services import live_service as LV

    manager = _manager()
    script = LV.build_demo_script(_utc(0))
    for ob in script:
        manager._ingest(ob)
    episodes = manager.store.episodes(DEMO_STATION)
    assert episodes, "spike must open an episode"
    assert all(e["interpretation"] for e in episodes)
    assert all("live-" in e["alert_id"] for e in episodes)
    opened = [e for e in episodes if e["status"] == "OPEN"]
    resolved = [e for e in episodes if e["status"] == "RESOLVED"]
    assert len(episodes) <= 2  # grouped, never per-poll spam
    assert opened or resolved
    for ob in script:  # replaying the script = duplicates, no new episodes
        manager._ingest(ob)
    assert len(manager.store.episodes(DEMO_STATION)) == len(episodes)


DEMO_STATION = "PATNA-TEST-01"


# 22. Restart preserves persisted operational state.
def test_22_restart_persistence(tmp_path):
    import src.live.store as live_store

    db = str(tmp_path / "live.sqlite")
    first = LM.LiveManager(config=LC.LiveConfig(), db_path=db)
    first.store.upsert_episode(
        {"alert_id": "live-abc", "station_id": "S1",
         "episode_key": "S1|ANOMALY", "interpretation": "LOCAL_SENSOR_ANOMALY",
         "started_at": "2026-09-29T00:00:00+00:00",
         "last_seen_at": "2026-09-29T00:05:00+00:00", "detection_count": 2,
         "status": "OPEN", "resolved_at": None, "score": 5.0}, {})
    second = LM.LiveManager(config=LC.LiveConfig(), db_path=db)
    assert any(e["alert_id"] == "live-abc"
               for e in second.tracker.open_episodes())
    assert live_store.SCHEMA.count("ground_truth") == 0
    assert live_store.SCHEMA.count("injection_id") == 0


# 23. Controlled-live demo runs end to end (causal, labeled as such).
def test_23_controlled_demo():
    from src.api.services import live_service as LV

    script = LV.build_demo_script(_utc(0))
    stamps = [o.timestamp for o in script]
    assert stamps == sorted(stamps)
    assert all(o.source == "CONTROLLED" for o in script)
    assert LV.DEMO_STATION == "PATNA-TEST-01"
    manager = _manager()
    manager.source = LS.ControlledLiveSource(script=script)
    manager.source_name = "CONTROLLED"
    while not manager.source.exhausted:
        asyncio.run(manager.poll_once())
    episodes = manager.store.episodes("PATNA-TEST-01")
    assert episodes


# 24. IMD unavailable behavior is structured, never synthesized.
def test_24_imd_unavailable(monkeypatch):
    monkeypatch.delenv("IMD_ARG_BASE_URL", raising=False)
    source = LS.IMDArgSource()
    with pytest.raises(LS.SourceError) as exc:
        source.fetch_new()
    assert exc.value.code == "not_configured"
    manager = _manager()
    assert manager.snapshot()["state"] == LM.LIVE_UNAVAILABLE


# 25. No secret values in configs, errors, or descriptions.
def test_25_no_secret_logging(monkeypatch):
    monkeypatch.setenv("IMD_ARG_API_KEY", "super-secret-key")
    monkeypatch.setenv("IMD_ARG_BASE_URL", "https://example.invalid/oapi")
    import json

    config = LS.IMDArgConfig.from_env()
    assert config.api_key_present is True
    blob = json.dumps([LS.IMDArgSource(config).describe(),
                       str(LS.SourceError("x", "y"))])
    assert "super-secret-key" not in blob
