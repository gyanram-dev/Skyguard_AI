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
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
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

# Year-first formats are order-unambiguous, so a column may mix them
# (naive, Z-suffixed, offset) safely. Day/month-ambiguous slash formats
# keep the strict single-format rule below.
ISO_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
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

# Station-identity column candidates for multi-station uploads. A detected
# station column partitions the upload; without one, all rows form a
# single station group (the Phase 20 single-station contract).
STATION_CANDIDATES = ["station_id", "station", "site_id", "site", "location",
                      "location_id", "name"]

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
    station_col = _detect_station_column(columns)
    detected: list[str] = []
    if station_col is not None:
        labels = frame[station_col].astype(str).str.strip()
        labels = labels[~labels.str.lower().isin(["", "nan"])]
        seen: list[str] = []
        for value in labels.tolist():
            key = str(value)[:80]
            if key not in seen:
                seen.append(key)
            if len(seen) >= 50:
                break
        detected = seen
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
            "warnings": warnings, "stations_detected": detected}


def _parse_timestamps(values: pd.Series) -> tuple[pd.Series, str]:
    """Parse timestamps deterministically; refuse ambiguous orders."""
    texts = values.astype(str).str.strip()
    iso_parsed = pd.Series(pd.NaT, index=texts.index)
    iso_used: set[str] = set()
    for fmt in ISO_FORMATS:
        missing = iso_parsed.isna()
        if not bool(missing.any()):
            break
        attempt = pd.to_datetime(texts[missing], format=fmt, errors="coerce")
        hit = attempt.notna()
        if bool(hit.any()):
            iso_used.add(fmt)
            iso_parsed.loc[attempt[hit].index] = attempt[hit].values
    if bool((~iso_parsed.isna()).all()):
        label = next(iter(iso_used)) if len(iso_used) == 1 else "ISO-8601 (mixed)"
        return iso_parsed, label
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


def _detect_station_column(columns: list[str]) -> str | None:
    """Station-identity column for multi-station uploads (None = single)."""
    normed = {_norm_name(c): c for c in columns}
    for candidate in STATION_CANDIDATES:
        if _norm_name(candidate) in normed:
            return normed[_norm_name(candidate)]
    return None


def _normalize_station(values: pd.DataFrame, stamps: pd.Series
                       ) -> tuple[pd.DataFrame, float, int]:
    """Chronological normalization for one station group.

    Sort ascending by timestamp (original position breaks ties
    deterministically). Rows with unparseable timestamps cannot be placed
    in time: they are excluded here and counted (reported as invalid),
    never silently repaired. Returns (sorted frame, cadence minutes,
    invalid-timestamp count). Cadence comes from sorted positive diffs
    only, so duplicate zero-duration diffs and physical CSV order cannot
    distort it.
    """
    valid = stamps.notna()
    invalid_count = int((~valid).sum())
    values = values.loc[valid].reset_index(drop=True)
    stamps = stamps.loc[valid].reset_index(drop=True)
    order = np.lexsort((values["_pos"].to_numpy(), stamps.to_numpy()))
    ordered = values.iloc[order].reset_index(drop=True)
    sorted_ts = stamps.iloc[order].reset_index(drop=True)
    # Timezone offsets are dropped after parsing; wall-clock time is kept
    # exactly (no silent conversion), so stored instants match the upload.
    ordered = ordered.assign(timestamp=sorted_ts.dt.strftime("%Y-%m-%d %H:%M:%S").values)
    diffs = sorted_ts.diff().dt.total_seconds().div(60.0)
    positive = diffs[diffs > 0].dropna()
    if len(positive) == 0:
        raise UploadError(422, "insufficient_data",
                         "Timestamps do not advance; temporal context unavailable.")
    return ordered, round(float(positive.median()), 3), invalid_count


