import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { useLiveReplay, type LiveReplay } from "@/hooks/useLiveReplay";
import type { AlertSummary } from "@/lib/api";
import type { LiveReading } from "@/lib/live";

export interface LivePreviewSelection {
  summary: AlertSummary;
  reading: LiveReading;
}

interface ReplaySessionValue {
  live: LiveReplay;
  livePreview: LivePreviewSelection | null;
  setLivePreview: (selection: LivePreviewSelection | null) => void;
}

const ReplaySessionContext = createContext<ReplaySessionValue | null>(null);

/**
 * Application-level replay session. Mounted once inside AppShell, above the
 * route Outlet, so SPA navigation (Overview <-> Investigations <-> Stations
 * ...) never unmounts the hook, never drops the WebSocket, and never clears
 * streamed readings/anomalies/counters. Only an explicit Start begins a new
 * session (clearing the previous one); full browser refresh still resets,
 * which is expected for an ephemeral live stream.
 */
export function ReplaySessionProvider({ children }: { children: ReactNode }) {
  const live = useLiveReplay();
  const [livePreview, setLivePreview] = useState<LivePreviewSelection | null>(null);

  // A new replay run owns a fresh session: drop the previous streamed preview.
  // Stop/completion/disconnect keep existing state for inspection.
  useEffect(() => {
    setLivePreview(null);
  }, [live.runId]);

  const value = useMemo<ReplaySessionValue>(
    () => ({ live, livePreview, setLivePreview }),
    [live, livePreview],
  );

  return <ReplaySessionContext.Provider value={value}>{children}</ReplaySessionContext.Provider>;
}

export function useReplaySession(): ReplaySessionValue {
  const value = useContext(ReplaySessionContext);
  if (!value) {
    throw new Error("useReplaySession must be used inside ReplaySessionProvider.");
  }
  return value;
}
