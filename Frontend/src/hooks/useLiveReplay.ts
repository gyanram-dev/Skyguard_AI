import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  LiveClient,
  type ConnectionState,
  type LiveAlert,
  type LiveEvent,
  type LiveReading,
  type ReplayStartParams,
} from "@/lib/live";

export type ReplayStatus = "idle" | "preparing" | "running" | "paused" | "stopped" | "completed";

export interface ReplaySummary {
  status: ReplayStatus;
  stationId: string | null;
  split: string | null;
  speed: number | null;
  effectiveSpeed: number | null;
  sequence: number;
  processed: number;
  anomalies: number;
}

export interface CompleteInfo {
  stationId: string;
  split: string;
  processed: number;
  anomalies: number;
  durationMs: number;
  effectiveSpeed: number | null;
}

const MAX_READINGS = 30;
const MAX_ALERTS = 50;
const MAX_RECONNECTS = 3;
const RECONNECT_DELAYS = [1000, 2000, 4000];

/**
 * Accelerated historical replay over WebSocket (Phase 16).
 * Local streaming state only (never the React Query cache): connection,
 * replay status, latest readings per station, recent readings ring, and a
 * deduplicated, bounded live-alert list. No auto-start, no auto-reconnect
 * after deliberate stop, bounded reconnects on mid-replay drops.
 */