def confirm_session(session_id: str, mapping: dict, units: dict,
                    station_label: str | None) -> dict:
    """Validate mapping/units and store normalized per-station frames.

    Pipeline: schema mapping -> timestamp parsing/validation -> station
    identification -> chronological normalization per station -> duplicate
    detection (DQ) -> cadence inference (sorted) -> gap detection (DQ) ->
    DQ validation -> feature construction -> analysis. Nothing temporal is
    ever computed from the physical CSV row order.
    """
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
    if int(stamps.notna().sum()) < 3:
        raise UploadError(422, "insufficient_data",
                         "At least 3 valid timestamps are required for temporal context.")
    temp = _to_numeric(raw[normalized_cols["temperature"]])
    if temp_unit == "F":
        temp = (temp - 32.0) * 5.0 / 9.0
    hum = _to_numeric(raw[normalized_cols["humidity"]]) \
        if normalized_cols["humidity"] else pd.Series(np.nan, index=raw.index)
    pres = _to_numeric(raw[normalized_cols["pressure"]]) \
        if normalized_cols["pressure"] else pd.Series(np.nan, index=raw.index)
    if pres_unit == "Pa":
        pres = pres / 100.0
    values = pd.DataFrame({
        "temperature_c": temp.values,
        "pressure_hpa": pres.values,
        "relative_humidity_pct": hum.values,
        "_pos": np.arange(len(raw)),
    })
    station_col = _detect_station_column(columns)
    groups: dict[str, pd.DataFrame] = {}
    if station_col is None:
        groups["__single__"] = values.assign(_station="")
    else:
        labels = raw[station_col].astype(str).str.strip()
        labels = labels.mask(labels.str.lower().isin(["", "nan"]), "")
        for sid, idx in labels.groupby(labels).groups.items():
            key = str(sid)[:80] if str(sid) else "__single__"
            groups[key] = values.loc[list(idx)].assign(_station=key)
    stations: dict[str, dict] = {}
    for sid, group in groups.items():
        part, cadence, invalid = _normalize_station(group, stamps.loc[group.index])
        part = part.drop(columns=["_pos"])
        if int(stamps.loc[group.index].notna().sum()) < 3:
            raise UploadError(422, "insufficient_data",
                             f"Station '{sid}': at least 3 valid timestamps required.")
        frame = pd.DataFrame({
            "timestamp": part["timestamp"].values,
            "temperature_c": part["temperature_c"].values,
            "pressure_hpa": part["pressure_hpa"].values,
            "relative_humidity_pct": part["relative_humidity_pct"].values,
            "source_dataset": "upload",
        })
        stations[sid] = {"frame": frame, "cadence_min": cadence,
                         "rows": int(len(frame)), "invalid_timestamps": invalid}
    multi = station_col is not None and len(stations) > 1
    if station_label and str(station_label).strip() and not multi:
        label = str(station_label).strip()[:80]
    elif multi:
        ids = sorted(stations)
        shown = ", ".join(ids[:5])
        label = f"{len(ids)} stations: {shown}" + ("..." if len(ids) > 5 else "")
    elif station_col is not None:
        only = next(iter(stations))
        label = only if only != "__single__" else "New Uploaded Station"
    else:
        label = "New Uploaded Station"
    total_rows = sum(s["rows"] for s in stations.values())
    with _SESSION_LOCK:
        session["mapping"] = normalized_cols
        session["units"] = {"temperature": temp_unit, "pressure": pres_unit}
        session["station_column"] = station_col
        session["station_label"] = label
        session["timestamp_format"] = ts_format
        session["stations"] = stations
        session["normalized"] = None
        session["cadence_min"] = None
        session["analysis"] = None
    first_cadence = next(iter(stations.values()))["cadence_min"]
    return {"session_id": session_id, "station_label": label,
            "rows": int(total_rows), "cadence_min": first_cadence,
            "timestamp_format": ts_format,
            "fields": {k: v for k, v in normalized_cols.items()}}
