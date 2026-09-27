import { Link } from "@tanstack/react-router";

import { cn } from "@/lib/utils";
import { normalizeStatus, type StationSummary } from "@/lib/api";
import { formatDateTime, formatScore, formatTemp } from "@/lib/format";
import { StatusBadge } from "@/components/shared";

function formatNullable(value: number | null, suffix: string): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(1)}${suffix}`;
}

/**
 * Station table shared by the Stations page (full columns) and the
 * Network Health page (compact columns). All values come from the API.
 */
export function StationTable({
  stations,
  variant,
}: {
  stations: StationSummary[];
  variant: "full" | "compact";
}) {
  const full = variant === "full";
  return (
    <div className="overflow-x-auto">
      <div className={cn("min-w-[720px]", !full && "min-w-[560px]")}>
        <div
          className={cn(
            "grid gap-2 px-2.5 text-[9px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground",
            full
              ? "grid-cols-[84px_minmax(0,1fr)_110px_90px_90px_90px_90px_130px]"
              : "grid-cols-[84px_minmax(0,1fr)_110px_90px_130px]",
          )}
          aria-hidden="true"
        >
          <span>Station</span>
          <span>City</span>
          <span>Status</span>
          <span>Temp</span>
          {full && <span>Humidity</span>}
          {full && <span>Pressure</span>}
          {full && <span>Score</span>}
          <span className="text-right">Updated</span>
        </div>
        <div className="mt-1.5 space-y-1.5">
          {stations.map((station) => {
            const status = normalizeStatus(station.status, station.data_available);
            return (
              <Link
                key={station.station_id}
                to="/stations/$stationId"
                params={{ stationId: station.station_id }}
                className={cn(
                  "grid cursor-pointer items-center gap-2 rounded-xl border border-border bg-card px-2.5 py-2 text-left transition-colors hover:border-primary/30 hover:bg-info-soft/50",
                  full
                    ? "grid-cols-[84px_minmax(0,1fr)_110px_90px_90px_90px_90px_130px]"
                    : "grid-cols-[84px_minmax(0,1fr)_110px_90px_130px]",
                )}
              >
                <strong className="text-[11px] font-extrabold">{station.station_id}</strong>
                <span className="truncate text-[11px] font-semibold text-muted-foreground">
                  {station.city}
                </span>
                <span>
                  <StatusBadge status={status} />
                </span>
                <strong className="text-xs font-extrabold">
                  {station.data_available ? formatTemp(station.temperature) : "—"}
                </strong>
                {full && (
                  <span className="text-[11px] font-semibold text-muted-foreground">
                    {station.data_available ? formatNullable(station.humidity, "%") : "—"}
                  </span>
                )}
                {full && (
                  <span className="text-[11px] font-semibold text-muted-foreground">
                    {station.data_available ? formatNullable(station.pressure, "") : "—"}
                  </span>
                )}
                {full && (
                  <span className="text-[11px] font-semibold text-muted-foreground">
                    {formatScore(station.anomaly_score)}
                  </span>
                )}
                <time className="text-right text-[10px] font-medium text-muted-foreground">
                  {station.last_updated ? formatDateTime(station.last_updated) : "—"}
                </time>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