export function useLiveReplay() {
  const [connection, setConnection] = useState<ConnectionState>("disconnected");
  const [replay, setReplay] = useState<ReplaySummary>({
    status: "idle",
    stationId: null,
    split: null,
    speed: null,
    effectiveSpeed: null,
    sequence: 0,
    processed: 0,
    anomalies: 0,
  });
  const [latestByStation, setLatestByStation] = useState<Record<string, LiveReading>>({});
  const [recentReadings, setRecentReadings] = useState<LiveReading[]>([]);
  const [liveAlerts, setLiveAlerts] = useState<LiveAlert[]>([]);
  const [anomalyMap, setAnomalyMap] = useState<Record<string, LiveReading>>({});
  const [obsCount, setObsCount] = useState(0);
  const [runId, setRunId] = useState(0);
  const [completeInfo, setCompleteInfo] = useState<CompleteInfo | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const clientRef = useRef<LiveClient | null>(null);
  const manualRef = useRef(false);
  const reconnectsRef = useRef(0);
  const reconnectTimerRef = useRef<number | null>(null);
  const stateRef = useRef({ connection, replay });
  stateRef.current = { connection, replay };
  // Session-owned pairing state: exact streamed payloads keyed by alert_id,
  // plus the set of seen reading sequences for duplicate-proof counting.
  // Cleared on every Start; never merged with persistent REST alerts.
  const sessionRef = useRef<{ seen: Set<number> }>({ seen: new Set() });
  const readingsRef = useRef<LiveReading[]>([]);

  useEffect(
    () => () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      clientRef.current?.disconnect();
    },
    [],
  );

  const handleEvent = useCallback((event: LiveEvent) => {
    if (event.type === "connection") {
      reconnectsRef.current = 0;
      return;
    }
    if (event.type === "replay_state") {
      setReplay((prev) => ({
        ...prev,
        status: event.status as ReplayStatus,
        stationId: event.station_id ?? prev.stationId,
        split: event.split ?? prev.split,
        speed: event.speed ?? prev.speed,
        effectiveSpeed: event.effective_speed ?? prev.effectiveSpeed,
        sequence: event.sequence,
        processed: event.processed,
        anomalies: event.anomalies,
      }));
      if (event.status === "stopped" || event.status === "completed") {
        manualRef.current = true;
      }
      return;
    }
    if (event.type === "reading") {
      // Duplicate deliveries (same sequence) update the latest view but are
      // never counted twice in the session summary.
      const isNew = !sessionRef.current.seen.has(event.sequence);
      if (isNew) {
        sessionRef.current.seen.add(event.sequence);
        setObsCount((count) => count + 1);
      }
      setLatestByStation((prev) => ({ ...prev, [event.station_id]: event }));
      setRecentReadings((prev) => {
        const next = isNew
          ? [...prev.slice(-(MAX_READINGS - 1)), event]
          : prev.map((row) => (row.sequence === event.sequence ? event : row));
        readingsRef.current = next;
        return next;
      });
      setReplay((prev) => ({ ...prev, sequence: event.sequence }));
      return;
    }
    if (event.type === "alert") {
      const reading = readingsRef.current.find(
        (row) => row.station_id === event.station_id && row.sequence === event.sequence,
      );
      setLiveAlerts((prev) => {
        if (prev.some((alert) => alert.alert_id === event.alert_id)) return prev;
        return [event, ...prev].slice(0, MAX_ALERTS);
      });
      if (reading) {
        setAnomalyMap((prev) =>
          prev[event.alert_id] ? prev : { ...prev, [event.alert_id]: reading },
        );
      }
      return;
    }
    if (event.type === "complete") {
      setCompleteInfo({
        stationId: event.station_id,
        split: event.split,
        processed: event.processed,
        anomalies: event.anomalies,
        durationMs: event.duration_ms,
        effectiveSpeed: event.effective_speed ?? null,
      });
      manualRef.current = true;
      return;
    }
    if (event.type === "error") {
      setNotice(`${event.detail} (code: ${event.code})`);
    }
  }, []);

  const connect = useCallback(() => {
    if (clientRef.current?.isOpen) return;
    manualRef.current = false;
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    setNotice(null);
    setConnection("connecting");
    const client = new LiveClient();
    clientRef.current = client;
    client.connect({
      onEvent: handleEvent,
      onOpen: () => setConnection("connected"),
      onClose: (clean) => {
        clientRef.current = null;
        if (manualRef.current || clean) {
          setConnection("disconnected");
          return;
        }
        const { replay: rep } = stateRef.current;
        const active =
          rep.status === "running" || rep.status === "paused" || rep.status === "preparing";
        if (!active || reconnectsRef.current >= MAX_RECONNECTS) {
          setNotice(
            active
              ? "Replay connection lost. Reconnect attempts exhausted — press Start to retry."
              : "Replay connection lost.",
          );
          setConnection("disconnected");
          return;
        }
        const delay =
          RECONNECT_DELAYS[Math.min(reconnectsRef.current, RECONNECT_DELAYS.length - 1)] ?? 4000;
        reconnectsRef.current += 1;
        setConnection("connecting");
        reconnectTimerRef.current = window.setTimeout(() => {
          reconnectTimerRef.current = null;
          connect();
        }, delay);
      },
    });
  }, [handleEvent]);

  const disconnect = useCallback(() => {
    manualRef.current = true;
    reconnectsRef.current = 0;
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    clientRef.current?.disconnect();
    clientRef.current = null;
    setConnection("disconnected");
  }, []);

  const sendStart = useCallback(
    (params: ReplayStartParams) => {
      const message: Record<string, unknown> = {
        action: "start",
        station_id: params.station_id,
        split: params.split,
        speed: params.speed,
      };
      if (params.limit != null) message["limit"] = params.limit;
      if (clientRef.current?.isOpen) {
        clientRef.current.send(message);
        return;
      }
      connect();
      const waiter = window.setInterval(() => {
        if (clientRef.current?.isOpen) {
          window.clearInterval(waiter);
          clientRef.current?.send(message);
        }
      }, 150);
      window.setTimeout(() => window.clearInterval(waiter), 10000);
    },
    [connect],
  );

  const start = useCallback(
    (params: ReplayStartParams) => {
      // New session: clear every previous replay artifact (readings, alerts,
      // exact payloads, counters). Persistent REST alerts are untouched.
      sessionRef.current = { seen: new Set() };
      readingsRef.current = [];
      setNotice(null);
      setCompleteInfo(null);
      setLiveAlerts([]);
      setAnomalyMap({});
      setObsCount(0);
      setRecentReadings([]);
      setLatestByStation({});
      setRunId((id) => id + 1);
      setReplay({
        status: "idle",
        stationId: params.station_id,
        split: params.split,
        speed: params.speed,
        effectiveSpeed: null,
        sequence: 0,
        processed: 0,
        anomalies: 0,
      });
      manualRef.current = false;
      sendStart(params);
    },
    [sendStart],
  );

  const pause = useCallback(() => {
    clientRef.current?.send({ action: "pause" });
  }, []);

  const resume = useCallback(() => {
    clientRef.current?.send({ action: "resume" });
  }, []);

  const stop = useCallback(() => {
    manualRef.current = true;
    clientRef.current?.send({ action: "stop" });
  }, []);

  const setSpeed = useCallback((value: number) => {
    setReplay((prev) => ({ ...prev, speed: value }));
    clientRef.current?.send({ action: "speed", value });
  }, []);

  const clearNotice = useCallback(() => setNotice(null), []);

  const actions = useMemo(
    () => ({ connect, disconnect, start, pause, resume, stop, setSpeed, clearNotice }),
    [connect, disconnect, start, pause, resume, stop, setSpeed, clearNotice],
  );

  const summary = useMemo(
    () => ({
      observations: obsCount,
      anomalies: liveAlerts.length,
      normal: Math.max(0, obsCount - liveAlerts.length),
    }),
    [obsCount, liveAlerts.length],
  );

  return {
    connection,
    replay,
    latestByStation,
    recentReadings,
    liveAlerts,
    anomalyMap,
    summary,
    runId,
    completeInfo,
    notice,
    ...actions,
  };
}

export type LiveReplay = ReturnType<typeof useLiveReplay>;
