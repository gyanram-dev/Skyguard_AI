import { API_BASE_URL } from "@/lib/api";

/**
 * Dedicated WebSocket layer for accelerated historical replay (Phase 16).
 * Transport + parsing only; streaming state lives in useLiveReplay.
 * The socket URL derives from VITE_API_BASE_URL (ws/wss); no hard-coded hosts.
 */

export type ConnectionState = "disconnected" | "connecting" | "connected" | "error";

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

export interface LiveReading {
  type: "reading";
  station_id: string;
  city: string;
  timestamp: string;
  sequence: number;
  data_mode: string;
  observations: LiveObservations;
  data_quality: { status: string; ml_eligible: boolean };
  anomaly: {
    detected: boolean;
    score: number | null;
    confidence: number | null;
    availability: string;
    threshold: number | null;
    method: string;
  };
  root_cause: { class: string | null; confidence: number | null; runner_up: string | null };
  evidence: {
    statistical: LiveComponentEvidence;
    isolation_forest: LiveComponentEvidence;
    lstm: LiveComponentEvidence;
    multivariate: Record<string, number | null>;
    spatial: Record<string, number | string | boolean | null>;
  };
  explanation: { text: string | null; features: Array<Record<string, unknown>> };
  spatial_decision?: Record<string, string | null> | null;
}

export interface LiveAlert {
  type: "alert";
  alert_id: string;
  station_id: string;
  city: string;
  timestamp: string;
  sequence: number;
  status: string;
  event: string;
  score: number | null;
  threshold: number | null;
  root_cause: string | null;
  confidence: number | null;
  runner_up: string | null;
  spatial_decision?: Record<string, string | null> | null;
  data_mode: string;
  summary: string;
}

export interface LiveConnection {
  type: "connection";
  status: string;
  data_mode: string;
}

export interface LiveReplayState {
  type: "replay_state";
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
  code: string;
  detail: string;
  data_mode: string;
}

export interface LiveComplete {
  type: "complete";
  station_id: string;
  split: string;
  processed: number;
  anomalies: number;
  duration_ms: number;
  effective_speed?: number;
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
