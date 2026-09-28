"""CSV upload sessions: parsing, column mapping, units, normalization.

Bounded in-memory sessions (server-generated IDs only): each upload is
size/shape-capped before parsing, and sessions are LRU-evicted past the
cap. Uploaded content is data only — never executed, never used for
paths or commands. Inference over normalized frames lives in
upload_analysis.py.
"""

from __future__ import annotations

import io
import logging
import math
import re
import threading
import uuid

import numpy as np
import pandas as pd

logger = logging.getLogger("skyguard.upload")

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 200_000
MAX_COLS = 50
MAX_CELL_CHARS = 10_000
MAX_SESSIONS = 50

TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
]

FIELD_CANDIDATES = {
    "timestamp": ["timestamp", "datetime", "date_time", "date", "time"],
    "temperature": ["temperature", "temperature_c", "temp", "temp_c", "air_temp",
                    "airtemp", "air_temperature", "t", "t_c", "temp_f", "temperature_f"],
    "humidity": ["humidity", "relative_humidity", "rel_hum", "rh", "rh_percent",
                 "rh_pct", "humidity_pct", "humidity_rh"],
    "pressure": ["pressure", "pressure_hpa", "pres", "atm_pres", "atmospheric_pressure",
                 "station_pressure", "air_pressure", "p", "pressure_pa", "pres_pa"],
}

REQUIRED_FIELDS = ("timestamp", "temperature")
OPTIONAL_FIELDS = ("humidity", "pressure")

TEMP_UNITS = ("C", "F")
PRESSURE_UNITS = ("hPa", "Pa")


