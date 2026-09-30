import { API_BASE_URL } from "@/lib/api";

/**
 * Dedicated WebSocket layer for accelerated historical replay (Phase 16).
 * Transport + parsing only; streaming state lives in useLiveReplay.
 * The socket URL derives from VITE_API_BASE_URL (ws/wss); no hard-coded hosts.
 */

export type ConnectionState = "disconnected" | "connecting" | "connected" | "error";

/**
 * Documented replay event contract (backend: src/api/replay/protocol.py).
 * Every server message carries both `type` (this frontend's original
 * contract) and `event_type` (the same event under its documented name).
 */
export type LiveEventType =
  "CONNECTION" | "REPLAY_STATE" | "OBSERVATION" | "ANOMALY_DETECTED" | "REPLAY_COMPLETE" | "ERROR";

export interface LiveObservations {
  temperature_c: number | null;
  relative_humidity_pct: number | null;
  pressure_hpa: number | null;
}

export interface LiveComponentEvidence {
  available: boolean;
  raw: number | null;
  calibrated: number | null;
}

/**
 * Evidence payload. Two shapes reach the wire:
 *
 * - Delhi frozen ensemble: statistical / isolation_forest / lstm component
 *   evidence plus multivariate and spatial context.
 * - Calibrated station detectors (the ten Indian GHCNh stations): a
 *   statistical verdict with contributing factors and spatial context. The
 *   ensemble-only components are genuinely absent, so every component field
 *   is optional and no component is invented by the UI.
 */
/** Deterministic freeze confirmation (stuck-signal evidence), when present. */
export interface LiveFreezeEvidence {
  confirmed: boolean;
  column?: string;
  variable?: string;
  run_rows?: number;
  run_hours?: number;
  severity?: string;
  confidence?: number | null;
  confidence_basis?: string;
  min_run_rows?: number;
}

export interface LiveEvidence {
  statistical?: LiveComponentEvidence;
  isolation_forest?: LiveComponentEvidence;
  lstm?: LiveComponentEvidence;
  multivariate?: Record<string, number | null>;
  spatial?: Record<string, number | string | boolean | null>;
  seasonal?: Record<string, number | string | boolean | null>;
  freeze?: LiveFreezeEvidence | null;
  contributing_factors?: string[];
}

export interface LiveDetection {
  detected?: boolean;
  anomaly?: boolean;
  score: number | null;
  severity?: string;
  confidence?: number | null;
  confidence_basis?: string | null;
  detector?: string;
  method?: string;
  trigger?: string | null;
  freeze?: LiveFreezeEvidence | null;
  pattern_estimate?: string | null;
  primary_reason?: string;
  contributing_factors?: string[];
}

export interface LiveReading {
  type: "reading";
  event_type?: LiveEventType;
  station_id: string;
  city: string;
  timestamp: string;
  sequence: number;
  source_mode?: string;
  data_mode: string;
  observations: LiveObservations;
  /** Spec'd alias of `observations` (present on calibrated station replays). */
  observation?: LiveObservations;
  /** Spec'd detection block (present on calibrated station replays). */
  detection?: LiveDetection;
  severity?: string;
  confidence?: number | null;
  reason?: string;
  data_quality: { status: string; ml_eligible: boolean; reason?: string };
  anomaly: {
    detected: boolean;
    score: number | null;
    confidence: number | null;
    /** Ensemble-only: absent for calibrated station detectors. */
    availability?: string;
    /** Ensemble-only decision threshold. */
    threshold?: number | null;
    severity?: string | null;
    trigger?: string | null;
    method: string;
  };
  confidence_basis?: string | null;
  trigger?: string | null;
  freeze?: LiveFreezeEvidence | null;
  root_cause: { class: string | null; confidence: number | null; runner_up: string | null };
  evidence: LiveEvidence;
  explanation: { text: string | null; features: Array<Record<string, unknown>> };
  spatial_decision?: Record<string, string | null> | null;
}

