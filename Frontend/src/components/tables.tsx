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
import type { AlertSummary, StationSummary } from "@/lib/api";

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
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Temp</TableHead>
            <TableHead className="text-right">Humidity</TableHead>
            <TableHead className="text-right">Pressure</TableHead>
            <TableHead className="text-right">Score</TableHead>
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
              <TableCell className="text-right">{formatScore(station.anomaly_score)}</TableCell>
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
            <TableHead>Station</TableHead>
            <TableHead>Event</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Score</TableHead>
            <TableHead>Root cause</TableHead>
            <TableHead className="text-right">Confidence</TableHead>
            <TableHead className="text-right">Time</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {alerts.map((alert) => (
            <NavigableRow
              key={alert.alert_id}
              to={basePath}
              params={{ alertId: alert.alert_id }}
              label={`Open investigation for ${alert.station_id} ${alert.event}`}
            >
              <TableCell className="font-extrabold">{alert.station_id}</TableCell>
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
              <TableCell className="text-right text-muted-foreground">
                {formatTime(alert.timestamp)}
              </TableCell>
            </NavigableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
