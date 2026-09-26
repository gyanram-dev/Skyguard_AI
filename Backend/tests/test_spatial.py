"""Phase 8B spatial-consistency tests: geometry, alignment, scoring, guards."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.spatial import neighbors as N
from src.spatial.alignment import TIME_TOLERANCE, align_neighbor
from src.spatial.distance import haversine_km
from src.spatial.reference import neighbor_mad, neighbor_median
from src.spatial.scoring import score_variable

STATIONS = [
    {"ghcnh_id": "A", "lat": 28.0, "lon": 77.0},
    {"ghcnh_id": "B", "lat": 28.5, "lon": 77.5},
    {"ghcnh_id": "C", "lat": 29.0, "lon": 78.0},
    {"ghcnh_id": "D", "lat": 10.0, "lon": 70.0},
]


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(".").resolve()


def test_1_haversine_distance():
    """Known great-circle distances (Delhi-Jaipur ~ 240 km)."""
    assert haversine_km(28.5845, 77.2058, 26.8242, 75.8122) == pytest.approx(239.0, abs=2.0)
    assert haversine_km(0.0, 0.0, 0.0, 0.0) == 0.0
    assert haversine_km(28.0, 77.0, 28.0, 77.0) == 0.0


def test_2_3_4_neighbors_rank_radius_exclusion():
    """Deterministic ranking, radius filtering, target exclusion."""
    pairs = N.pairwise_distances(STATIONS)
    # pairs carry all distances; the radius gate lives in select_neighbors.
    d_row = pairs[(pairs["target_station"] == "A") & (pairs["neighbor_station"] == "D")]
    assert float(d_row["distance_km"].iloc[0]) > 600.0
    sel = N.select_neighbors(pairs, k=2, radius_km=600.0)
    assert "D" not in sel[sel["target_station"] == "A"]["neighbor_station"].tolist()
    got = sel[sel["target_station"] == "A"].sort_values("rank")
    assert got["neighbor_station"].tolist() == ["B", "C"]
    assert (got["rank"].tolist() == [1, 2])
    # Fewer than k within radius: D gets nobody; determinism on repeat.
    assert sel[sel["target_station"] == "D"].empty
    assert N.select_neighbors(pairs, k=2, radius_km=600.0)["distance_km"].equals(
        sel["distance_km"])


def test_5_temporal_tolerance():
    """Nearest within ±30 min matches; outside does not."""
    tgt = pd.Series(pd.to_datetime(["2022-01-01 00:00+00:00"]))
    near = pd.Series(pd.to_datetime(["2022-01-01 00:29+00:00", "2022-01-01 05:00+00:00"]))
    pos = align_neighbor(tgt, near)
    assert int(pos.iloc[0]) == 0
    far = pd.Series(pd.to_datetime(["2022-01-01 00:31+00:00"]))
    assert int(align_neighbor(tgt, far).iloc[0]) == -1
    assert TIME_TOLERANCE == pd.Timedelta(minutes=30)


def test_6_no_interpolation():
    """Alignment returns positions of real rows only (-1 for gaps)."""
    tgt = pd.Series(pd.to_datetime(["2022-01-01 00:00+00:00", "2022-01-01 06:00+00:00"]))
    nbr = pd.Series(pd.to_datetime(["2022-01-01 00:10+00:00"]))
    pos = align_neighbor(tgt, nbr)
    assert int(pos.iloc[0]) == 0 and int(pos.iloc[1]) == -1


def test_7_median_reference():
    """Median (not mean) of available neighbors; NaN when none."""
    assert neighbor_median(np.array([10.0, 11.0, 30.0])) == pytest.approx(11.0)
    assert np.isnan(neighbor_median(np.array([np.nan, np.nan])))


def test_8_mad_scale():
    """MAD dispersion; NaN with fewer than 2 values."""
    assert neighbor_mad(np.array([10.0, 11.0, 30.0])) == pytest.approx(1.0)
    assert np.isnan(neighbor_mad(np.array([10.0])))


def test_9_10_insufficient_and_missing():
    """<2 neighbors -> NaN score; missing target/variable -> UNAVAILABLE."""
    one = score_variable(10.0, np.array([9.0, np.nan]), 3)
    assert np.isnan(one["robust_score"]) and one["context"] == "LOW_CONTEXT"
    assert one["reference"] == pytest.approx(9.0)
    assert score_variable(np.nan, np.array([9.0, 10.0]), 3)["context"] == "UNAVAILABLE"
    assert score_variable(10.0, np.array([np.nan, np.nan]), 3)["context"] == "UNAVAILABLE"


def test_12_confidence_classes():
    """HIGH/MEDIUM/LOW/UNAVAILABLE by observable availability only."""
    assert score_variable(12.0, np.array([10.0, 11.0, 12.0]), 3)["context"] == "HIGH_CONTEXT"
    assert score_variable(12.0, np.array([10.0, 11.0, np.nan]), 3)["context"] == "MEDIUM_CONTEXT"
    assert score_variable(12.0, np.array([10.0, 10.0, 10.0]), 3)["context"] == "LOW_CONTEXT"


def test_11_pressure_basis_separation(project_root):
    """Only altimeter enters the pressure comparison; SLP/station columns absent."""
    frame = pd.read_csv(project_root / "data" / "noaa" / "processed"
                        / "spatial_consistency.csv", nrows=5)
    assert "pres_target" in frame.columns
    assert not any("sea_level" in c or "station_level" in c for c in frame.columns)
    import json

    cfg = json.load(open(project_root / "data" / "noaa" / "metadata"
                         / "spatial_config.json", encoding="utf-8"))
    assert cfg["pressure_basis"] == "altimeter_setting_hpa"


def test_13_reproducibility(project_root):
    """Rebuilt frame for one station matches the shipped artifact exactly."""
    from src.spatial import evaluator as E

    proc = project_root / "data" / "noaa" / "processed"
    shipped = pd.read_csv(proc / "spatial_consistency.csv", usecols=["station_id"])
    sid = shipped["station_id"].iloc[0]
    import json

    sel = pd.read_csv(project_root / "data" / "noaa" / "metadata" / "neighbor_graph.csv")
    nids = sel[(sel["target_station"] == sid) & (sel["selected"])].sort_values("rank")[
        "neighbor_station"].tolist()
    frames = {s: pd.read_csv(proc / f"{s}_2022_2024.csv",
                             usecols=["timestamp_utc", "temperature_c",
                                      "relative_humidity_pct", "altimeter_setting_hpa"])
              for s in [sid] + nids}
    rebuilt = E.build_consistency_frame(sid, frames[sid], frames, nids)
    disk = pd.read_csv(proc / "spatial_consistency.csv")
    disk = disk[disk["station_id"] == sid].reset_index(drop=True)
    pd.testing.assert_frame_equal(disk, rebuilt, check_dtype=False)


def test_14_phases_1_to_7_unchanged(project_root):
    """Frozen earlier-phase invariants still hold after Phase 8B."""
    assert len(pd.read_csv(project_root / "data" / "features" / "jena_features.csv",
                           usecols=["timestamp"])) == 420224
    assert len(pd.read_csv(project_root / "data" / "evaluation" / "statistical_baseline"
                           / "summary_metrics.csv")) > 0
    import json

    cfg = json.load(open(project_root / "reports" / "isolation_forest"
                         / "model_config.json", encoding="utf-8"))
    assert cfg["jena"]["threshold_raw"] == pytest.approx(0.0263, abs=1e-4)
    assert cfg["delhi"]["threshold_raw"] == pytest.approx(0.0356, abs=1e-4)
    from src.baseline.zscore_baseline import Z_THRESHOLD
    from src.baseline.iqr_baseline import IQR_FACTOR
    assert Z_THRESHOLD == 3.0 and IQR_FACTOR == 1.5
