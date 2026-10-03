"""Health reporting over data artifacts and deferred inference artifacts."""

from __future__ import annotations

API_VERSION = "1.0.0-phase12"

# Lazy-load facts reported by the module that owns model loading.
_DEFERRED = "deferred"
_LOADED = "loaded"
_UNAVAILABLE = "unavailable"


def report(store) -> dict:
    """Health payload; every state is measured, never aspirational.

    ``data_status`` is 'available' whenever the datastore (all required data
    artifacts) loaded; a missing datastore never serves health at all (503),
    so 'available' here is factual.

    ``model_status`` distinguishes the three real states of each inference
    family:
      loaded      — usable now: the deterministic statistical rules need no
                    artifact, and the others become 'loaded' once the single
                    lazy owner (src.api.services.scoring) has cached its
                    per-dataset bundle;
      deferred    — artifact present and verified at startup, loads on first
                    inference (startup deliberately does not load models);
      unavailable — a required artifact is missing, or a lazy load failed.

    ``status`` is 'ok' only when every family is loaded, 'ready' while
    families are deferred (nothing is broken, inference loads on demand), and
    'degraded' when any family is unavailable.
    """
    from src.api.dependencies import PIPELINE_DATASETS
    from src.api.services import scoring as SC

    model_status = dict(store.model_status)
    state = SC.load_state()
    failures = state["failures"]
    all_cached = set(state["cached_datasets"]) >= set(PIPELINE_DATASETS)
    for family, family_status in list(model_status.items()):
        if family_status == _UNAVAILABLE or not family_status:
            continue          # missing at startup: already truthful
        if family == "statistical":
            continue          # in-process rules: nothing to load, stays loaded
        if failures:
            model_status[family] = _UNAVAILABLE
        elif all_cached:
            model_status[family] = _LOADED
    values = set(model_status.values())
    if _UNAVAILABLE in values:
        status = "degraded"
    elif values == {_LOADED}:
        status = "ok"
    else:
        status = "ready"
    return {"status": status,
            "service": "skyguard-api",
            "version": API_VERSION,
            "data_mode": "historical_replay",
            "data_status": "available",
            "model_status": model_status}
