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
    data_status: str = "available"
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


class DetectionEntry(BaseModel):
    dataset: str
    split: str
    method: str = "ens_median"
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    fpr: float | None = None
    fnr: float | None = None
    events: int | None = None
    events_detected: int | None = None
    event_recall: float | None = None
    latency_median_min: float | None = None


class ModelComparisonEntry(BaseModel):
    dataset: str
    split: str
    reference_method: str
    method: str
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    event_recall: float | None = None
    fpr: float | None = None


class GeneralizationEntry(BaseModel):
    dataset: str
    method: str = "ens_median"
    id_precision: float | None = None
    id_recall: float | None = None
    id_f1: float | None = None
    id_event_recall: float | None = None
    ood_precision: float | None = None
    ood_recall: float | None = None
    ood_f1: float | None = None
    ood_event_recall: float | None = None


class RootCauseEntry(BaseModel):
    dataset: str
    split: str
    n_diagnosed: int
    accuracy_incl_unknown: float | None = None
    accuracy_excl_unknown: float | None = None
    unknown_rate: float | None = None
    macro_f1: float | None = None
    per_class: dict = Field(default_factory=dict)


class EvaluationSummary(BaseModel):
    data_mode: str = "benchmark_evaluation"
    provenance: dict = Field(default_factory=dict)
    detection: list[DetectionEntry] = Field(default_factory=list)
    model_comparison: list[ModelComparisonEntry] = Field(default_factory=list)
    generalization: list[GeneralizationEntry] = Field(default_factory=list)
    root_cause: list[RootCauseEntry] = Field(default_factory=list)
    runtime: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ReadinessResponse(BaseModel):
    ready: bool
    data_mode: str = "historical_replay"
    default_station: str | None = None
    default_split: str = "OOD"
    replay_available: bool = False
    probe_available: bool = False
    evaluation_available: bool = False
    missing: list[str] = Field(default_factory=list)


class MappingProposal(BaseModel):
    column: str | None = None
    confidence: str
    alternates: list[str] = Field(default_factory=list)


class UnitsProposal(BaseModel):
    unit: str | None = None
    source: str


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    size_bytes: int
    rows: int
    columns: list[str] = Field(default_factory=list)
    mapping: dict[str, MappingProposal] = Field(default_factory=dict)
    units: dict[str, UnitsProposal] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ConfirmMapping(BaseModel):
    timestamp: str
    temperature: str
    humidity: str | None = None
    pressure: str | None = None


class ConfirmUnits(BaseModel):
    temperature: str
    pressure: str | None = None


class ConfirmRequest(BaseModel):
    mapping: ConfirmMapping
    units: ConfirmUnits
    station_label: str | None = None


class TimeRange(BaseModel):
    start: str | None = None
    end: str | None = None


class DQPreview(BaseModel):
    session_id: str
    station_label: str
    rows: int
    time_range: TimeRange
    cadence_min: float
    horizons: dict = Field(default_factory=dict)
    duplicates: int
    missing: dict = Field(default_factory=dict)
    large_gaps: int
    invalid_timestamps: int
    non_finite: int
    rh_invalid: int | None = None
    rh_available: bool
    pressure_available: bool
    ml_eligible: int
    quality_counts: dict = Field(default_factory=dict)


class AnomalyRecord(BaseModel):
    timestamp: str
    station: str
    observation: dict = Field(default_factory=dict)
    score: float | None = None
    decision: str = "anomaly"
    confidence: float | None = None
    root_cause_estimate: str
    evidence: dict = Field(default_factory=dict)
    explanation: str
    correction: dict | None = None
    recommended_action: str


class AnalysisResult(BaseModel):
    session_id: str
    filename: str
    station_label: str
    data_mode: str = "upload_analysis"
    cadence_min: float
    observations: int
    normal: int
    anomalies: int
    dq_events: int
    evidence_availability: dict = Field(default_factory=dict)
    breakdown: dict = Field(default_factory=dict)
    anomalies_detail: list[AnomalyRecord] = Field(default_factory=list)
    mapping: dict = Field(default_factory=dict)
    units: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
