"""Explicit typed response schemas for the versioned API namespace."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelStatus(BaseModel):
    statistical: str
    isolation_forest: str
    lstm_autoencoder: str
    ensemble: str
    root_cause: str


class HealthResponse(BaseModel):
    status: str
    service: str = "skyguard-api"
    version: str
    data_mode: str = "historical_replay"
    model_status: ModelStatus


class StationSummary(BaseModel):
    station_id: str
    city: str
    latitude: float | None
    longitude: float | None
    status: str
    data_available: bool = True
    data_mode: str = "historical_replay"
    temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    anomaly_score: float | None = None
    confidence: float | None = None
    last_updated: str | None = None


class StationListResponse(BaseModel):
    data_mode: str = "historical_replay"
    stations: list[StationSummary]


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class StationInfo(BaseModel):
    station_id: str
    city: str
    coordinates: Coordinates | None = None
    status: str
    data_mode: str = "historical_replay"
    last_updated: str | None = None


class Observations(BaseModel):
    temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    pressure_hpa: float | None = None


class DataQuality(BaseModel):
    status: str
    ml_eligible: bool
    flags: list[str] = Field(default_factory=list)


class Anomaly(BaseModel):
    detected: bool
    score: float | None = None
    method: str
    confidence: float | None = None


class RootCause(BaseModel):
    class_: str | None = Field(default=None, alias="class")
    confidence: float | None = None

    model_config = {"populate_by_name": True}


class SpatialContext(BaseModel):
    available: bool
    neighbor_count: int = 0
    context_level: str = "UNAVAILABLE"


class StationDetailResponse(BaseModel):
    station: StationInfo
    observations: Observations
    data_quality: DataQuality
    anomaly: Anomaly
    root_cause: RootCause
    spatial_context: SpatialContext


class AlertSummary(BaseModel):
    alert_id: str
    station_id: str
    timestamp: str
    status: str
    event: str
    anomaly_score: float | None = None
    root_cause: str | None = None
    root_cause_confidence: float | None = None
    summary: str


class AlertListResponse(BaseModel):
    data_mode: str = "historical_replay"
    alerts: list[AlertSummary]


class EvidenceItem(BaseModel):
    title: str
    detail: str
    source: str


class HistorySeries(BaseModel):
    variable: str
    hours: int
    series: list[dict]


class ExplanationFeature(BaseModel):
    name: str
    value: float | None = None
    contribution: float | None = None
    direction: str


class Explanation(BaseModel):
    text: str | None = None
    features: list[ExplanationFeature] = Field(default_factory=list)


class AlertDetailResponse(BaseModel):
    alert: AlertSummary
    observations: Observations
    evidence: list[EvidenceItem]
    history: HistorySeries
    root_cause: RootCause
    explanation: Explanation
    ensemble_method: str = "ens_median"


class NetworkSummary(BaseModel):
    stations_monitored: int
    healthy: int
    needs_review: int
    anomaly: int
    offline: int
    network_health_pct: float
    data_mode: str = "historical_replay"
    last_updated: str | None = None


class HistoryResponse(BaseModel):
    station_id: str
    variable: str
    hours: int
    data_mode: str = "historical_replay"
    points: list[dict]


class ErrorResponse(BaseModel):
    detail: str
    code: str


class ProbeRequest(BaseModel):
    station_id: str | None = None
    temperature: float
    pressure: float
    humidity: float


class ProbeObservation(BaseModel):
    station_id: str | None = None
    temperature: float
    pressure: float
    humidity: float


class ProbeContext(BaseModel):
    station_available: bool
    historical_anchor: str | None = None
    spatial_available: bool = False
    neighbor_count: int = 0
    context_note: str


class ProbeResult(BaseModel):
    is_anomalous: bool
    anomaly_score: float | None = None
    confidence: float | None = None
    availability: str = "INSUFFICIENT_EVIDENCE"
    threshold: float | None = None
    method: str = "ens_median"


class ComponentEvidence(BaseModel):
    available: bool
    raw: float | None = None
    calibrated: float | None = None


class ProbeEvidence(BaseModel):
    statistical: ComponentEvidence
    isolation_forest: ComponentEvidence
    lstm: ComponentEvidence
    multivariate: dict = Field(default_factory=dict)
    spatial: dict = Field(default_factory=dict)
    data_quality: dict = Field(default_factory=dict)


class ProbeRootCause(BaseModel):
    class_: str | None = Field(default=None, alias="class")
    confidence: float | None = None
    runner_up: str | None = None

    model_config = {"populate_by_name": True}


class ProbeExplanation(BaseModel):
    text: str | None = None
    features: list[ExplanationFeature] = Field(default_factory=list)


class ProbeResponse(BaseModel):
    data_mode: str = "historical_replay"
    probe: ProbeObservation
    context: ProbeContext
    result: ProbeResult
    evidence: ProbeEvidence
    root_cause: ProbeRootCause
    explanation: ProbeExplanation
