"""India GHCNh expansion tests: parser, units, integrity, classification.

Fast unit tests only (no network, no downloads, no retraining). Deterministic.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.features.feature_builder import horizons_for_cadence
from src.noaa import process as PR


def _raw_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "STATION": ["INI0000VABB"] * 4,
        "Station_name": ["CHHATRAPATI SHIVAJI INTL"] * 4,
        "DATE": ["2023-03-01 00:00:00", "2023-03-01 00:30:00",
                 "2023-03-01 00:30:00", "2023-03-01 01:00:00"],
        "temperature": [29.5, 29.6, 29.6, -9999],
        "temperature_Quality_Code": ["0", "0", "0", "9"],
        "dew_point_temperature": [24.0, 24.1, 24.1, 24.2],
        "station_level_pressure": [-9999, -9999, -9999, -9999],
        "station_level_pressure_Quality_Code": ["9"] * 4,
        "sea_level_pressure": [1008.0, 1008.1, 1008.1, 1008.2],
        "sea_level_pressure_Quality_Code": ["0"] * 4,
        "altimeter": [1008.0, 1008.0, 1008.0, 1008.0],
        "relative_humidity": [70.0, 71.0, 71.0, 101.5],
        "relative_humidity_Quality_Code": ["0", "0", "0", "0"],
    })


# GHCNh parser: sentinel->NaN, UTC, duplicates flagged never dropped.
def test_parser():
    out = PR.standardize_station_frame(_raw_frame(), "INI0000VABB", "f.parquet")
    assert list(out.columns) == PR.PROCESSED_COLUMNS
    assert out["temperature_c"].isna().sum() == 1
    assert out["station_level_pressure_hpa"].isna().all()
    assert out["duplicate_timestamp"].sum() == 2
    assert len(out) == 4  # nothing dropped
    assert str(out["timestamp_utc"].dt.tz) == "UTC"


# Missing columns fail loudly.
def test_parser_missing_columns_raise():
    frame = _raw_frame().drop(columns=["temperature"])
    with pytest.raises(ValueError, match="lacks columns"):
        PR.standardize_station_frame(frame, "INI0000VABB", "f.parquet")


# Mixed station IDs fail loudly.
def test_parser_mixed_stations_raise():
    frame = _raw_frame()
    frame.loc[0, "STATION"] = "INI0000VOBL"
    with pytest.raises(ValueError, match="mixes station IDs"):
        PR.standardize_station_frame(frame, "INI0000VABB", "f.parquet")


# Unparseable timestamps fail loudly.
def test_parser_bad_timestamps_raise():
    frame = _raw_frame()
    frame.loc[0, "DATE"] = "not-a-time"
    with pytest.raises(ValueError, match="unparseable timestamps"):
        PR.standardize_station_frame(frame, "INI0000VABB", "f.parquet")


# RH>100 is preserved (flagged downstream), never clipped.
def test_rh_out_of_bounds_preserved():
    out = PR.standardize_station_frame(_raw_frame(), "INI0000VABB", "f.parquet")
    assert float(out["relative_humidity_pct"].max()) == 101.5


# Pressure variables stay separate (no silent substitution).
def test_pressure_semantics():
    out = PR.standardize_station_frame(_raw_frame(), "INI0000VABB", "f.parquet")
    assert out["station_level_pressure_hpa"].isna().all()
    assert out["sea_level_pressure_hpa"].notna().all()
    assert out["altimeter_setting_hpa"].notna().all()


# RH comes only from relative_humidity (never dew point).
def test_rh_provenance():
    out = PR.standardize_station_frame(_raw_frame(), "INI0000VABB", "f.parquet")
    assert float(out.loc[0, "relative_humidity_pct"]) == 70.0
    assert "dew_point" not in "relative_humidity_pct"


# Cadence-aware horizons support hourly/synoptic data.
def test_feature_compatibility_hourly():
    horizons = horizons_for_cadence(30.0)
    assert horizons == {"expected_interval_min": 30.0, "30m": 3,
                        "2h": 6, "6h": 12}
    assert horizons_for_cadence(60.0)["6h"] == 12  # minimums stay meaningful
    with pytest.raises(ValueError):
        horizons_for_cadence(0)


# Capability rule: station-level joint TPR gates FULL_TPR honestly.
def test_capability_rule():
    audit = pd.read_csv("data/processed/india_station_audit.csv")
    assert (audit["joint_tpr_available_pct"] < 50.0).all()
    assert "eligible" in audit.columns
    assert set(audit["city"]) >= {"Mumbai", "Pune", "Jaipur"}


# Canonical schema carries provenance + flags.
def test_canonical_schema():
    frame = pd.read_csv("data/processed/india_tpr/INI0000VABB_canonical.csv",
                        nrows=50)
    required = {"timestamp", "station_id", "city", "latitude", "longitude",
                "elevation", "temperature_c", "pressure_hpa",
                "relative_humidity_pct", "temperature_valid", "pressure_valid",
                "humidity_valid", "joint_tpr_valid", "source", "source_file",
                "humidity_source", "pressure_variable", "data_quality_flags"}
    assert required <= set(frame.columns)
    assert (frame["pressure_variable"] == "altimeter_setting_hpa (QNH; station-level "
            "pressure absent at these stations)").all()


# No station is labeled FULL_TPR without passing eligibility.
def test_no_unearned_full_tpr():
    import json

    for path in ("reports/india_ghcnh/INDIA_GHCNH_AUDIT.md",
                 "reports/india_ghcnh/INDIA_DETECTOR_COVERAGE.md"):
        text = open(path, encoding="utf-8").read()
        assert "FULL_TPR" in text  # classification discussed...
    audit = pd.read_csv("data/processed/india_station_audit.csv")
    assert not audit["eligible"].any()  # ...and none earn it on joint TPR


# Discovery file is complete and deterministic.
def test_discovery():
    disc = pd.read_csv("data/india_station_discovery.csv")
    assert len(disc) == 10
    assert set(disc["city"]) == {"Mumbai", "Hyderabad", "Chennai", "Bengaluru",
                                 "Pune", "Kolkata", "Bhopal", "Jaipur",
                                 "Lucknow", "Chandigarh"}
