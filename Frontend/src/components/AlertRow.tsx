import { Link } from "@tanstack/react-router";

import { cn } from "@/lib/utils";
import { normalizeStatus, type AlertSummary } from "@/lib/api";
import { formatScore, formatTime } from "@/lib/format";
import { StatusBadge } from "@/components/shared";

/**
 * Alert queue row shared by the Alerts and Investigations pages.
 * Navigates to the per-page detail route via the `to` pattern.
 */
export function AlertRow({
  alert,
  selected,
  to,
}: {
  alert: AlertSummary;
  selected: boolean;
  to: "/alerts/$alertId" | "/investigations/$alertId";
}) {
  const status = normalizeStatus(alert.status, true);
  return (
    <Link
      to={to}
      params={{ alertId: alert.alert_id }}
      aria-current={selected ? "true" : undefined}
      title={alert.summary}
      className={cn(
        "grid w-full cursor-pointer grid-cols-[88px_minmax(0,1fr)_104px_128px_60px] items-center gap-2 rounded-xl border px-2.5 py-2 text-left transition-colors",
        selected
          ? "border-primary/50 bg-info-soft"
          : "border-border bg-card hover:border-primary/30 hover:bg-info-soft/50",
      )}
    >
      <strong className="text-[11px] font-extrabold">{alert.station_id}</strong>
      <span className="truncate text-[11px] font-semibold text-muted-foreground">
        {alert.event}
      </span>
      <strong
        className="text-xs font-extrabold"
        title="Anomaly score — open the detail view for observed readings"
      >
        {formatScore(alert.anomaly_score)}
      </strong>
      <span>
        <StatusBadge status={status} />
      </span>
      <time className="text-right text-[10px] font-medium text-muted-foreground">
        {formatTime(alert.timestamp)}
      </time>
    </Link>
  );
}

export function AlertListHeader() {
  return (
    <div
      className="grid grid-cols-[88px_minmax(0,1fr)_104px_128px_60px] gap-2 px-2.5 text-[9px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground"
      aria-hidden="true"
    >
      <span>Station</span>
      <span>Event</span>
      <span>Reading</span>
      <span>Status</span>
      <span className="text-right">Time</span>
    </div>
  );
}
