"""Historical replay abstraction over frozen datasets.

There is no physical real-time AWS stream yet. HistoricalReplay exposes
the latest available timestamp per source and reads backward from it.
Responses always carry data_mode="historical_replay"; nothing here is
"real-time" or "live". A future streaming adapter can replace this
module without changing API schemas.
"""

from __future__ import annotations

DATA_MODE = "historical_replay"


class HistoricalReplay:
    """Replay source metadata for one backend station."""

    def __init__(self, backend_id: str, latest_timestamp: str, n_observations: int,
                 source: str) -> None:
        self.backend_id = backend_id
        self.latest_timestamp = latest_timestamp
        self.n_observations = n_observations
        self.source = source

    def describe(self) -> dict:
        """Replay cursor description (no live claims)."""
        return {"data_mode": DATA_MODE,
                "backend_station_id": self.backend_id,
                "latest_timestamp": self.latest_timestamp,
                "n_observations": self.n_observations,
                "source": self.source,
                "realtime": False}


def replay_for_pipeline(store, backend_id: str) -> HistoricalReplay:
    """Replay cursor for a Jena/Delhi pipeline station."""
    bundle = store.pipeline[backend_id]
    return HistoricalReplay(backend_id, bundle["latest"], len(bundle["obs"]),
                            f"data/processed/{backend_id}_clean.csv")


def replay_for_noaa(store, backend_id: str) -> HistoricalReplay | None:
    """Replay cursor for a NOAA station (None when unavailable)."""
    obs = store.noaa_obs.get(backend_id)
    if obs is None or len(obs) == 0:
        return None
    return HistoricalReplay(backend_id, str(obs["timestamp_utc"].iloc[-1]), len(obs),
                            f"data/noaa/processed/{backend_id}_2022_2024.csv")
