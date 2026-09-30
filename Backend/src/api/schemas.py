"""Explicit typed response schemas for the versioned API namespace."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelStatus(BaseModel):
    statistical: str
    isolation_forest: str
    lstm_autoencoder: str
    ensemble: str
    root_cause: str


class StationDetectorState(BaseModel):
    """Calibrated station-detector declaration (registry, not inferred).

    Present only for stations with a calibrated station-specific detector.
    ``cadence`` is minutes between real observations; ``pressure_semantics``
    records the measured basis (QNH altimeter is never relabelled as
    station pressure).
    """

    station_id: str | None = None
    capability: str | None = None
    detector_available: bool = False
    detector_type: str | None = None
    detector_method: str | None = None
    cadence: float | None = None
    pressure_semantics: str | None = None
    rh_provenance: str | None = None
    data_mode: str | None = None
    backend_station_id: str | None = None
    source: str | None = None


class StationCapability(BaseModel):
    """Explicit Phase-25 data-capability block (additive; measured, never inferred).

    ``detector_capability``: FULL_TPR | PARTIAL | CONTEXT_ONLY | UNAVAILABLE.
    ``data_mode``: HISTORICAL | REPLAY | CONTROLLED_DEMO | LIVE | LIVE_UNAVAILABLE —
    LIVE is never inferred from a configured provider.
    """

    station_name: str | None = None
    city: str | None = None
    state: str | None = None
    country: str = "India"
    data_source: str
    pressure_basis: str | None = None
    data_mode: str
    observation_count: int = 0
    start_time: str | None = None
    end_time: str | None = None
    variables_available: list[str] = Field(default_factory=list)
    detector_capability: str
    spatial_context_capability: str
    # Calibrated station-detector state (None when no detector covers it).
    detector: StationDetectorState | None = None


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
    source_mode: str = "HISTORICAL"
    source_dataset: str | None = None
    latitude: float | None
    longitude: float | None
    status: str
    data_available: bool = True
    operational_scope: str = "indian_operational"
    capability_notes: list[str] = Field(default_factory=list)
    available_variables: list[str] = Field(default_factory=list)
    # Interactive probe requires detector coverage; contextual-only stations
    # report False so the UI never routes the demo into a guaranteed error.
    capability: StationCapability | None = None
    probe_available: bool = False
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
    source_mode: str = "HISTORICAL"
    source_dataset: str | None = None
    coordinates: Coordinates | None = None
    status: str
    operational_scope: str = "indian_operational"
    capability_notes: list[str] = Field(default_factory=list)
    available_variables: list[str] = Field(default_factory=list)
    capability: StationCapability | None = None
    probe_available: bool = False
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
    maintenance: dict = Field(default_factory=dict)
    signal_health: dict = Field(default_factory=dict)
    spatial_context: SpatialContext


class AlertSummary(BaseModel):
    alert_id: str
    station_id: str
    source_mode: str = "HISTORICAL_ALERT"
    sensor: str | None = None
    timestamp: str
    status: str
    event: str
    anomaly_score: float | None = None
    root_cause: str | None = None
    root_cause_confidence: float | None = None
    duration_seconds: float = 0.0
    summary: str


class AlertListResponse(BaseModel):
    data_mode: str = "historical_replay"
    alerts: list[AlertSummary]
    # Honest paging metadata: `returned` may be smaller than `total` when the
    # caller's limit is reached, so the UI never reports a capped page as a
    # total count of active alerts.
    returned: int = 0
    total: int = 0
    limit: int = 0


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
    data_quality: dict = Field(default_factory=dict)
    root_cause: RootCause
    recommended_action: str | None = None
    explanation: Explanation
    ensemble_method: str = "ens_median"


class NetworkSummary(BaseModel):
    stations_monitored: int
    healthy: int
    needs_review: int
    anomaly: int
    offline: int
    network_health_pct: float
    indian_operational_monitored: int = 0
    indian_operational_healthy: int = 0
    # Honest health breakdown. The four operational buckets below count only
    # stations with detector coverage; `context_only` counts stations that
    # carry historical observations but have no detector, so they must never
    # be folded into "healthy".
    detector_covered: int = 0
    context_only: int = 0
    indian_operational_context_only: int = 0
    # Derived counts for honest headline numbers (never hardcoded):
    # observations_indexed = rows actually loaded from frozen datasets.
    # live_capable_stations = audited IMD WIS2 capability registry size.
    observations_indexed: int = 0
    live_capable_stations: int = 0
    # Phase-25 capability counts (additive). live_connected_stations is a
    # MEASURED fact: 0 unless a real provider connection is currently RUNNING.
    total_stations: int = 0
    historical_stations: int = 0
    full_tpr_stations: int = 0
    partial_stations: int = 0
    context_only_stations: int = 0
    total_observations: int = 0
    live_connected_stations: int = 0
    # Task-contract aliases for the same measured counts (explicit names).
    historical_only: int = 0
    full_tpr: int = 0
    partial: int = 0
    live_capable: int = 0
    data_mode: str = "historical_replay"
    last_updated: str | None = None


class HistoryResponse(BaseModel):
    station_id: str
    variable: str
    hours: int
    data_mode: str = "historical_replay"
    points: list[dict]


class TimelineDetector(BaseModel):
    """Declared provenance of the detector whose events a timeline shows.

    ``available = false`` means no stored detector output covers the
    station; the UI then states HISTORICAL DATA — DETECTOR VERDICT
    UNAVAILABLE and must not infer a verdict.
    """

    available: bool = False
    coverage: str = "UNAVAILABLE"
    detector_type: str | None = None
    threshold: float | None = None
    iqr_factor: float | None = None
    note: str | None = None
    coverage_window: dict | None = None
    flags_total: int = 0
    flags_scored: int | None = None
    flag_rate: float | None = None
    excluded_injection_rows: int | None = None


class TimelineEvent(BaseModel):
    """One detector event over the station's real history (existing output)."""

    timestamp: str
    variable: str | None = None
    observed: float | None = None
    temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    # Causal station baseline and the deviation from it (the frozen 2-hour
    # rolling median for the statistical detector, the station's own preceding
    # two hours for the ensemble timeline).
    baseline_median: float | None = None
    deviation: float | None = None
    baseline_variable: str | None = None
    baseline_basis: str | None = None
    z: float | None = None
    score: float | None = None
    threshold: float | None = None
    severity: str | None = None
    confidence: float | None = None
    confidence_basis: str | None = None
    pattern: str | None = None
    trigger: str | None = None
    detector: str | None = None
    data_quality: str | None = None
    reason: str | None = None
    contributing_factors: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)