export interface LiveAlert {
  type: "alert";
  event_type?: LiveEventType;
  alert_id: string;
  station_id: string;
  city: string;
  timestamp: string;
  sequence: number;
  status: string;
  /** Durable replay-store state (e.g. RECORDED); absent on the ensemble path. */
  record_status?: string;
  event: string;
  severity?: string;
  score: number | null;
  /** Ensemble-only decision threshold. */
  threshold?: number | null;
  detector?: string;
  root_cause: string | null;
  root_cause_basis?: string | null;
  confidence: number | null;
  runner_up?: string | null;
  trigger?: string | null;
  freeze?: LiveFreezeEvidence | null;
  reason?: string;
  observation?: LiveObservations;
  detection?: LiveDetection;
  contributing_factors?: string[];
  data_quality?: { status: string; ml_eligible: boolean; reason?: string };
  spatial_decision?: Record<string, string | null> | null;
  source_mode?: string;
  data_mode: string;
  summary: string;
}

export interface LiveConnection {
  type: "connection";
  event_type?: LiveEventType;
  status: string;
  data_mode: string;
  source_mode?: string;
}

export interface LiveReplayState {
  type: "replay_state";
  event_type?: LiveEventType;
  status: string;
  station_id?: string;
  split?: string;
  speed?: number;
  sequence: number;
  processed: number;
  anomalies: number;
  effective_speed?: number;
  data_mode: string;
}

export interface LiveError {
  type: "error";
  event_type?: LiveEventType;
  code: string;
  detail: string;
  data_mode: string;
}

export interface LiveComplete {
  type: "complete";
  event_type?: LiveEventType;
  station_id: string;
  split: string;
  processed: number;
  anomalies: number;
  duration_ms: number;
  effective_speed?: number;
  /** Replay alerts actually persisted for this run (station replays only). */
  alerts_recorded?: number;
  source_mode?: string;
  data_mode: string;
}

export type LiveEvent =
  LiveConnection | LiveReplayState | LiveReading | LiveAlert | LiveError | LiveComplete;

export interface ReplayStartParams {
  station_id: string;
  split: string;
  speed: number;
  limit?: number | null;
}

export function liveUrl(): string {
  const base = API_BASE_URL.trim();
  const wsBase = base.startsWith("https")
    ? `wss${base.slice(5)}`
    : base.startsWith("http")
      ? `ws${base.slice(4)}`
      : base;
  return `${wsBase.replace(/\/$/, "")}/api/v1/live`;
}

export interface LiveCallbacks {
  onEvent: (event: LiveEvent) => void;
  onOpen: () => void;
  onClose: (clean: boolean) => void;
}

/** Thin WebSocket wrapper: connect/disconnect/send, JSON parsing. */
export class LiveClient {
  private socket: WebSocket | null = null;
  private callbacks: LiveCallbacks | null = null;

  get isOpen(): boolean {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN;
  }

  connect(callbacks: LiveCallbacks): void {
    this.disconnect();
    this.callbacks = callbacks;
    const socket = new WebSocket(liveUrl());
    this.socket = socket;
    socket.onopen = () => this.callbacks?.onOpen();
    socket.onmessage = (message) => {
      try {
        this.callbacks?.onEvent(JSON.parse(String(message.data)) as LiveEvent);
      } catch {
        this.callbacks?.onEvent({
          type: "error",
          code: "protocol_error",
          detail: "Unparseable replay frame received.",
          data_mode: "historical_replay",
        });
      }
    };
    socket.onerror = () => {
      this.callbacks?.onEvent({
        type: "error",
        code: "connection_error",
        detail: "Replay socket error. The backend may be unreachable.",
        data_mode: "historical_replay",
      });
    };
    socket.onclose = (event) => {
      if (this.socket === socket) this.socket = null;
      this.callbacks?.onClose(event.wasClean);
    };
  }

  send(message: Record<string, unknown>): boolean {
    if (!this.isOpen || !this.socket) return false;
    try {
      this.socket.send(JSON.stringify(message));
      return true;
    } catch {
      return false;
    }
  }

  disconnect(): void {
    const socket = this.socket;
    this.socket = null;
    this.callbacks = null;
    try {
      socket?.close();
    } catch {
      // Already closed; nothing to do.
    }
  }
}
