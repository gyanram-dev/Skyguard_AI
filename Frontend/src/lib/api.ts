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

async function request<T>(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(`Request timed out: GET ${path}`);
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
      }
      if (typeof body.code === "string") code = body.code;
    } catch {
      // Non-JSON error body: fall through to the status-based message.
    }
    throw new ApiError(
      detail ?? `SkyGuard API error ${response.status} for GET ${path}`,
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

export interface HistoryPoint {
  timestamp: string;
  temperature?: number | null;
  humidity?: number | null;
  pressure?: number | null;
}

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
