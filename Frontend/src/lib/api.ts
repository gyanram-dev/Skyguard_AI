/**
 * SkyGuard AI API client — single integration point for the FastAPI backend.
 *
 * - Base URL comes from VITE_API_BASE_URL (development default http://localhost:8000).
 * - Native fetch only; no axios.
 * - Centralized URL construction, JSON parsing, non-2xx errors, timeout/abort.
 * - Never returns fabricated values: failures throw ApiError for callers to render.
 */

/** Frontend status domain used across the dashboard map, badges, and queues. */
export type DisplayStatus = "healthy" | "review" | "anomaly" | "offline";

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
  latitude: number | null;
  longitude: number | null;
  status: string;
  data_available: boolean;
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
  coordinates: { latitude: number; longitude: number } | null;
  status: string;
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
  spatial_context: SpatialContext;
}

export interface AlertSummary {
  alert_id: string;
  station_id: string;
  timestamp: string;
  status: string;
  event: string;
  anomaly_score: number | null;
  root_cause: string | null;
  root_cause_confidence: number | null;
  summary: string;
}

export interface AlertListResponse {
  data_mode: string;
  alerts: AlertSummary[];
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
  root_cause: RootCause;
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
  availability: string;
  threshold: number | null;
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
  data_quality: Record<string, number | string | boolean | null>;
}

export interface ProbeRootCause {
  class: string | null;
  confidence: number | null;
  runner_up: string | null;
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
