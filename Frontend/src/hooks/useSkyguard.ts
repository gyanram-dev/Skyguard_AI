import { useMutation, useQuery } from "@tanstack/react-query";

import {
  getAlert,
  getAlerts,
  getEvaluationSummary,
  getHealth,
  getNetworkSummary,
  getStation,
  getStations,
  getStationHistory,
  probeObservation,
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