class UploadError(Exception):
    """Structured upload failure (status_code, code, detail)."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


_SESSIONS: dict[str, dict] = {}
_SESSION_LOCK = threading.Lock()


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", str(name).lower()) if t]


def _evict_if_needed() -> None:
    while len(_SESSIONS) >= MAX_SESSIONS:
        oldest = min(_SESSIONS, key=lambda k: _SESSIONS[k]["created"])
        del _SESSIONS[oldest]


def get_session(session_id: str) -> dict:
    """Fetch a session or raise a structured 404 (no path handling)."""
    if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-f]{32}", session_id):
        raise UploadError(404, "session_not_found", "Unknown analysis session.")
    with _SESSION_LOCK:
        session = _SESSIONS.get(session_id)
    if session is None:
        raise UploadError(404, "session_not_found", "Unknown analysis session.")
    return session


def _parse_csv(filename: str, content: bytes) -> tuple[pd.DataFrame, list[str]]:
    """Decode and read a CSV within hard limits (structured errors only)."""
    if not str(filename).lower().endswith(".csv"):
        raise UploadError(422, "invalid_file", "Only .csv files are accepted.")
    if len(content) == 0:
        raise UploadError(422, "invalid_file", "The uploaded file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise UploadError(413, "file_too_large",
                         f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UploadError(422, "invalid_file",
                         "File is not valid UTF-8 text. Re-save with UTF-8 encoding.") from None
    try:
        frame = pd.read_csv(io.StringIO(text))
    except Exception:
        raise UploadError(422, "invalid_file",
                         "File could not be parsed as CSV.") from None
    if len(frame) == 0:
        raise UploadError(422, "invalid_file", "CSV contains no data rows.")
    if len(frame) > MAX_ROWS:
        raise UploadError(413, "too_many_rows",
                         f"CSV exceeds the {MAX_ROWS:,} row limit.")
    if len(frame.columns) > MAX_COLS:
        raise UploadError(413, "too_many_columns",
                         f"CSV exceeds the {MAX_COLS} column limit.")
    warnings: list[str] = []
    for col in frame.columns:
        if len(str(col)) > 200:
            raise UploadError(422, "invalid_file", "CSV has an overlong column name.")
    for col in frame.select_dtypes(include=["object"]).columns:
        try:
            longest = int(frame[col].astype(str).str.len().max())
        except (TypeError, ValueError):
            longest = 0
        if longest > MAX_CELL_CHARS:
            raise UploadError(422, "invalid_file",
                             f"Column '{col}' has an overlong cell.")
    return frame, warnings


def _match_columns(columns: list[str]) -> dict:
    """Propose CSV column per SkyGuard field (null when ambiguous/absent)."""
    normed = {_norm_name(c): c for c in columns}
    proposal = {}
    for field, candidates in FIELD_CANDIDATES.items():
        wanted = {_norm_name(c) for c in candidates}
        hits = [normed[c] for c in wanted if c in normed]
        if len(hits) == 1:
            proposal[field] = {"column": hits[0], "confidence": "high",
                               "alternates": []}
        elif len(hits) > 1:
            proposal[field] = {"column": None, "confidence": "ambiguous",
                               "alternates": sorted(hits)}
        else:
            proposal[field] = {"column": None, "confidence": "absent",
                               "alternates": []}
    return proposal


def _infer_unit(column: str | None, kind: str) -> dict:
    """Unit proposal from column-name hints; 'ask' when not safely known."""
    if not column:
        return {"unit": None, "source": "not_applicable"}
    tokens = _tokens(column)
    if kind == "temperature":
        if any(t in ("f", "fahrenheit", "degf", "tempf") for t in tokens):
            return {"unit": "F", "source": "inferred"}
        if any(t in ("c", "celsius", "degc", "tempc") for t in tokens) \
                or str(column).lower().endswith(("_c", "(c)", "[c]")):
            return {"unit": "C", "source": "inferred"}
        return {"unit": None, "source": "ask"}
    if any(t == "pa" for t in tokens) and not any("hpa" in t for t in tokens):
        return {"unit": "Pa", "source": "inferred"}
    if any("hpa" in t for t in tokens):
        return {"unit": "hPa", "source": "inferred"}
    return {"unit": None, "source": "ask"}


def create_session(filename: str, content: bytes) -> dict:
    """Parse an upload and propose mapping/units (no inference yet)."""
    frame, warnings = _parse_csv(filename, content)
    columns = [str(c) for c in frame.columns]
    mapping = _match_columns(columns)
    temp_col = mapping["temperature"]["column"]
    pres_col = mapping["pressure"]["column"]
    units = {"temperature": _infer_unit(temp_col, "temperature"),
             "pressure": _infer_unit(pres_col, "pressure")}
    session_id = uuid.uuid4().hex
    with _SESSION_LOCK:
        _evict_if_needed()
        _SESSIONS[session_id] = {
            "session_id": session_id,
            "filename": str(filename)[:200],
            "size_bytes": len(content),
            "columns": columns,
            "raw": frame,
            "mapping_proposal": mapping,
            "units_proposal": units,
            "warnings": warnings,
            "normalized": None,
            "analysis": None,
        }
    logger.info("Upload session %s: %s (%d rows)", session_id, filename, len(frame))
    return {"session_id": session_id, "filename": str(filename)[:200],
            "size_bytes": len(content), "rows": int(len(frame)),
            "columns": columns, "mapping": mapping, "units": units,
            "warnings": warnings}


def _parse_timestamps(values: pd.Series) -> tuple[pd.Series, str]:
    """Parse timestamps deterministically; refuse ambiguous orders."""
    texts = values.astype(str).str.strip()
    full_hits: dict[str, pd.Series] = {}
    for fmt in TIMESTAMP_FORMATS:
        parsed = pd.to_datetime(texts, format=fmt, errors="coerce")
        if bool((~parsed.isna()).all()):
            full_hits[fmt] = parsed
    if not full_hits:
        raise UploadError(422, "invalid_timestamp",
                         "Timestamps could not be parsed. Use ISO 'YYYY-MM-DD HH:MM:SS'.")
    slash = [f for f in full_hits if "/" in f]
    if len(slash) > 1:
        raise UploadError(422, "ambiguous_timestamp",
                         "Day/month order is ambiguous (D/M vs M/D). "
                         "Re-save timestamps as ISO 'YYYY-MM-DD HH:MM:SS'.")
    fmt = next(iter(full_hits))
    return full_hits[fmt], fmt


def _to_numeric(values: pd.Series) -> pd.Series:
    """Coerce numerics (thousands separators tolerated); garbage -> NaN."""
    text = values.astype(str).str.strip()
    nums = pd.to_numeric(text, errors="coerce")
    missing = nums.isna() & text.str.lower().ne("nan") & (text != "")
    if bool(missing.any()):
        stripped = pd.to_numeric(text.str.replace(",", "", regex=False), errors="coerce")
        nums = nums.fillna(stripped)
    return nums.astype(float)


def confirm_session(session_id: str, mapping: dict, units: dict,
                    station_label: str | None) -> dict:
    """Validate mapping/units and store the normalized canonical frame."""
    session = get_session(session_id)
    columns = session["columns"]
    for field in REQUIRED_FIELDS:
        col = (mapping or {}).get(field)
        if not isinstance(col, str) or col not in columns:
            raise UploadError(422, "mapping_required",
                             f"A CSV column for '{field}' is required.")
    normalized_cols = {}
    for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        col = (mapping or {}).get(field)
        normalized_cols[field] = col if isinstance(col, str) and col in columns else None
    temp_unit = (units or {}).get("temperature")
    pres_unit = (units or {}).get("pressure")
    if temp_unit not in TEMP_UNITS:
        raise UploadError(422, "units_required",
                         "Select the temperature unit (°C or °F).")
    if normalized_cols["pressure"] is not None and pres_unit not in PRESSURE_UNITS:
        raise UploadError(422, "units_required",
                         "Select the pressure unit (hPa or Pa).")
    raw: pd.DataFrame = session["raw"]
    stamps, ts_format = _parse_timestamps(raw[normalized_cols["timestamp"]])
    temp = _to_numeric(raw[normalized_cols["temperature"]])
    if temp_unit == "F":
        temp = (temp - 32.0) * 5.0 / 9.0
    hum = _to_numeric(raw[normalized_cols["humidity"]]) \
        if normalized_cols["humidity"] else pd.Series(np.nan, index=raw.index)
    pres = _to_numeric(raw[normalized_cols["pressure"]]) \
        if normalized_cols["pressure"] else pd.Series(np.nan, index=raw.index)
    if pres_unit == "Pa":
        pres = pres / 100.0
    frame = pd.DataFrame({
        "timestamp": stamps.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "temperature_c": temp.values,
        "pressure_hpa": pres.values,
        "relative_humidity_pct": hum.values,
        "source_dataset": "upload",
    })
    valid_ts = stamps.notna()
    if int(valid_ts.sum()) < 3:
        raise UploadError(422, "insufficient_data",
                         "At least 3 valid timestamps are required for temporal context.")
    diffs = stamps[valid_ts].diff().dt.total_seconds().div(60.0)
    positive = diffs[diffs > 0].dropna()
    if len(positive) == 0:
        raise UploadError(422, "insufficient_data",
                         "Timestamps do not advance; temporal context unavailable.")
    cadence = round(float(positive.median()), 3)
    label = str(station_label).strip()[:80] if station_label else "New Uploaded Station"
    with _SESSION_LOCK:
        session["mapping"] = normalized_cols
        session["units"] = {"temperature": temp_unit, "pressure": pres_unit}
        session["station_label"] = label
        session["timestamp_format"] = ts_format
        session["cadence_min"] = cadence
        session["normalized"] = frame
        session["analysis"] = None
    return {"session_id": session_id, "station_label": label,
            "rows": int(len(frame)), "cadence_min": cadence,
            "timestamp_format": ts_format,
            "fields": {k: v for k, v in normalized_cols.items()}}
