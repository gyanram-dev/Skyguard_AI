"""Phase 21B reproducibility: manifest, dependencies, startup validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_dependency_manifest_pinned():
    req = Path("requirements.txt").read_text(encoding="utf-8")
    for package in ("fastapi==", "uvicorn==", "pandas==", "numpy==",
                    "scikit-learn==", "tensorflow-cpu==", "shap==",
                    "joblib==", "pydantic==", "pytest=="):
        assert package in req, package


def test_artifact_manifest_content():
    manifest = json.loads(
        Path("reports/phase21b_go1_artifact_manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]
    from src.api.dependencies import REQUIRED_FILES

    covered = {e["path"] for e in manifest["artifacts"]}
    for rel in REQUIRED_FILES:
        assert rel in covered, rel
    for entry in manifest["artifacts"]:
        assert len(entry["sha256"]) == 64
        assert entry["purpose"]
        assert entry["version"]


def test_startup_fails_fast_with_exact_causes(tmp_path):
    from src.api.dependencies import DataStore

    with pytest.raises(RuntimeError, match="Missing required artifacts"):
        DataStore.load(tmp_path)