class TimelineResponse(BaseModel):
    station_id: str
    city: str
    pressure_basis: str | None = None
    period: dict = Field(default_factory=dict)
    observations: int = 0
    cadence_min: float | None = None
    series: dict = Field(default_factory=dict)
    events: list[TimelineEvent] = Field(default_factory=list)
    events_returned: int = 0
    events_total: int = 0
    detector: TimelineDetector
    data_source: str | None = None
    note: str | None = None


class NearbyStation(BaseModel):
    """One audited neighbour with its real, causally aligned observation."""

    station_id: str
    city: str | None = None
    backend_station_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    rank: int | None = None
    aligned_timestamp: str | None = None
    age_minutes: float | None = None
    temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    pressure_basis: str | None = None
    data_freshness: str | None = None


class InvestigationResponse(BaseModel):
    """Target station vs real nearby stations (existing spatial decision)."""

    station_id: str
    city: str
    coordinates: dict = Field(default_factory=dict)
    pressure_basis: str | None = None
    source_dataset: str | None = None
    anchor: dict = Field(default_factory=dict)
    target_observation: Observations
    detector_verdict: dict = Field(default_factory=dict)
    nearby: list[NearbyStation] = Field(default_factory=list)
    expected_neighbors: int = 0
    usable_neighbors: int = 0
    comparison: dict = Field(default_factory=dict)
    interpretation: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class FaultDemoResponse(BaseModel):
    """Controlled fault-injection demo (never live data)."""

    label: str
    disclaimer: str
    station_id: str
    city: str
    city_coordinates: dict = Field(default_factory=dict)
    source_dataset: str
    cadence_min: float
    anchor: str
    context_rows: int
    detector: str
    injection_parameters: dict = Field(default_factory=dict)
    summary: dict = Field(default_factory=dict)
    rows: list[dict] = Field(default_factory=list)
    stored_data_modified: bool = False


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
    confidence_basis: str | None = None
    availability: str = "INSUFFICIENT_EVIDENCE"
    threshold: float | None = None
    severity: str | None = None
    trigger: str | None = None
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
    seasonal: dict = Field(default_factory=dict)
    data_quality: dict = Field(default_factory=dict)
    freeze: dict = Field(default_factory=dict)


class ProbeRootCause(BaseModel):
    class_: str | None = Field(default=None, alias="class")
    confidence: float | None = None
    runner_up: str | None = None
    basis: str | None = None

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
    spatial_decision: dict = Field(default_factory=dict)
    recommended_action: str | None = None
    detector: str | None = None
    severity: str | None = None
    primary_reason: str | None = None
    contributing_factors: list[str] | None = None


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
    stations_detected: list[str] = Field(default_factory=list)


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
    stations: list = Field(default_factory=list)


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
    stations: list = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
