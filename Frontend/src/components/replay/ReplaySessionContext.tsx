import { createContext, useContext, useMemo } from "react";
import type { ReactNode } from "react";

import { useLiveReplay, type LiveReplay } from "@/hooks/useLiveReplay";

interface ReplaySessionValue {
  live: LiveReplay;
}

const ReplaySessionContext = createContext<ReplaySessionValue | null>(null);

/**
 * Application-level replay session. Mounted once inside AppShell, above the
 * route Outlet, so SPA navigation (Overview <-> investigations <-> stations
 * ...) never unmounts the hook, never drops the WebSocket, and never clears
 * streamed readings/anomalies/counters. Only an explicit Start begins a new
 * session (clearing the previous one); full browser refresh still resets,
 * which is expected for an ephemeral live stream. Anomaly selection is
 * URL-driven (/investigations/replay/$anomalyId) against the stored session
 * payloads.
 */
export function ReplaySessionProvider({ children }: { children: ReactNode }) {
  const live = useLiveReplay();

  const value = useMemo<ReplaySessionValue>(() => ({ live }), [live]);

  return <ReplaySessionContext.Provider value={value}>{children}</ReplaySessionContext.Provider>;
}

export function useReplaySession(): ReplaySessionValue {
  const value = useContext(ReplaySessionContext);
  if (!value) {
    throw new Error("useReplaySession must be used inside ReplaySessionProvider.");
  }
  return value;
}
