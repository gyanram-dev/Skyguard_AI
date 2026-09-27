import { StatusBadge } from "@/components/common";
import { formatTemp, formatTime } from "@/lib/format";
import { normalizeStatus } from "@/lib/api";
import type { LiveAlert, LiveReading } from "@/lib/live";

/** Compact streamed-event feed (dataset timestamps, never the local clock). */
export function LiveEventFeed({
  readings,
  limit = 6,
}: {
  readings: LiveReading[];
  limit?: number;
}) {
  const rows = readings.slice(-limit).reverse();
  if (rows.length === 0) {
    return (
      <p className="text-[10px] text-muted-foreground" role="status">
        No streamed events yet — press Start to begin the replay.
      </p>
    );
  }
  return (
    <ul className="min-w-0 flex-1 space-y-1" aria-label="Live replay event feed">
      {rows.map((reading) => {
        const anomalous = reading.anomaly.detected;
        const known = !!reading.root_cause.class && reading.root_cause.class !== "UNKNOWN";
        const status = anomalous
          ? known
            ? "anomaly"
            : "review"
          : reading.data_quality.ml_eligible
            ? "healthy"
            : "offline";
        return (
          <li
            key={`r${reading.sequence}`}
            className="flex items-center gap-2 text-[10px]"
            title={`${reading.station_id} · ${reading.timestamp} · score ${reading.anomaly.score ?? "—"}`}
          >
            <time className="shrink-0 font-semibold text-muted-foreground">
              {formatTime(reading.timestamp)}
            </time>
            <strong className="shrink-0 font-extrabold">{reading.station_id}</strong>
            <span className="shrink-0 font-semibold">
              {formatTemp(reading.observations.temperature_c)}
            </span>
            <span className="ml-auto">
              <StatusBadge status={normalizeStatus(status, true)} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}
