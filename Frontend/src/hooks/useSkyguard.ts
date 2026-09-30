import { useMutation, useQuery } from "@tanstack/react-query";

import {
  getAlert,
  getAlerts,
  getDemoReadiness,
  getFaultSequence,
  getStationInvestigation,
  getStationTimeline,
  getEvaluationSummary,
  getHealth,
  getLiveAlerts,
  getLiveAlert,
  getLiveStations,
  getLiveStatus,
  getNetworkSummary,
  getStation,
  getStations,
  getStationHistory,
  probeObservation,
  startLive,
  startLiveDemo,
  stopLive,
  type HistoryVariable,
  type ProbePayload,
} from "@/lib/api";

/**
 * Server-state hooks for the SkyGuard dashboard (Phase 13).
 * All backend reads go through React Query here; components stay presentational.
 * No polling: historical replay is fetched on mount / on selection change.
 */

const STALE_MS = 30_000;

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    staleTime: STALE_MS,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useNetworkSummary() {
  return useQuery({
    queryKey: ["network-summary"],
    queryFn: getNetworkSummary,
    staleTime: STALE_MS,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useStations() {
  return useQuery({
    queryKey: ["stations"],
    queryFn: getStations,
    staleTime: STALE_MS,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useStation(stationId: string | null) {
  return useQuery({
    queryKey: ["station", stationId],
    queryFn: () => getStation(stationId as string),
    enabled: stationId !== null,
    staleTime: STALE_MS,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

/**
 * Full-period historical timeline (real observations + existing detector
 * events). Fetched on selection change only; no polling.
 */
export function useStationTimeline(stationId: string | null) {
  return useQuery({
    queryKey: ["station-timeline", stationId],
    queryFn: () => getStationTimeline(stationId as string),
    enabled: stationId !== null,
    staleTime: STALE_MS,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

/** Anchor a station against its audited neighbours (existing spatial layer). */
export function useStationInvestigation(stationId: string | null, at: string | null) {
  return useQuery({
    queryKey: ["station-investigation", stationId, at],
    queryFn: () => getStationInvestigation(stationId as string, at),
    enabled: stationId !== null,
    staleTime: STALE_MS,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

/**
 * Controlled fault demo. Runs only when the judge presses the button: the
 * backend replays real Delhi rows with benchmark injections applied, so the
 * result is deterministic and cached server-side.
 */
export function useFaultSequence() {
  return useMutation({
    mutationFn: () => getFaultSequence(),
    retry: false,
  });
}

export function useStationHistory(stationId: string | null, variable: HistoryVariable, hours = 24) {
  return useQuery({
    queryKey: ["station-history", stationId, variable, hours],
    queryFn: () => getStationHistory(stationId as string, variable, hours),
    enabled: stationId !== null,
    staleTime: STALE_MS,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

/** Full alert queue (single shared cache key) for badge, alert center, and investigations. */
export function useAlerts(limit = 1000) {
  return useQuery({
    queryKey: ["alerts", limit],
    queryFn: () => getAlerts(limit),
    staleTime: STALE_MS,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useAlert(alertId: string | null) {
  return useQuery({
    queryKey: ["alert", alertId],
    queryFn: () => getAlert(alertId as string),
    enabled: alertId !== null,
    staleTime: STALE_MS,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

/**
 * Judge-probe mutation. Never runs automatically: the page submits
 * explicitly. Result lives on the mutation (no global state), retry
 * re-submits the same payload.
 */
export function useProbeObservation() {
  return useMutation({
    mutationFn: (payload: ProbePayload) => probeObservation(payload),
    retry: false,
  });
}

/** Frozen benchmark + runtime evidence (read-only presentation layer). */
export function useEvaluation() {
  return useQuery({
    queryKey: ["evaluation-summary"],
    queryFn: getEvaluationSummary,
    staleTime: STALE_MS,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

/** Demo capability flags; failure never blocks the app (no mocks). */
export function useReadiness() {
  return useQuery({
    queryKey: ["demo-readiness"],
    queryFn: getDemoReadiness,
    staleTime: 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

/** Live ingestion state (polled while the page is open). */
export function useLiveStatus() {
  return useQuery({
    queryKey: ["live-status"],
    queryFn: getLiveStatus,
    staleTime: 5_000,
    refetchInterval: 10_000,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useLiveStations() {
  return useQuery({
    queryKey: ["live-stations"],
    queryFn: getLiveStations,
    staleTime: 5_000,
    refetchInterval: 10_000,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

export function useLiveAlerts() {
  return useQuery({
    queryKey: ["live-alerts"],
    queryFn: () => getLiveAlerts(),
    staleTime: 5_000,
    refetchInterval: 10_000,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}

/**
 * Count of open live alert episodes for the sidebar badge. Only active
 * (OPEN) episodes count — historical totals are never shown as a badge.
 */
export function useOpenLiveEpisodes(): number {
  const query = useLiveAlerts();
  const episodes = query.data?.episodes ?? [];
  let open = 0;
  for (const episode of episodes) {
    if (episode.status === "OPEN") open += 1;
  }
  return open;
}

export function useLiveAlert(alertId: string) {
  return useQuery({
    queryKey: ["live-alert", alertId],
    queryFn: () => getLiveAlert(alertId),
    enabled: alertId !== "",
    retry: 1,
  });
}

export function useStartLiveDemo() {
  return useMutation({
    mutationFn: startLiveDemo,
    retry: false,
  });
}

export function useStartLive() {
  return useMutation({
    mutationFn: startLive,
    retry: false,
  });
}

export function useStopLive() {
  return useMutation({
    mutationFn: stopLive,
    retry: false,
  });
}
