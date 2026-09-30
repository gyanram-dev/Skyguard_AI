import { ObservationBadge, observationState } from "@/components/replay/observation";
import { formatTime } from "@/lib/format";
import type { LiveReading } from "@/lib/live";
import { cn } from "@/lib/utils";

const DEFAULT_LIMIT = 12;

/**
 * Replay timeline: streamed observations in their actual replay order
 * (oldest → newest). Anomaly rows carry the only strong colour; normal rows
 * stay visually quiet, and no row is ever labelled "Offline" — a historical
 * replay has no live connection state.
 */
export function ReplayTimeline({
  readings,
  limit = DEFAULT_LIMIT,
}: {
  readings: LiveReading[];
  limit?: number;
}) {
  const rows = readings.slice(-limit);
  return (
    <div className="min-w-0" aria-label="Replay timeline">
      <div className="flex items-baseline justify-between gap-2">
        <p className="section-kicker">Replay timeline</p>
        <span className="text-[9px] text-muted-foreground">
          {readings.length > rows.length
            ? `last ${rows.length} of ${readings.length}`
            : `${rows.length} observation${rows.length === 1 ? "" : "s"}`}
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="mt-1.5 text-[10px] text-muted-foreground" role="status">
          Start Historical Replay to process observations.
        </p>
      ) : (
        <ol className="mt-1.5 max-h-[236px] space-y-1 overflow-y-auto pr-0.5">
          {rows.map((reading) => {
            const state = observationState(reading);
            const anomalous = state === "anomaly";
            return (
              <li
                key={reading.sequence}
                className={cn(
                  "flex min-w-0 items-center gap-2 rounded-lg border-l-2 px-2 py-1 text-[10px]",
                  anomalous
                    ? "border-anomaly bg-anomaly-soft/60"
                    : "border-transparent bg-muted/40",
                )}
                title={`${reading.station_id} · ${reading.timestamp}${
                  state === "data-quality" ? ` · data quality ${reading.data_quality.status}` : ""
                }`}
              >
                <time className="shrink-0 font-semibold tabular-nums text-muted-foreground">
                  {formatTime(reading.timestamp)}
                </time>
                <strong className="shrink-0 font-extrabold">{reading.station_id}</strong>
                <span className="ml-auto shrink-0">
                  <ObservationBadge state={state} />
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
