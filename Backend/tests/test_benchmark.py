"""Phase 5 controlled fault-injection benchmark tests.

No model is trained or evaluated here. No detection metrics are
asserted. Tests verify injection correctness, range discipline
(train/ID vs disjoint OOD), non-overlap, label alignment,
reproducibility, and upstream immutability.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.benchmark import config as C

DATASETS = ("jena", "delhi")
SPLITS = ("train", "test_in_distribution", "test_generalization")


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(".").resolve()


@pytest.fixture(scope="module")
def manifest(project_root) -> dict:
    with open(project_root / "data" / "benchmark" / "manifests" / "benchmark_manifest.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def event_labels(project_root) -> dict[str, pd.DataFrame]:
    return {ds: pd.read_csv(project_root / "data" / "benchmark" / "labels" / f"{ds}_event_labels.csv")
            for ds in DATASETS}


@pytest.fixture(scope="module")
def sources(project_root) -> dict[str, pd.DataFrame]:
    return {ds: pd.read_csv(project_root / "data" / "processed" / f"{ds}_clean.csv",
                            usecols=["timestamp", "temperature_c", "pressure_hpa",
                                     "relative_humidity_pct"]) for ds in DATASETS}


@pytest.fixture(scope="module")
def bench_frames(project_root) -> dict[tuple[str, str], pd.DataFrame]:
    out = {}
    for ds in DATASETS:
        for sp in SPLITS:
            out[(ds, sp)] = pd.read_csv(
                project_root / "data" / "benchmark" / ds / f"{sp}.csv")
    return out


@pytest.fixture(scope="module")
def injected_values(project_root) -> dict[str, pd.DataFrame]:
    return {ds: pd.read_csv(project_root / "data" / "benchmark" / "ground_truth" / f"{ds}_injected_values.csv")
            for ds in DATASETS}


def _sensor_events(ev: pd.DataFrame) -> pd.DataFrame:
    return ev[ev["fault_type"] != "COMMUNICATION_GAP"]


# 1. Source processed datasets unchanged.
def test_1_source_processed_unchanged(sources):
    assert len(sources["jena"]) == 420224
    assert len(sources["delhi"]) == 289728
    assert list(sources["jena"].columns) == ["timestamp", "temperature_c", "pressure_hpa",
                                             "relative_humidity_pct"]


# 2. Benchmark generation deterministic (two full runs, identical artifacts).
def test_2_generation_deterministic(project_root, tmp_path):
    from src.benchmark.run import run_benchmark_pipeline, snapshot_hashes

    before = snapshot_hashes(project_root)
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    run_benchmark_pipeline(project_root=project_root, output_root=out_a, seed=26073)
    run_benchmark_pipeline(project_root=project_root, output_root=out_b, seed=26073)

    def _hashes(root: Path) -> dict:
        import hashlib
        out = {}
        for p in sorted((root / "data" / "benchmark").rglob("*.csv")) + \
                 sorted((root / "data" / "benchmark" / "manifests").glob("*.json")) + \
                 sorted((root / "reports" / "benchmark").glob("*.md")):
            with open(p, "rb") as f:
                content = f.read()
            if p.suffix == ".md":
                # Execution-time provenance line is run-specific by nature;
                # normalize it out so data determinism is what is compared.
                lines = [ln for ln in content.decode("utf-8").splitlines()
                         if "executed in ~" not in ln]
                content = "\n".join(lines).encode("utf-8")
            h = hashlib.sha256()
            h.update(content)
            out[str(p.relative_to(root))] = h.hexdigest()
        return out

    assert _hashes(out_a) == _hashes(out_b)
    assert snapshot_hashes(project_root) == before  # temp runs touch nothing upstream


# 3. Train/ID use training parameter ranges only.
def test_3_train_id_use_training_ranges(event_labels):
    for ds in DATASETS:
        ev = event_labels[ds]
        sub = _sensor_events(ev[ev["split"] != "test_generalization"])
        for _, r in sub.iterrows():
            if r["fault_type"] == "SPIKE":
                lo, hi = C.SPIKE_AMPLITUDE[r["target_variable"]]["train_id"]
                assert lo <= abs(float(r["amplitude"])) <= hi, r["injection_id"]
            elif r["fault_type"] == "FROZEN":
                lo, hi = C.FROZEN_DURATION["train_id"]
                assert lo <= int(r["duration_rows"]) <= hi, r["injection_id"]
            elif r["fault_type"] == "DRIFT":
                lo, hi = C.DRIFT_RATE_PER_HOUR[r["target_variable"]]["train_id"]
                assert lo <= abs(float(r["drift_rate_per_hour"])) <= hi, r["injection_id"]
            elif r["fault_type"] == "CROSS_VARIABLE":
                lo, hi = C.CROSS_DURATION["train_id"]
                assert lo <= int(r["duration_rows"]) <= hi, r["injection_id"]


# 4. OOD does not overlap training parameter ranges.
def test_4_ood_disjoint_from_training(event_labels):
    for ds in DATASETS:
        ev = event_labels[ds]
        sub = _sensor_events(ev[ev["split"] == "test_generalization"])
        assert len(sub) > 0
        for _, r in sub.iterrows():
            if r["fault_type"] == "SPIKE" and r["target_variable"] == "temperature_c":
                tlo, thi = C.SPIKE_AMPLITUDE["temperature_c"]["train_id"]
                assert not (tlo <= abs(float(r["amplitude"])) <= thi), r["injection_id"]
                olo, ohi = C.SPIKE_AMPLITUDE["temperature_c"]["ood"]
                assert olo <= abs(float(r["amplitude"])) <= ohi, r["injection_id"]
            elif r["fault_type"] == "FROZEN":
                tlo, thi = C.FROZEN_DURATION["train_id"]
                assert not (tlo <= int(r["duration_rows"]) <= thi), r["injection_id"]
            elif r["fault_type"] == "DRIFT":
                tlo, thi = C.DRIFT_RATE_PER_HOUR[r["target_variable"]]["train_id"]
                assert not (tlo <= abs(float(r["drift_rate_per_hour"])) <= thi), r["injection_id"]
            elif r["fault_type"] == "CROSS_VARIABLE":
                tlo, thi = C.CROSS_DURATION["train_id"]
                assert not (tlo <= int(r["duration_rows"]) <= thi), r["injection_id"]


def _bench_value(bench_frames, ds, ts: str, var: str) -> float:
    for sp in SPLITS:
        sub = bench_frames[(ds, sp)]
        hit = sub[sub["timestamp"] == ts]
        if len(hit):
            return float(hit[var].iloc[0])
    raise KeyError(f"timestamp {ts} absent (gap row?)")


def _source_value(sources, ds, ts: str, var: str) -> float:
    hit = sources[ds][sources[ds]["timestamp"] == ts]
    assert len(hit) == 1
    return float(hit[var].iloc[0])


# 5. Spike changes only the intended target variable.
def test_5_spike_only_target_changed(event_labels, sources, bench_frames, injected_values):
    for ds in DATASETS:
        spikes = event_labels[ds][event_labels[ds]["fault_type"] == "SPIKE"]
        assert len(spikes) > 0
        for _, r in spikes.iterrows():
            vals = injected_values[ds][injected_values[ds]["injection_id"] == r["injection_id"]]
            assert set(vals["target_variable"].unique()) == {r["target_variable"]}
            for _, v in vals.iterrows():
                diff = v["injected_value"] - v["clean_value"]
                assert abs(diff - float(r["direction"]) * abs(float(r["amplitude"]))) < 1e-6
                assert abs(v["clean_value"] - _source_value(sources, ds, v["timestamp"], v["target_variable"])) < 1e-9
                assert abs(v["injected_value"] - _bench_value(bench_frames, ds, v["timestamp"], v["target_variable"])) < 1e-9
            # Non-target variables untouched across the event window.
            others = [c for c in C.CORE_VARS if c != r["target_variable"]]
            for o in others:
                for _, v in vals.iterrows():
                    assert abs(_bench_value(bench_frames, ds, v["timestamp"], o)
                               - _source_value(sources, ds, v["timestamp"], o)) < 1e-9


# 6. Frozen values identical during the run (equal to anchor).
def test_6_frozen_run_identical(event_labels, bench_frames):
    for ds in DATASETS:
        frozen = event_labels[ds][event_labels[ds]["fault_type"] == "FROZEN"]
        assert len(frozen) > 0
        probe = frozen.iloc[::10]  # every 10th keeps suite fast
        for _, r in probe.iterrows():
            frame = pd.concat([bench_frames[(ds, sp)] for sp in SPLITS], ignore_index=True)
            sub = frame[frame["injection_id"] == r["injection_id"]]
            assert len(sub) == int(r["duration_rows"]) == int(r["run_length"])
            assert (sub[r["target_variable"]] == float(r["anchor_value"])).all()


# 7+8. Drift monotonic at the recorded rate.
def test_7_8_drift_monotonic_and_rate(event_labels, injected_values):
    for ds in DATASETS:
        drifts = event_labels[ds][event_labels[ds]["fault_type"].isin(("DRIFT", "SPIKE_PLUS_DRIFT"))]
        assert len(drifts) > 0
        for _, r in drifts.iterrows():
            var = r["target_variable"] if r["fault_type"] == "DRIFT" else r["target_variable"].split("+")[0]
            vals = injected_values[ds][(injected_values[ds]["injection_id"] == r["injection_id"])
                                       & (injected_values[ds]["target_variable"] == var)].copy()
            vals["ts"] = pd.to_datetime(vals["timestamp"])
            vals = vals.sort_values("ts")
            offsets = (vals["injected_value"] - vals["clean_value"]).to_numpy(dtype=float)
            elapsed_h = (vals["ts"] - vals["ts"].iloc[0]).dt.total_seconds().to_numpy(dtype=float) / 3600.0
            direction = int(r["direction"])
            diffs = np.diff(offsets)
            assert ((diffs >= -1e-9).all() if direction > 0 else (diffs <= 1e-9).all()), r["injection_id"]
            expected = float(r["drift_rate_per_hour"]) * direction * elapsed_h
            assert np.allclose(offsets, expected, atol=1e-6), r["injection_id"]


# 9+10. Cross-variable modifies intended variables with correct duration.
def test_9_10_cross_variable_correct(event_labels, injected_values, bench_frames):
    for ds in DATASETS:
        cross = event_labels[ds][event_labels[ds]["fault_type"] == "CROSS_VARIABLE"]
        assert len(cross) > 0
        probe = cross.iloc[::6]
        for _, r in probe.iterrows():
            vals = injected_values[ds][injected_values[ds]["injection_id"] == r["injection_id"]]
            assert set(vals["target_variable"].unique()) == set(C.CORE_VARS)
            rates = eval(r["rates_per_reading"]) if isinstance(r["rates_per_reading"], str) else r["rates_per_reading"]
            for var in C.CORE_VARS:
                sub = vals[vals["target_variable"] == var].copy()
                assert len(sub) == int(r["duration_rows"])
                steps = np.arange(1, len(sub) + 1)
                sub = sub.sort_values("timestamp")
                assert np.allclose((sub["injected_value"] - sub["clean_value"]).to_numpy(dtype=float),
                                   float(rates[var]) * steps, atol=1e-6)


# 11+12. Humidity bounds, no clipping (exact recorded offsets everywhere).
def test_11_12_humidity_valid_unclipped(bench_frames, injected_values):
    for ds in DATASETS:
        for sp in SPLITS:
            rh = pd.to_numeric(bench_frames[(ds, sp)]["relative_humidity_pct"], errors="coerce").dropna()
            assert ((rh >= 0.0) & (rh <= 100.0)).all()
        hum = injected_values[ds][injected_values[ds]["target_variable"] == "relative_humidity_pct"]
        assert len(hum) > 0
        assert ((hum["injected_value"] >= 0.0) & (hum["injected_value"] <= 100.0)).all()


# 13. No interpolation: source missing stays missing; clean values untouched.
def test_13_no_interpolation(sources, bench_frames):
    for ds in DATASETS:
        src = sources[ds]
        bench = pd.concat([bench_frames[(ds, sp)] for sp in SPLITS], ignore_index=True)
        for var in C.CORE_VARS:
            src_nan_ts = set(src[src[var].isna()]["timestamp"])
            bench_nan_ts = set(bench[bench[var].isna()]["timestamp"])
            assert src_nan_ts <= bench_nan_ts  # missing never filled
        clean = bench[bench["ground_truth_anomaly"] == 0]
        merged = clean.merge(src, on="timestamp", suffixes=("", "_src"))
        for var in C.CORE_VARS:
            a = pd.to_numeric(merged[var], errors="coerce")
            b = pd.to_numeric(merged[f"{var}_src"], errors="coerce")
            assert (a.isna() == b.isna()).all()
            assert np.allclose(a.dropna().to_numpy(dtype=float), b.dropna().to_numpy(dtype=float))


# 14+15. Gap rows genuinely removed; manifest counts exact.
def test_14_15_gap_rows_absent_and_counted(event_labels, bench_frames, sources):
    for ds in DATASETS:
        gaps = event_labels[ds][event_labels[ds]["fault_type"] == "COMMUNICATION_GAP"]
        assert len(gaps) == 60, f"{ds} gaps"
        bench = pd.concat([bench_frames[(ds, sp)] for sp in SPLITS], ignore_index=True)
        bench_ts = set(bench["timestamp"])
        for _, g in gaps.iterrows():
            src = sources[ds]
            i0 = src.index[src["timestamp"] == g["start_timestamp"]].tolist()
            assert len(i0) == 1
            span = src["timestamp"].iloc[i0[0]: i0[0] + int(g["removed_row_count"])].tolist()
            assert span[-1] == g["end_timestamp"]
            assert len(set(span) & bench_ts) == 0
            assert int(g["removed_row_count"]) == len(span)


# 16. No event overlaps natural missing/gap periods.
def test_16_no_injection_on_natural_missing(event_labels, sources):
    for ds in DATASETS:
        src = sources[ds]
        present = src[list(C.CORE_VARS)].notna().all(axis=1)
        for _, r in event_labels[ds].iterrows():
            i0 = src.index[src["timestamp"] == r["start_timestamp"]].tolist()[0]
            window = present.iloc[i0: i0 + int(r["duration_rows"] if r["fault_type"] != "COMMUNICATION_GAP" else r["removed_row_count"])]
            assert bool(window.all()), r["injection_id"]


# 17. Events do not overlap (combinations are single recorded spans).
def test_17_events_do_not_overlap(event_labels):
    for ds in DATASETS:
        ev = event_labels[ds].sort_values("start_timestamp").reset_index(drop=True)
        starts = pd.to_datetime(ev["start_timestamp"])
        ends = pd.to_datetime(ev["end_timestamp"])
        assert bool((starts.iloc[1:].values > ends.iloc[:-1].values).all())


# 18. Row labels align with injected timestamps.
def test_18_row_labels_align(project_root, event_labels):
    for ds in DATASETS:
        rows = pd.read_csv(project_root / "data" / "benchmark" / "labels" / f"{ds}_row_labels.csv",
                           usecols=["timestamp", "ground_truth_anomaly", "ground_truth_fault_type", "injection_id"])
        faults = event_labels[ds][event_labels[ds]["fault_type"] != "COMMUNICATION_GAP"]
        flagged = rows[rows["ground_truth_anomaly"] == 1]
        assert len(flagged) == sum(int(r["duration_rows"]) for _, r in faults.iterrows())
        assert set(flagged["injection_id"].unique()) == set(faults["injection_id"].unique())
        assert set(flagged["ground_truth_fault_type"].unique()) <= set(C.FAULT_TYPES)


# 19+20. Clean values match source; injected values match benchmark.
def test_19_20_ground_truth_values_match(event_labels, sources, bench_frames, injected_values):
    for ds in DATASETS:
        faults = event_labels[ds][event_labels[ds]["fault_type"] != "COMMUNICATION_GAP"]
        probe_ids = faults["injection_id"].iloc[::12].tolist()
        probe = injected_values[ds][injected_values[ds]["injection_id"].isin(probe_ids)]
        assert len(probe) > 0
        for _, v in probe.iterrows():
            assert abs(v["clean_value"] - _source_value(sources, ds, v["timestamp"], v["target_variable"])) < 1e-9
            assert abs(v["injected_value"] - _bench_value(bench_frames, ds, v["timestamp"], v["target_variable"])) < 1e-9


# 21. OOD includes unseen combinations.
def test_21_ood_unseen_combination(event_labels):
    for ds in DATASETS:
        ev = event_labels[ds]
        combos = ev[ev["fault_type"] == "SPIKE_PLUS_DRIFT"]
        assert len(combos) == 20, f"{ds} combos"
        assert (combos["split"] == "test_generalization").all()
        assert (ev[ev["split"] != "test_generalization"]["fault_type"] != "SPIKE_PLUS_DRIFT").all()


# Split leakage: disjoint timestamps, no boundary crossing.
def test_split_leakage(bench_frames, manifest):
    for ds in DATASETS:
        seen: set = set()
        for sp in SPLITS:
            ts = set(bench_frames[(ds, sp)]["timestamp"])
            assert len(ts & seen) == 0, f"{ds} {sp} timestamp overlap"
            seen |= ts
        for s in manifest["datasets"][ds]["splits"]:
            assert s["rows"] > 0


# 22. No Phase 1-4 dataset changed.
def test_22_upstream_unchanged(project_root):
    assert len(pd.read_csv(project_root / "data" / "features" / "jena_features.csv", usecols=["timestamp"])) == 420224
    assert len(pd.read_csv(project_root / "data" / "features" / "delhi_features.csv", usecols=["timestamp"])) == 289728
    assert len(pd.read_csv(project_root / "data" / "features" / "jena_features.csv", nrows=0).columns) == 106
    assert len(pd.read_csv(project_root / "data" / "quality" / "jena_quality.csv", usecols=["timestamp"])) == 420224
    assert len(pd.read_csv(project_root / "data" / "baseline" / "delhi_statistical_baseline.csv", usecols=["timestamp"])) == 289728


# 23. No future phase implemented.
def test_23_no_future_phase(project_root):
    src = project_root / "src"
    existing = {p.name for p in src.iterdir() if p.is_dir() and not p.name.startswith("__")}
    # Allowlist amended in Phase 6 (evaluation), Phase 7 (isolation_forest),
    # Phase 8A (noaa acquisition/audit), Phase 8B (spatial evidence),
    # Phase 9 (lstm_autoencoder), Phase 10 (ensemble), Phase 11
    # (root_cause), Phase 12 (api) and Phase 21A (data_sources: official
    # IMD WIS2 ingestion boundary, no models): each addition is a mandated
    # single-purpose package. Intent unchanged. TensorFlow is allowed
    # ONLY inside src/lstm_autoencoder (Phase 9 mandate); the import scans
    # below are unchanged and still forbid it in benchmark/evaluation/
    # isolation_forest.
    assert existing <= {"data", "preprocessing", "features", "data_quality", "baseline",
                        "benchmark", "evaluation", "isolation_forest", "noaa",
                        "spatial", "lstm_autoencoder", "ensemble",
                        "root_cause", "api", "data_sources"}, existing
    forbidden = ("sklearn", "tensorflow", "torch", "fastapi", "shap", "xgboost")
    import re

    import_pat = re.compile(r"^\s*(import|from)\s+([a-z0-9_\.]+)", re.MULTILINE)
    for pkg in ("benchmark", "evaluation", "isolation_forest"):
        for py in (src / pkg).rglob("*.py"):
            mods = import_pat.findall(py.read_text(encoding="utf-8").lower())
            top = {m.split(".")[0] for _, m in mods}
            assert not ((set(forbidden) - {"sklearn"}) & top), py.name
    # sklearn is allowed ONLY inside src/isolation_forest (Phase 7 mandate).
    # Nothing else ML/serving-related may appear anywhere.
    for pkg in ("benchmark", "evaluation", "isolation_forest"):
        for py in (src / pkg).rglob("*.py"):
            mods = import_pat.findall(py.read_text(encoding="utf-8").lower())
            top = {m.split(".")[0] for _, m in mods}
            assert not ({"tensorflow", "torch", "fastapi"} & top), py.name
    for pkg in ("benchmark", "evaluation"):
        for py in (src / pkg).rglob("*.py"):
            mods = import_pat.findall(py.read_text(encoding="utf-8").lower())
            top = {m.split(".")[0] for _, m in mods}
            assert "sklearn" not in top, py.name
