/**
 * SkyGuard AI API client — single integration point for the FastAPI backend.
 *
 * - Base URL comes from VITE_API_BASE_URL (development default http://localhost:8000).
 * - Native fetch only; no axios.
 * - Centralized URL construction, JSON parsing, non-2xx errors, timeout/abort.
 * - Never returns fabricated values: failures throw ApiError for callers to render.
 */

/**
 * Frontend status domain used across the dashboard map, badges, and queues.
 *
 * `historical` means the station carries real historical observations but has
 * no detector coverage, so no health verdict exists for it. It is deliberately
 * NOT reported as healthy.
 */
export type DisplayStatus = "healthy" | "review" | "anomaly" | "offline" | "historical";

/** Phase-25 detector capability classes (mirrors backend station_service). */
export type DetectorCapability = "FULL_TPR" | "PARTIAL" | "CONTEXT_ONLY" | "UNAVAILABLE";

/**
 * Calibrated station-detector declaration served inside `capability.detector`
 * (mirrors Backend/src/api/schemas.py StationDetectorState). Present only for
 * stations with a calibrated station-specific detector; every value is read
 * from the detector registry, never inferred in the browser.
 *
 * `cadence` is minutes between real observations. `pressure_semantics` records
 * the measured pressure basis (QNH altimeter is never shown as station
 * pressure).
 */
export interface StationDetectorState {
  station_id: string | null;
  capability: DetectorCapability | null;
  detector_available: boolean;
  detector_type: string | null;
  detector_method: string | null;
  cadence: number | null;
  pressure_semantics: string | null;
  rh_provenance: string | null;
  data_mode: string | null;
  backend_station_id: string | null;
  source: string | null;
}

/**
 * Phase-25 capability block served additively by /api/v1/stations.
 * `observation_count` is measured from loaded rows; missing variables stay
 * absent from `variables_available` — never fabricated.
 */
export interface StationCapability {
  station_name: string | null;
  city: string | null;
  state: string | null;
  country: string;
  data_source: string;
  pressure_basis: string | null;
  data_mode: string;
  observation_count: number;
  start_time: string | null;
  end_time: string | null;
  variables_available: string[];
  detector_capability: DetectorCapability;
  spatial_context_capability: string;
  /** Calibrated station detector (null when no detector covers the station). */
  detector?: StationDetectorState | null;
}

/**
 * True when a detector can actually produce a verdict for this station:
 * the frozen ensemble (FULL_TPR) or a calibrated station-specific statistical
 * detector. PARTIAL means partial variable coverage, never "no detector".
 */
export function hasDetectorCoverage(
  summary:
    | { probe_available?: boolean | undefined; capability?: StationCapability | null | undefined }
    | undefined,
): boolean {
  if (!summary) return false;
  if (summary.capability?.detector?.detector_available === true) return true;
  return summary.probe_available === true;
}

/**
 * The ONE status normalization function. Backend status strings
 * (e.g. "needs_review", "healthy", "anomaly", "offline") are mapped here;
 * components must not scatter their own conversions.
 */
export function normalizeStatus(
  raw: string | null | undefined,
  dataAvailable = true,
): DisplayStatus {
  if (!dataAvailable) return "offline";
  const value = (raw ?? "").toLowerCase().trim();
  if (value === "healthy" || value === "normal" || value === "ok" || value === "pass") {
    return "healthy";
  }
  if (
    value === "historical_only" ||
    value === "historical" ||
    value === "context_only" ||
    value === "historical."
  ) {
    return "historical";
  }
  if (value === "anomaly" || value === "anomalous" || value === "critical" || value === "fault") {
    return "anomaly";
  }
  if (
    value === "offline" ||
    value === "missing" ||
    value === "unavailable" ||
    value === "no_data" ||
    value === "nodata"
  ) {
    return "offline";
  }
  // "review", "needs_review", "unknown", "" and anything unexpected
  // conservatively need operator review.
  return "review";
}

