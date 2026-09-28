import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type {
  DQPreview,
  UploadAnalysisResult,
  UploadAnomalyRecord,
  UploadResponse,
} from "@/lib/api";

interface UploadSessionValue {
  session: UploadResponse | null;
  preview: DQPreview | null;
  result: UploadAnalysisResult | null;
  selectedAnomaly: UploadAnomalyRecord | null;
  setSession: (session: UploadResponse | null) => void;
  setPreview: (preview: DQPreview | null) => void;
  setResult: (result: UploadAnalysisResult | null) => void;
  setSelectedAnomaly: (anomaly: UploadAnomalyRecord | null) => void;
  reset: () => void;
}

const UploadSessionContext = createContext<UploadSessionValue | null>(null);

/**
 * Application-level upload-analysis session (Phase 19B pattern). Mounted
 * once inside AppShell above the route Outlet, so navigating Results ->
 * anomaly -> investigation -> Back never loses the analysis. A new upload
 * replaces the session explicitly; nothing else clears it.
 */
export function UploadSessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<UploadResponse | null>(null);
  const [preview, setPreview] = useState<DQPreview | null>(null);
  const [result, setResult] = useState<UploadAnalysisResult | null>(null);
  const [selectedAnomaly, setSelectedAnomaly] = useState<UploadAnomalyRecord | null>(null);

  const value = useMemo<UploadSessionValue>(
    () => ({
      session,
      preview,
      result,
      selectedAnomaly,
      setSession,
      setPreview,
      setResult,
      setSelectedAnomaly,
      reset: () => {
        setSession(null);
        setPreview(null);
        setResult(null);
        setSelectedAnomaly(null);
      },
    }),
    [session, preview, result, selectedAnomaly],
  );

  return <UploadSessionContext.Provider value={value}>{children}</UploadSessionContext.Provider>;
}

export function useUploadSession(): UploadSessionValue {
  const value = useContext(UploadSessionContext);
  if (!value) {
    throw new Error("useUploadSession must be used inside UploadSessionProvider.");
  }
  return value;
}
