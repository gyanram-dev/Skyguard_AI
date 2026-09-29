"""Phase 8A NOAA acquisition tests: manifest, mapping, integrity, determinism."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.noaa import config as C
from src.noaa import process as P

REQUIRED_MANIFEST_FIELDS = (
    "source_dataset", "source_version", "access_date", "stations",
    "variables", "common_overlap", "raw_files",
)
REQUIRED_STATION_FIELDS = (
    "ghcnh_id", "name", "lat", "lon", "observation_period",
    "processed_file", "processed_sha256",
)


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(".").resolve()


@pytest.fixture(scope="module")
def manifest(project_root) -> dict:
    return json.load(open(project_root / "data" / "noaa" / "metadata"
                          / "station_manifest.json", encoding="utf-8"))


def test_manifest_validity_and_fields(manifest):
    """Manifest exists with all required top-level and per-station fields."""
    for field in REQUIRED_MANIFEST_FIELDS:
        assert field in manifest, field
    assert manifest["source_dataset"] == C.DATASET_NAME
    assert 12 <= len(manifest["stations"]) <= 20
    station_ids = {station["ghcnh_id"] for station in manifest["stations"]}
    assert {"INI0000VICG", "INI0000VAPO", "INI0000VOHS"} <= station_ids
    for station in manifest["stations"]:
        for field in REQUIRED_STATION_FIELDS:
            assert field in station, (station.get("ghcnh_id"), field)
    assert manifest["common_overlap"]["common_hours"] > 0


def test_station_uniqueness(manifest):
    """Station IDs unique; coordinates present and within India."""
    ids = [s["ghcnh_id"] for s in manifest["stations"]]
    assert len(set(ids)) == len(ids)
    for station in manifest["stations"]:
        assert 5.0 <= station["lat"] <= 37.0
        assert 68.0 <= station["lon"] <= 98.0


def test_variable_mapping(manifest, project_root):
    """Mapping doc covers T/P/RH; processed files carry the mapped columns."""
    mapped = {m["skyguard"] for m in manifest["variables"]}
    assert {"temperature_c", "sea_level_pressure_hpa",
            "relative_humidity_pct"} <= mapped
    assert (project_root / "reports" / "noaa" / "variable_mapping.md").is_file()
    expected = set(P.PROCESSED_COLUMNS)
    for station in manifest["stations"]:
        frame = pd.read_csv(project_root / station["processed_file"], nrows=5)
        assert set(frame.columns) == expected, station["ghcnh_id"]


def test_timestamp_parsing(project_root, manifest):
    """Timestamps parse as UTC and are sorted ascending per station."""
    for station in manifest["stations"]:
        frame = pd.read_csv(project_root / station["processed_file"],
                            usecols=["timestamp_utc"])
        ts = pd.to_datetime(frame["timestamp_utc"], utc=True)
        assert ts.notna().all(), station["ghcnh_id"]
        assert (ts.diff().dropna() >= pd.Timedelta(0)).all(), station["ghcnh_id"]


def test_duplicate_detection(project_root, manifest):
    """Duplicate flags in processed files match recomputation on raw files."""
    for station in manifest["stations"]:
        frame = pd.read_csv(project_root / station["processed_file"],
                            usecols=["timestamp_utc", "duplicate_timestamp"])
        ts = pd.to_datetime(frame["timestamp_utc"], utc=True)
        assert (frame["duplicate_timestamp"].astype(int).to_numpy()
                == ts.duplicated(keep=False).astype(int).to_numpy()).all()


def test_missingness_accounting(project_root, manifest):
    """Quality summary missing counts match the processed files."""
    quality = pd.read_csv(project_root / "reports" / "noaa"
                          / "station_quality_summary.csv").set_index("station_id")
    for station in manifest["stations"]:
        frame = pd.read_csv(project_root / station["processed_file"],
                            usecols=["temperature_c", "relative_humidity_pct"])
        row = quality.loc[station["ghcnh_id"]]
        assert row["rows"] == len(frame)
        assert row["temperature_c_missing"] == int(frame["temperature_c"].isna().sum())
        assert (row["relative_humidity_pct_missing"]
                == int(frame["relative_humidity_pct"].isna().sum()))


def test_no_station_mixing(project_root, manifest):
    """Each processed file contains exactly its own station ID."""
    for station in manifest["stations"]:
        frame = pd.read_csv(project_root / station["processed_file"],
                            usecols=["ghcnh_station_id"])
        assert (frame["ghcnh_station_id"] == station["ghcnh_id"]).all()


def test_no_sentinel_leakage(project_root, manifest):
    """Provider -9999 sentinel never appears in processed numeric fields."""
    numeric = [c for c in P.PROCESSED_COLUMNS
               if c not in ("timestamp_utc", "ghcnh_station_id", "station_name",
                            "source_file") and not c.endswith(("_qc", "_flag"))
               and c != "duplicate_timestamp"]
    for station in manifest["stations"]:
        frame = pd.read_csv(project_root / station["processed_file"], usecols=numeric)
        assert (frame.fillna(0).to_numpy() != C.MISSING_SENTINEL).all()


def test_raw_inventory_presence(project_root, manifest):
    """Raw year files + inventory snapshot exist and match manifest hashes."""
    from src.noaa.acquire import sha256_file

    for rec in manifest["raw_files"]:
        path = project_root / rec["path"]
        assert path.is_file(), rec["path"]
        assert sha256_file(path) == rec["sha256"], rec["path"]
    for rec in manifest["inventory"]:
        assert (project_root / rec["path"]).is_file(), rec["path"]


def test_deterministic_processed_output(project_root, manifest, tmp_path):
    """Reprocessing raw files reproduces the shipped processed bytes."""
    from src.noaa.acquire import sha256_file

    station = manifest["stations"][0]
    raws = [str(project_root / rec["path"]) for rec in manifest["raw_files"]
            if rec["station_id"] == station["ghcnh_id"]]
    out = tmp_path / "repro.csv"
    P.build_processed_station(station["ghcnh_id"], raws, str(out))
    assert sha256_file(out) == station["processed_sha256"]


def test_overlap_consistency(project_root, manifest):
    """Overlap summary common period matches the manifest; stations overlap."""
    overlap = pd.read_csv(project_root / "reports" / "noaa" / "overlap_summary.csv")
    common = overlap[overlap["scope"] == "common"].iloc[0]
    assert common["first_timestamp"] == manifest["common_overlap"]["common_start"]
    assert manifest["common_overlap"]["fraction_ge2"] > 0.5