const rawBaseUrl = (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "";
export const API_BASE_URL = rawBaseUrl.trim() !== "" ? rawBaseUrl.trim() : "http://localhost:8000";

export const DATA_MODE_HISTORICAL_REPLAY = "historical_replay";

export class ApiError extends Error {
  readonly status: number | null;
  readonly code: string | null;

  constructor(message: string, status: number | null = null, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const DEFAULT_TIMEOUT_MS = 10_000;
const PROBE_TIMEOUT_MS = 120_000;

async function request<T>(
  path: string,
  options?: { method?: string; body?: unknown; rawBody?: BodyInit; timeoutMs?: number },
): Promise<T> {
  const method = options?.method ?? "GET";
  const timeoutMs = options?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  const init: RequestInit = {
    method,
    headers: {
      Accept: "application/json",
      ...(options?.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    signal: controller.signal,
  };
  if (options?.rawBody !== undefined) {
    init.body = options.rawBody;
  } else if (options?.body !== undefined) {
    init.body = JSON.stringify(options.body);
  }
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(`Request timed out: ${method} ${path}`);
    }
    throw new ApiError(
      `Unable to reach the SkyGuard API at ${API_BASE_URL}. Is the backend running?`,
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    let detail: string | null = null;
    let code: string | null = null;
    try {
      const body = (await response.json()) as { detail?: unknown; code?: unknown };
      if (typeof body.detail === "string" && body.detail.trim() !== "") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        // Pydantic request-validation errors: summarize without leaking schema internals.
        detail = `Invalid probe input (${response.status}). Check the highlighted fields.`;
        code = "invalid_input";
      }
      if (typeof body.code === "string") code = body.code;
    } catch {
      // Non-JSON error body: fall through to the status-based message.
    }
    throw new ApiError(
      detail ?? `SkyGuard API error ${response.status} for ${method} ${path}`,
      response.status,
      code,
    );
  }

  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Response types mirroring Backend/src/api/schemas.py (Phase 12 contract).
// ---------------------------------------------------------------------------

export interface ModelStatus {
  statistical: string;
  isolation_forest: string;
  lstm_autoencoder: string;
  ensemble: string;
  root_cause: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  data_mode: string;
  model_status: ModelStatus;
}

export interface StationSummary {
  station_id: string;
  city: string;
  source_mode: string;
  source_dataset: string | null;
  latitude: number | null;
  longitude: number | null;
  status: string;
  data_available: boolean;
  operational_scope: string;
  capability_notes: string[];
  /** Detector coverage: whether the interactive probe can score this station. */
  probe_available: boolean;
  available_variables: string[];
  /** Explicit Phase-25 capability block (null on older backends). */
  capability: StationCapability | null;
  data_mode: string;
  temperature: number | null;
  humidity: number | null;
  pressure: number | null;
  anomaly_score: number | null;
  confidence: number | null;
  last_updated: string | null;
}

export interface StationListResponse {
  data_mode: string;
  stations: StationSummary[];
}

export interface StationInfo {
  station_id: string;
  city: string;
  source_mode: string;
  source_dataset: string | null;
  coordinates: { latitude: number; longitude: number } | null;
  status: string;
  operational_scope: string;
  capability_notes: string[];
  probe_available: boolean;
  available_variables: string[];
  /** Explicit Phase-25 capability block (null on older backends). */
  capability: StationCapability | null;
  data_mode: string;
  last_updated: string | null;
}

export interface Observations {
  temperature_c: number | null;
  relative_humidity_pct: number | null;
  pressure_hpa: number | null;
}

export interface DataQuality {
  status: string;
  ml_eligible: boolean;
  flags: string[];
}

export interface Anomaly {
  detected: boolean;
  score: number | null;
  method: string;
  confidence: number | null;
}

export interface RootCause {
  class: string | null;
  confidence: number | null;
}

export interface SpatialContext {
  available: boolean;
  neighbor_count: number;
  context_level: string;
}

export interface StationDetailResponse {
  station: StationInfo;
  observations: Observations;
  data_quality: DataQuality;
  anomaly: Anomaly;
  root_cause: RootCause;
  maintenance?: Record<string, string | number | boolean | null>;
  /** Longitudinal flatline indicator; descriptive, never a prediction. */
  signal_health?: Record<string, string | number | boolean | null> | null;
  spatial_context: SpatialContext;
}

export interface AlertSummary {
  alert_id: string;
  station_id: string;
  source_mode?: string;
  sensor?: string | null;
  timestamp: string;
  status: string;
  event: string;
  anomaly_score: number | null;
  root_cause: string | null;
  root_cause_confidence: number | null;
  duration_seconds?: number;
  summary: string;
}

export interface AlertListResponse {
  data_mode: string;
  alerts: AlertSummary[];
  /** Paging metadata so a capped page is never reported as a total. */
  returned: number;
  total: number;
  limit: number;
}

export interface EvidenceItem {
  title: string;
  detail: string;
  source: string;
}

export interface HistorySeries {
  variable: string;
  hours: number;
  /** Points are { timestamp, <variable>: number|null }; missingness preserved. */
  series: Array<{ timestamp: string } & Record<string, number | string | null>>;
}

export interface ExplanationFeature {
  name: string;
  value: number | null;
  contribution: number | null;
  direction: string;
}

export interface Explanation {
  text: string | null;
  features: ExplanationFeature[];
}

export interface AlertDetailResponse {
  alert: AlertSummary;
  observations: Observations;
  evidence: EvidenceItem[];
  history: HistorySeries;
  data_quality?: { status: string; evaluation_eligible: boolean };
  root_cause: RootCause;
  recommended_action?: string | null;
  explanation: Explanation;
  ensemble_method: string;
}

export interface NetworkSummary {
  stations_monitored: number;
  healthy: number;
  needs_review: number;
  anomaly: number;
  offline: number;
  network_health_pct: number;
  indian_operational_monitored: number;
  indian_operational_healthy: number;
  /** Stations with detector coverage (the only ones with a health verdict). */
  detector_covered?: number;
  /** Stations with historical observations but no detector. */
  context_only?: number;
  indian_operational_context_only?: number;
  /** Rows actually loaded from frozen datasets (measured, never hardcoded). */
  observations_indexed?: number;
  /** Audited IMD WIS2 capability registry size (no bulk rows). */
  live_capable_stations?: number;
  /** Phase-25 capability counts; live_connected is measured, 0 when disabled. */
  total_stations?: number;
  historical_stations?: number;
  full_tpr_stations?: number;
  partial_stations?: number;
  context_only_stations?: number;
  total_observations?: number;
  live_connected_stations?: number;
  data_mode: string;
  last_updated: string | null;
}

export type HistoryVariable = "temperature" | "humidity" | "pressure";

export type HistoryPoint = {
  timestamp: string;
  temperature?: number | null;
  humidity?: number | null;
  pressure?: number | null;
};

export interface HistoryResponse {
  station_id: string;
  variable: string;
  hours: number;
  data_mode: string;
  points: HistoryPoint[];
}

// ---------------------------------------------------------------------------
// Typed endpoint functions.
// ---------------------------------------------------------------------------

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/v1/health");
}

export function getStations(): Promise<StationListResponse> {
  return request<StationListResponse>("/api/v1/stations");
}

export function getStation(stationId: string): Promise<StationDetailResponse> {
  return request<StationDetailResponse>(`/api/v1/stations/${encodeURIComponent(stationId)}`);
}

export function getStationHistory(
  stationId: string,
  variable: HistoryVariable,
  hours = 24,
): Promise<HistoryResponse> {
  return request<HistoryResponse>(
    `/api/v1/stations/${encodeURIComponent(stationId)}/history?variable=${variable}&hours=${hours}`,
  );
}

export function getAlerts(limit = 50): Promise<AlertListResponse> {
  return request<AlertListResponse>(`/api/v1/alerts?limit=${limit}`);
}

export function getAlert(alertId: string): Promise<AlertDetailResponse> {
  return request<AlertDetailResponse>(`/api/v1/alerts/${encodeURIComponent(alertId)}`);
}

export function getNetworkSummary(): Promise<NetworkSummary> {
  return request<NetworkSummary>("/api/v1/network/summary");
}

// ---------------------------------------------------------------------------
// Live ingestion types mirroring the backend live service (Phase 23).
// ---------------------------------------------------------------------------

export interface LiveStatus {
  state: string;
  status: string;
  provider_status: string;
  mode: string;
  detail?: string | null;
  source: string | null;
  stations: string[];
  last_attempt: string | null;
  last_success: string | null;
  last_error: string;
  open_episodes: number;
  inference_latency: Record<string, number>;
}

export interface LiveStationState {
  station_id: string;
  history_rows: number;
  warm_state: string;
  latest_timestamp: string | null;
  latest: Record<string, number | null> | null;
}

export interface LiveEpisode {
  alert_id: string;
  station_id: string;
  episode_key: string;
  interpretation: string;
  started_at: string;
  last_seen_at: string;
  detection_count: number;
  status: string;
  resolved_at: string | null;
  score: number | null;
}

export interface LiveInvestigationObservation {
  obs_id: string;
  station_id: string;
  timestamp: string;
  temperature_c: number | null;
  pressure_hpa: number | null;
  relative_humidity_pct: number | null;
  source: string;
  pressure_basis: string;
  dq_state: string;
  received_at: string;
}

export interface LiveAlertInvestigation {
  source_mode: "LIVE_ALERT";
  episode: LiveEpisode;
  evidence: Record<string, unknown>;
  observations: LiveInvestigationObservation[];
}

export function getLiveStatus(): Promise<LiveStatus> {
  return request<LiveStatus>("/api/v1/live/status");
}

export function getLiveStations(): Promise<{ mode: string; stations: LiveStationState[] }> {
  return request<{ mode: string; stations: LiveStationState[] }>("/api/v1/live/stations");
}

export function getLiveAlerts(
  stationId?: string,
): Promise<{ mode: string; episodes: LiveEpisode[] }> {
  const query = stationId ? `?station_id=${encodeURIComponent(stationId)}` : "";
  return request<{ mode: string; episodes: LiveEpisode[] }>(`/api/v1/live/alerts${query}`);
}

export function getLiveAlert(alertId: string): Promise<LiveAlertInvestigation> {
  return request<LiveAlertInvestigation>(`/api/v1/live/alerts/${encodeURIComponent(alertId)}`);
}

export function startLive(): Promise<LiveStatus> {
  return request<LiveStatus>("/api/v1/live/start", { method: "POST" });
}

export function stopLive(): Promise<LiveStatus> {
  return request<LiveStatus>("/api/v1/live/stop", { method: "POST" });
}

export function startLiveDemo(): Promise<LiveStatus> {
  return request<LiveStatus>("/api/v1/live/demo/start", { method: "POST" });
}

// ---------------------------------------------------------------------------
// Judge probe types mirroring Backend/src/api/schemas.py (Phase 15).
// ---------------------------------------------------------------------------

export interface ProbePayload {
  station_id: string | null;
  temperature: number;
  pressure: number;
  humidity: number;
}

export interface ProbeObservationEcho {
  station_id: string | null;
  temperature: number;
  pressure: number;
  humidity: number;
}

export interface ProbeContext {
  station_available: boolean;
  historical_anchor: string | null;
  spatial_available: boolean;
  neighbor_count: number;
  context_note: string;
}

export interface ProbeResult {
  is_anomalous: boolean;
  anomaly_score: number | null;
  confidence: number | null;
  confidence_basis?: string | null;
  availability: string;
  threshold: number | null;
  severity?: string | null;
  trigger?: string | null;
  method: string;
}

export interface ProbeComponentEvidence {
  available: boolean;
  raw: number | null;
  calibrated: number | null;
}

export interface ProbeEvidence {
  statistical: ProbeComponentEvidence;
  isolation_forest: ProbeComponentEvidence;
  lstm: ProbeComponentEvidence;
  multivariate: Record<string, number | null>;
  spatial: Record<string, number | string | boolean | null>;
  seasonal?: Record<string, number | string | boolean | null> | null;
  data_quality: Record<string, number | string | boolean | null>;
  freeze?: Record<string, string | number | boolean | null> | null;
}

export interface ProbeRootCause {
  class: string | null;
  confidence: number | null;
  runner_up: string | null;
  basis?: string | null;
}

export interface SpatialDecision {
  base_decision: string;
  contextual_decision: string;
  spatial_influence: string;
  spatial_status: string;
  description?: string | null;
}

export interface ProbeResponse {
  data_mode: string;
  probe: ProbeObservationEcho;
  context: ProbeContext;
  result: ProbeResult;
  evidence: ProbeEvidence;
  root_cause: ProbeRootCause;
  explanation: Explanation;
  spatial_decision?: SpatialDecision | null;
  recommended_action?: string | null;
  /**
   * Station-specific detector evidence: sent only by backends that score the
   * observation with a calibrated station detector. The frozen ensemble path
   * does not carry these fields, so they are optional and are rendered only
   * when actually present — never inferred in the browser.
   */
  detector?: string | null;
  severity?: string | null;
  primary_reason?: string | null;
  contributing_factors?: string[] | null;
}

export function probeObservation(payload: ProbePayload): Promise<ProbeResponse> {
  return request<ProbeResponse>("/api/v1/demo/probe", {
    method: "POST",
    body: payload,
    timeoutMs: PROBE_TIMEOUT_MS,
  });
}

// ---------------------------------------------------------------------------
// Evaluation evidence types mirroring Backend/src/api/schemas.py (Phase 17).
// Frozen benchmark values served verbatim; missing stays null (N/A).
// ---------------------------------------------------------------------------

export interface DetectionEntry {
  dataset: string;
  split: string;
  method: string;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  fpr: number | null;
  fnr: number | null;
  events: number | null;
  events_detected: number | null;
  event_recall: number | null;
  latency_median_min: number | null;
}

export interface ModelComparisonEntry {
  dataset: string;
  split: string;
  reference_method: string;
  method: string;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  event_recall: number | null;
  fpr: number | null;
}

export interface GeneralizationEntry {
  dataset: string;
  method: string;
  id_precision: number | null;
  id_recall: number | null;
  id_f1: number | null;
  id_event_recall: number | null;
  ood_precision: number | null;
  ood_recall: number | null;
  ood_f1: number | null;
  ood_event_recall: number | null;
}

export interface RootCauseClassStats {
  precision: number | null;
  recall: number | null;
  f1: number | null;
  support: number | null;
}

export interface RootCauseEntry {
  dataset: string;
  split: string;
  n_diagnosed: number;
  accuracy_incl_unknown: number | null;
  accuracy_excl_unknown: number | null;
  unknown_rate: number | null;
  macro_f1: number | null;
  per_class: Record<string, RootCauseClassStats>;
}

export interface EvaluationSummary {
  data_mode: string;
  provenance: Record<string, string>;
  detection: DetectionEntry[];
  model_comparison: ModelComparisonEntry[];
  generalization: GeneralizationEntry[];
  root_cause: RootCauseEntry[];
  runtime: Record<string, unknown>;
  notes: string[];
}

export function getEvaluationSummary(): Promise<EvaluationSummary> {
  return request<EvaluationSummary>("/api/v1/evaluation/summary");
}

// ---------------------------------------------------------------------------
// Demo readiness types mirroring Backend/src/api/schemas.py (Phase 18).
// Lightweight capability flags; never blocks the app when unavailable.
// ---------------------------------------------------------------------------

export interface DemoReadiness {
  ready: boolean;
  data_mode: string;
  default_station: string | null;
  default_split: string;
  replay_available: boolean;
  probe_available: boolean;
  evaluation_available: boolean;
  missing: string[];
}

export function getDemoReadiness(): Promise<DemoReadiness> {
  return request<DemoReadiness>("/api/v1/demo/readiness");
}

// ---------------------------------------------------------------------------
// CSV upload analysis types mirroring Backend/src/api/schemas.py (Phase 20).
// ---------------------------------------------------------------------------

export interface UploadMappingProposal {
  column: string | null;
  confidence: string;
  alternates: string[];
}

export interface UploadUnitsProposal {
  unit: string | null;
  source: string;
}

export interface UploadResponse {
  session_id: string;
  filename: string;
  size_bytes: number;
  rows: number;
  columns: string[];
  mapping: Record<string, UploadMappingProposal>;
  units: Record<string, UploadUnitsProposal>;
  warnings: string[];
  stations_detected: string[];
}

export interface ConfirmUploadPayload {
  mapping: {
    timestamp: string;
    temperature: string;
    humidity?: string | null | undefined;
    pressure?: string | null | undefined;
  };
  units: { temperature: string; pressure?: string | null | undefined };
  station_label?: string | undefined;
}

export interface DQPreview {
  session_id: string;
  station_label: string;
  rows: number;
  time_range: { start: string | null; end: string | null };
  cadence_min: number;
  horizons: Record<string, number>;
  duplicates: number;
  missing: Record<string, number>;
  large_gaps: number;
  invalid_timestamps: number;
  non_finite: number;
  rh_invalid: number | null;
  rh_available: boolean;
  pressure_available: boolean;
  ml_eligible: number;
  quality_counts: Record<string, number>;
  stations: Array<Record<string, unknown>>;
}

export interface UploadAnomalyCorrection {
  original_value: number | null;
  suggested_value: number | null;
  reason: string;
}

export interface UploadAnomalyRecord {
  timestamp: string;
  station: string;
  observation: Record<string, number | null>;
  score: number | null;
  decision: string;
  confidence: number | null;
  root_cause_estimate: string;
  evidence: Record<string, unknown>;
  explanation: string;
  correction: UploadAnomalyCorrection | null;
  recommended_action: string;
}

export interface UploadAnalysisResult {
  session_id: string;
  filename: string;
  station_label: string;
  data_mode: string;
  cadence_min: number;
  observations: number;
  normal: number;
  anomalies: number;
  dq_events: number;
  evidence_availability: Record<string, boolean>;
  breakdown: Record<string, number>;
  anomalies_detail: UploadAnomalyRecord[];
  mapping: Record<string, string | null>;
  units: Record<string, string | null>;
  stations: Array<Record<string, unknown>>;
  notes: string[];
}

export function uploadCsv(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file, file.name);
  return request<UploadResponse>("/api/v1/analyze/upload", {
    method: "POST",
    rawBody: form,
    timeoutMs: 60_000,
  });
}

export function confirmUpload(
  sessionId: string,
  payload: ConfirmUploadPayload,
): Promise<DQPreview> {
  return request<DQPreview>(`/api/v1/analyze/${encodeURIComponent(sessionId)}/confirm`, {
    method: "POST",
    body: payload,
    timeoutMs: 60_000,
  });
}

export function runUploadAnalysis(sessionId: string): Promise<UploadAnalysisResult> {
  return request<UploadAnalysisResult>(`/api/v1/analyze/${encodeURIComponent(sessionId)}/run`, {
    method: "POST",
    timeoutMs: 300_000,
  });
}

export function getUploadAnalysis(sessionId: string): Promise<UploadAnalysisResult> {
  return request<UploadAnalysisResult>(`/api/v1/analyze/${encodeURIComponent(sessionId)}`);
}

// ---------------------------------------------------------------------------
// Historical timeline + investigation hub (showcase layer).
//
// `detector.available === false` means no stored detector output covers the
// station: the timeline then shows real observations only and the UI must
// state HISTORICAL DATA — DETECTOR VERDICT UNAVAILABLE. Nothing here infers a
// verdict the backend does not have.
// ---------------------------------------------------------------------------
export interface TimelineDetector {
  available: boolean;
  coverage: string;
  detector_type: string | null;
  threshold: number | null;
  iqr_factor: number | null;
  note: string | null;
  coverage_window: { start: string; end: string } | null;
  flags_total: number;
  flags_scored: number | null;
  flag_rate: number | null;
  excluded_injection_rows: number | null;
}

export interface TimelineEvent {
  timestamp: string;
  variable: string | null;
  /** Value of the parameter that actually fired (equals one channel below). */
  observed: number | null;
  temperature?: number | null;
  humidity: number | null;
  pressure: number | null;
  /** Causal station baseline (2-hour median) and the deviation from it. */
  baseline_median?: number | null;
  deviation?: number | null;
  baseline_variable?: string | null;
  baseline_basis?: string | null;
  /** Detector statistic behind the event (z margin / raw component value). */
  z?: number | null;
  score: number | null;
  threshold: number | null;
  severity: string | null;
  confidence: number | null;
  confidence_basis: string | null;
  pattern: string | null;
  trigger: string | null;
  detector: string | null;
  data_quality: string | null;
  reason: string | null;
  contributing_factors?: string[];
  evidence?: Record<string, number | string | null>;
}

export interface TimelineSeries {
  timestamps: string[];
  temperature: Array<number | null>;
  humidity: Array<number | null>;
  pressure: Array<number | null>;
  stride?: number;
  reported_points?: number;
}

export interface TimelineResponse {
  station_id: string;
  city: string;
  pressure_basis: string | null;
  period: { start: string | null; end: string | null };
  observations: number;
  cadence_min: number | null;
  series: TimelineSeries;
  events: TimelineEvent[];
  events_returned: number;
  events_total: number;
  detector: TimelineDetector;
  data_source: string | null;
  note: string | null;
}

export interface NearbyStation {
  station_id: string;
  city: string | null;
  backend_station_id: string | null;
  latitude: number | null;
  longitude: number | null;
  distance_km: number | null;
  rank: number | null;
  aligned_timestamp: string | null;
  age_minutes: number | null;
  temperature: number | null;
  humidity: number | null;
  pressure: number | null;
  pressure_basis: string | null;
  data_freshness: string | null;
}

export interface SpatialVariableEvidence {
  status: string;
  reference_median: number | null;
  mad: number | null;
  robust_score: number | null;
  deviation: number | null;
  neighbor_count: number;
  usable_neighbor_count: number;
  supporting_neighbors: string[];
  contradicting_neighbors: string[];
  reason: string;
}

export interface InvestigationResponse {
  station_id: string;
  city: string;
  coordinates: { latitude: number | null; longitude: number | null };
  pressure_basis: string | null;
  source_dataset: string | null;
  anchor: {
    timestamp: string;
    basis: string;
    requested: string | null;
    time_basis: string;
  };
  target_observation: Observations;
  detector_verdict: Record<string, unknown>;
  nearby: NearbyStation[];
  expected_neighbors: number;
  usable_neighbors: number;
  comparison: {
    temperature: SpatialVariableEvidence;
    humidity: SpatialVariableEvidence;
    pressure: SpatialVariableEvidence;
    target_temperature: number | null;
    neighbor_median_temperature: number | null;
    temperature_deviation: number | null;
  };
  interpretation: {
    base_decision: string;
    contextual_decision: string;
    spatial_influence: string;
    spatial_status: string;
    humidity_status: string;
    humidity_corroboration: string | null;
    description: string;
  };
  notes: string[];
}

export interface FaultDemoRow {
  index: number;
  timestamp: string;
  phase: "NORMAL" | "SPIKE" | "FROZEN" | "DRIFT" | "CROSS_VARIABLE";
  injected: boolean;
  temperature_c: number | null;
  pressure_hpa: number | null;
  relative_humidity_pct: number | null;
  detection: {
    anomaly: boolean;
    severity: string | null;
    confidence: number | null;
    confidence_basis: string | null;
    trigger: string | null;
    method: string | null;
    score: number | null;
    threshold: number | null;
    availability: string | null;
    components_available: number | null;
    root_cause: string | null;
    root_cause_confidence: number | null;
    root_cause_basis: string | null;
    pattern: string | null;
    reason: string;
    multivariate_max_abs_robust_deviation_2h: number | null;
    data_quality: string;
    spatial_context: string | null;
  };
}

export interface FaultDemoResponse {
  label: string;
  disclaimer: string;
  station_id: string;
  city: string;
  source_dataset: string;
  cadence_min: number;
  anchor: string;
  context_rows: number;
  detector: string;
  injection_parameters: Record<string, unknown>;
  summary: {
    rows: number;
    normal_false_positives: number;
    faults_detected: number;
    faults_total: number;
    by_phase: Record<
      string,
      {
        rows: number;
        detected: number;
        first_detection: {
          index: number;
          timestamp: string;
          severity: string | null;
          root_cause: string | null;
          confidence: number | null;
        } | null;
      }
    >;
  };
  rows: FaultDemoRow[];
  stored_data_modified: boolean;
}

export function getStationTimeline(
  stationId: string,
  maxPoints = 900,
  maxEvents = 400,
): Promise<TimelineResponse> {
  return request<TimelineResponse>(
    `/api/v1/stations/${encodeURIComponent(stationId)}/timeline?max_points=${maxPoints}&max_events=${maxEvents}`,
    { timeoutMs: 120_000 },
  );
}

export function getStationInvestigation(
  stationId: string,
  at?: string | null,
): Promise<InvestigationResponse> {
  const suffix = at ? `?at=${encodeURIComponent(at)}` : "";
  return request<InvestigationResponse>(
    `/api/v1/stations/${encodeURIComponent(stationId)}/investigation${suffix}`,
    { timeoutMs: 120_000 },
  );
}

export function getFaultSequence(): Promise<FaultDemoResponse> {
  return request<FaultDemoResponse>("/api/v1/demo/fault-sequence", { timeoutMs: 600_000 });
}
