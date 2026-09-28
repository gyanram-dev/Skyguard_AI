"""Investigation assembly: evidence, history, diagnosis, explanation."""

from __future__ import annotations

import pandas as pd

from src.api.services import station_service as SS


def build_investigation(store, alert: dict) -> dict:
    """Full evidence bundle for one alert (frozen detector outputs only).

    Every lookup is keyed by (dataset, alert timestamp): the focus row is
    the ensemble row AT the alert time, the history window ends AT the
    alert time, and the diagnosis is the classifier row AT the alert time.
    No injection IDs, fault labels, or event tables enter.
    """
    ds = alert["backend_id"]
    bundle = store.pipeline[ds]
    stamp = str(alert.get("timestamp"))
    ens = bundle["ens"]
    rows = ens[ens["timestamp"].astype(str) == stamp]
    if len(rows) == 0:
        raise KeyError(f"No ensemble row at '{stamp}'")
    focus = rows.iloc[0]
    evidence = [
        {"title": "Statistical evidence",
         "detail": f"max|z|={SS._num(focus['z_raw'])} "
                   f"(calibrated {SS._num(focus['z_cal'])}); IQR flag={focus['iqr_raw']}.",
         "source": "statistical"},
        {"title": "Isolation Forest evidence",
         "detail": f"raw score={SS._num(focus['if_raw'])} "
                   f"(calibrated {SS._num(focus['if_cal'])}).",
         "source": "isolation_forest"},
        {"title": "LSTM reconstruction evidence",
         "detail": f"target MSE={SS._num(focus['lstm_raw'])} "
                   f"(calibrated {SS._num(focus['lstm_cal'])}).",
         "source": "lstm"},
        {"title": "Ensemble decision",
         "detail": f"mean={SS._num(focus['ens_mean'])}, median={SS._num(focus['ens_median'])}; "
                   f"availability={focus['availability']}; quality={focus['data_quality_status']}.",
         "source": "quality"},
    ]
    if ds == "delhi":
        evidence.append({"title": "NOAA spatial context",
                         "detail": _noaa_detail(store, stamp),
                         "source": "spatial"})
    rc = bundle["rc"]
    rc_rows = rc[rc["timestamp"].astype(str) == stamp]
    rc_rows = rc_rows[rc_rows["has_diagnosis"].astype(bool)]
    root_class, confidence, explanation, features = None, None, None, []
    if len(rc_rows):
        best = rc_rows.iloc[0]
        root_class = str(best["predicted_class"])
        confidence = SS._num(best["confidence"])
        explanation = str(best["explanation"]) if str(best["explanation"]) else None
        features = _parse_shap(best.get("shap_top5"))
    history = SS.history_range(
        store, {"backend_station_id": ds, "source_dataset": f"{ds}_clean"},
        "temperature", str(alert.get("timestamp")), 24)
    observations = {"temperature_c": SS._num(focus["temperature_c"]),
                    "relative_humidity_pct": SS._num(focus["relative_humidity_pct"]),
                    "pressure_hpa": SS._num(focus["pressure_hpa"])}
    return {"alert": alert, "observations": observations, "evidence": evidence,
            "history": {"variable": "temperature", "hours": 24, "series": history},
            "root_cause": {"class": root_class, "confidence": confidence},
            "explanation": {"text": explanation, "features": features}}


def _parse_shap(raw) -> list[dict]:
    """Parse stored 'feature=+0.123; ...' strings (empty when absent)."""
    if raw is None or str(raw) == "" or str(raw).lower() == "nan":
        return []
    out = []
    for chunk in str(raw).split(";"):
        chunk = chunk.strip()
        if "=" not in chunk:
            continue
        name, val = chunk.split("=", 1)
        try:
            contribution = float(val)
        except ValueError:
            continue
        out.append({"name": name.strip(), "value": None, "contribution": contribution,
                    "direction": "positive" if contribution >= 0 else "negative"})
    return out


def _noaa_detail(store, stamp: str) -> str:
    """Delhi spatial context sentence (honest about availability)."""
    path = store.root / "reports" / "noaa" / "aws_context_validation.csv"
    if not path.is_file():
        return "NOAA context file unavailable."
    try:
        ist = pd.Timestamp(stamp) + pd.Timedelta(hours=5, minutes=30)
        key = ist.strftime("%Y-%m-%d %H:%M:%S")
        ctx = pd.read_csv(path, usecols=["timestamp_ist", "ctx_temp_difference",
                                         "ctx_temp_station_count"])
        hit = ctx[ctx["timestamp_ist"] == key]
        if not len(hit):
            return "No NOAA observation within the alignment window (context unavailable)."
        row = hit.iloc[0]
        return (f"NOAA Delhi-context median differs by "
                f"{float(row['ctx_temp_difference']):+.2f}C "
                f"({int(row['ctx_temp_station_count'])} stations; contextual only).")
    except (ValueError, KeyError):
        return "NOAA context unavailable for this timestamp."
