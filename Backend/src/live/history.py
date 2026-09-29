"""Bounded causal station-history buffer for live observations.

Per station: chronological deque of CanonicalObservation. Only rows
available at decision time ever enter; duplicates are acknowledged
without re-inference; late (out-of-order) rows are recorded with an
explicit OUT_OF_ORDER state and never rewrite issued decisions.
Warm-up is explicit: WARMING_UP until enough rows exist for the frozen
statistical horizons, INSUFFICIENT_EVIDENCE below the LSTM lookback.
Missing LSTM history is never manufactured — the LSTM is reported
unavailable instead.
"""

from __future__ import annotations

from collections import deque

import pandas as pd

from src.live import obs as LO

# Warm-up floors (documented conventions, not fitted values).
WARM_ROWS_STATISTICAL = 12  # covers the frozen short horizons
WARM_ROWS_LSTM = 12  # frozen 12-step lookback window
LATE_WINDOW_ROWS = 3  # arrivals older than newest-3 are too late to matter


class StationHistory:
    """Chronological bounded buffer for one live station."""

    def __init__(self, station_id: str, maxlen: int = 500) -> None:
        self.station_id = station_id
        self._rows: deque = deque(maxlen=maxlen)
        self._ids: set[str] = set()

    def add(self, ob: LO.CanonicalObservation) -> str:
        """Insert one observation; return its row-level DQ state."""
        if ob.obs_id in self._ids:
            return LO.DUPLICATE
        if ob.temperature_c is None and ob.pressure_hpa is None \
                and ob.relative_humidity_pct is None:
            self._ids.add(ob.obs_id)
            self._rows.append(ob)
            return LO.MISSING
        if not self._rows:
            self._ids.add(ob.obs_id)
            self._rows.append(ob)
            return LO.VALID
        newest = self._rows[-1].timestamp
        if ob.timestamp <= newest:
            position = len(self._rows) - 1
            while position >= 0 and self._rows[position].timestamp > ob.timestamp:
                position -= 1
            if len(self._rows) - 1 - position > LATE_WINDOW_ROWS:
                self._ids.add(ob.obs_id)
                return LO.OUT_OF_ORDER
            rows = list(self._rows)
            rows.insert(position + 1, ob)
            self._rows = deque(rows[-self._rows.maxlen:], maxlen=self._rows.maxlen)
            self._ids.add(ob.obs_id)
            return LO.OUT_OF_ORDER
        self._ids.add(ob.obs_id)
        self._rows.append(ob)
        return LO.VALID

    def warm_state(self) -> str:
        """WARMING_UP / INSUFFICIENT_EVIDENCE / VALID by buffer depth."""
        n = len(self._rows)
        if n < WARM_ROWS_STATISTICAL:
            return LO.WARMING_UP
        if n < WARM_ROWS_LSTM:
            return LO.INSUFFICIENT_EVIDENCE
        return LO.VALID

    def lstm_available(self) -> bool:
        return len(self._rows) >= WARM_ROWS_LSTM

    def frame(self) -> pd.DataFrame:
        """Chronological sensor frame for the shared feature pipeline."""
        return pd.DataFrame([{
            "timestamp": o.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "temperature_c": o.temperature_c,
            "pressure_hpa": o.pressure_hpa,
            "relative_humidity_pct": o.relative_humidity_pct,
            "source_dataset": "live"} for o in self._rows])

    def latest(self) -> LO.CanonicalObservation | None:
        return self._rows[-1] if self._rows else None

    def __len__(self) -> int:
        return len(self._rows)
