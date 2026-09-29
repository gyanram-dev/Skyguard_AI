import { useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "@/components/common";
import { normalizeStatus } from "@/lib/api";
import {
  cleanText,
  formatConfidence,
  formatDateTime,
  formatScore,
  formatTemp,
  formatTime,
} from "@/lib/format";
import { stationSourceLabel } from "@/lib/mapMeta";
import { cn } from "@/lib/utils";
import type { AlertSummary, StationSummary } from "@/lib/api";

/**
 * Capability chip: truthful per-station detection coverage. CONTEXT_ONLY
 * explicitly says "no detector verdict" instead of implying health.
 */
export function CapabilityChip({ station }: { station: StationSummary }) {
  const declared = station.capability?.detector_capability;
  const capability =
    declared === "FULL_TPR"
      ? "FULL T/P/RH"
      : declared === "PARTIAL"
        ? "PARTIAL"
        : declared === "CONTEXT_ONLY"
          ? "CONTEXT ONLY"
          : declared === "UNAVAILABLE"
            ? "UNAVAILABLE"
            : station.probe_available
              ? "FULL T/P/RH"
              : "CONTEXT ONLY";
  const tone =
    capability === "FULL T/P/RH"
      ? "bg-info-soft text-info"
      : capability === "PARTIAL"
        ? "bg-warning-soft text-warning-deep"
        : "bg-muted text-muted-foreground";
  return (
    <span
      className={cn("inline-block rounded-md px-1.5 py-0.5 text-[9px] font-extrabold", tone)}
      title={
        capability === "CONTEXT ONLY"
          ? "Real historical observations; no detector models cover this station — no anomaly verdict exists."
          : `Detector capability: ${capability}`
      }
    >
      {capability}
    </span>
  );
}

function NavigableRow({
  to,
  params,
  label,
  children,
}: {
  to: string;
  params: Record<string, string>;
  label: string;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  const go = () => navigate({ to, params } as never);
  return (
    <TableRow
      className="cursor-pointer"
      tabIndex={0}
      role="link"
      aria-label={label}
      onClick={go}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          go();
        }
      }}
    >
      {children}
    </TableRow>
  );
}

export function StationTable({ stations }: { stations: StationSummary[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Station</TableHead>
            <TableHead>City</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Capability</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Temp</TableHead>
            <TableHead className="text-right">Humidity</TableHead>
            <TableHead className="text-right">Pressure</TableHead>
            <TableHead className="text-right">Updated</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {stations.map((station) => (
            <NavigableRow
              key={station.station_id}
              to="/stations/$stationId"
              params={{ stationId: station.station_id }}
              label={`Open ${station.station_id} station detail`}
            >
              <TableCell className="font-extrabold">{station.station_id}</TableCell>
              <TableCell>{station.city}</TableCell>
              <TableCell className="text-[10px] font-semibold text-muted-foreground">
                {stationSourceLabel(station)}
              </TableCell>
              <TableCell>
                <CapabilityChip station={station} />
              </TableCell>
              <TableCell>
                <StatusBadge status={normalizeStatus(station.status, station.data_available)} />
              </TableCell>
              <TableCell className="text-right">
                {station.data_available ? formatTemp(station.temperature) : "—"}
              </TableCell>
              <TableCell className="text-right">
                {station.humidity !== null && station.humidity !== undefined
                  ? `${station.humidity.toFixed(1)}%`
                  : "—"}
              </TableCell>
              <TableCell className="text-right">
                {station.pressure !== null && station.pressure !== undefined
                  ? `${station.pressure.toFixed(1)}`
                  : "—"}
              </TableCell>
              <TableCell className="text-right text-muted-foreground">
                {formatDateTime(station.last_updated)}
              </TableCell>
            </NavigableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function AlertTable({
  alerts,
  basePath,
}: {
  alerts: AlertSummary[];
  basePath: "/alerts/$alertId" | "/investigations/$alertId";
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Source</TableHead>
            <TableHead>Station</TableHead>
            <TableHead>Sensor</TableHead>
            <TableHead>Event</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Score</TableHead>
            <TableHead>Root cause</TableHead>
            <TableHead className="text-right">Confidence</TableHead>
            <TableHead className="text-right">Duration</TableHead>
            <TableHead className="text-right">Time</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {alerts.map((alert) => {
            const live = alert.source_mode === "LIVE_ALERT";
            const replay = alert.source_mode === "REPLAY_ALERT";
            const to = live
              ? "/investigations/live/$alertId"
              : replay
                ? "/investigations/replay/$anomalyId"
                : basePath;
            const params = live
              ? { alertId: alert.alert_id }
              : replay
                ? { anomalyId: alert.alert_id }
                : { alertId: alert.alert_id };
            return (
              <NavigableRow
                key={alert.alert_id}
                to={to}
                params={params}
                label={`${live || replay ? "Open investigation" : "Review alert"} for ${alert.station_id} ${alert.event}`}
              >
                <TableCell className="text-[10px] text-muted-foreground">
                  {alert.source_mode ?? "HISTORICAL_ALERT"}
                </TableCell>
                <TableCell className="font-extrabold">{alert.station_id}</TableCell>
                <TableCell>{alert.sensor ?? "Not isolated"}</TableCell>
                <TableCell className="max-w-[220px] truncate">{alert.event}</TableCell>
                <TableCell>
                  <StatusBadge status={normalizeStatus(alert.status, true)} />
                </TableCell>
                <TableCell className="text-right">{formatScore(alert.anomaly_score)}</TableCell>
                <TableCell>{cleanText(alert.root_cause) ?? "—"}</TableCell>
                <TableCell className="text-right">
                  {alert.root_cause_confidence !== null && alert.root_cause_confidence !== undefined
                    ? formatConfidence(alert.root_cause_confidence)
                    : "—"}
                </TableCell>
                <TableCell className="text-right">
                  {alert.duration_seconds === undefined
                    ? "—"
                    : alert.duration_seconds === 0
                      ? "1 sample"
                      : `${Math.round(alert.duration_seconds / 60)} min`}
                </TableCell>
                <TableCell className="text-right text-muted-foreground">
                  {formatTime(alert.timestamp)}
                </TableCell>
              </NavigableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
