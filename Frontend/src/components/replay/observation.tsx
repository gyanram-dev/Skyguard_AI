import { cn } from "@/lib/utils";
import type { LiveReading } from "@/lib/live";

/**
 * How a streamed historical observation is presented.
 *
 * Historical replay is NOT a live station connection, so an ordinary
 * observation is NORMAL — never "Offline". `data-quality` is the backend's own
 * signal (`data_quality.ml_eligible === false`): the row arrived but could not
 * be analysed by the detector, which is a different statement from
 * connectivity.
 */
export type ObservationState = "anomaly" | "normal" | "data-quality";

export function observationState(reading: LiveReading): ObservationState {
  if (reading.anomaly.detected) return "anomaly";
  if (reading.data_quality.ml_eligible !== true) return "data-quality";
  return "normal";
}

export const observationStateLabel: Record<ObservationState, string> = {
  anomaly: "ANOMALY DETECTED",
  normal: "NORMAL",
  "data-quality": "DATA QUALITY ISSUE",
};

const STATE_TONE: Record<ObservationState, string> = {
  anomaly: "status-anomaly",
  normal: "status-historical",
  "data-quality": "status-review",
};

/** Compact state badge for a historical observation (no connectivity claim). */
export function ObservationBadge({
  state,
  className,
}: {
  state: ObservationState;
  className?: string;
}) {
  return (
    <span className={cn("status-badge", STATE_TONE[state], className)}>
      <span className="status-dot" />
      {observationStateLabel[state]}
    </span>
  );
}
