import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState, StatusBadge } from "@/components/common";
import { cn } from "@/lib/utils";
import { cleanText, errorMessage, formatConfidence, formatScore, formatTime } from "@/lib/format";
import { normalizeStatus, type AlertSummary, type DisplayStatus } from "@/lib/api";

/** A triage row plus the honest source label derived from the live mode. */
type TriageAlert = AlertSummary & { sourceLabel: string };
import { useAlerts, useLiveAlerts } from "@/hooks/useSkyguard";
import { useReplaySession } from "@/components/replay/ReplaySessionContext";

export const Route = createFileRoute("/_app/alerts/")({
  head: () => ({
    meta: [{ title: "Alerts | SkyGuard AI" }],
  }),
  component: AlertsPage,
});

/**
 * Triage filters. Alerts is a "what needs attention?" queue: it never renders
 * the SHAP panels or full evidence bundle that belong to Investigations.
 */
type TriageFilter = "all" | "active" | "resolved" | "historical" | "replay" | "live" | "root_cause";

const triageFilters: Array<{ value: TriageFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "resolved", label: "Resolved" },
  { value: "historical", label: "Historical" },
  { value: "replay", label: "Replay" },
  { value: "live", label: "Live" },
  { value: "root_cause", label: "Root cause" },
];

function sourceOf(alert: AlertSummary): "historical" | "replay" | "live" {
  if (alert.source_mode === "LIVE_ALERT") return "live";
  if (alert.source_mode === "REPLAY_ALERT") return "replay";
  return "historical";
}

function isResolved(alert: AlertSummary): boolean {
  const status = (alert.status ?? "").toLowerCase();
  return status === "resolved" || status === "closed";
}

function matchesFilter(alert: AlertSummary, filter: TriageFilter): boolean {
  switch (filter) {
    case "all":
      return true;
    case "active":
      return !isResolved(alert);
    case "resolved":
      return isResolved(alert);
    case "historical":
    case "replay":
    case "live":
      return sourceOf(alert) === filter;
    case "root_cause": {
      const cause = cleanText(alert.root_cause);
      return cause !== null && cause.toUpperCase() !== "UNKNOWN";
    }
    default:
      return true;
  }
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return formatTime(iso);
  const deltaMs = Date.now() - then;
  if (deltaMs < 0) return formatTime(iso);
  const minutes = Math.floor(deltaMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} d ago`;
  return formatTime(iso);
}

function durationLabel(seconds: number | undefined): string {
  if (seconds === undefined || seconds === null) return "—";
  if (seconds <= 0) return "1 sample";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

const sourceTone: Record<"historical" | "replay" | "live", string> = {
  historical: "bg-muted text-muted-foreground",
  replay: "bg-warning-soft text-warning-deep",
  live: "bg-success-soft text-success-deep",
};

function AlertsPage() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<TriageFilter>("all");
  const alertsQuery = useAlerts(1000);
  const liveAlertsQuery = useLiveAlerts();
  const { live: replay } = useReplaySession();
  const navigate = useNavigate();

  const alerts = useMemo<TriageAlert[]>(() => {
    const historical: TriageAlert[] = (alertsQuery.data?.alerts ?? []).map((alert) => ({
      ...alert,
      sourceLabel: "HISTORICAL",
    }));
    // Persisted live episodes are labelled by the actual live mode: scripted
    // demos must never read as IMD data.
    const liveMode = liveAlertsQuery.data?.mode ?? null;
    const liveLabel = liveMode === "LIVE_IMD" ? "LIVE" : "CONTROLLED LIVE";
    const liveEpisodes: TriageAlert[] = (liveAlertsQuery.data?.episodes ?? []).map((episode) => ({
      alert_id: episode.alert_id,
      station_id: episode.station_id,
      source_mode: "LIVE_ALERT",
      sensor: "Live observation",
      timestamp: episode.last_seen_at,
      status: episode.status === "OPEN" ? "anomaly" : "resolved",
      event: episode.interpretation,
      anomaly_score: episode.score,
      root_cause: episode.interpretation,
      root_cause_confidence: null,
      duration_seconds: Math.max(
        0,
        (Date.parse(episode.last_seen_at) - Date.parse(episode.started_at)) / 1000,
      ),
      summary: `${episode.interpretation} · ${episode.detection_count} observations`,
      sourceLabel: liveLabel,
    }));
    const replayAlerts: TriageAlert[] = replay.liveAlerts.map((alert) => ({
      alert_id: alert.alert_id,
      station_id: alert.station_id,
      source_mode: "REPLAY_ALERT",
      sensor: "Replay observation",
      timestamp: alert.timestamp,
      status: alert.status,
      event: alert.event,
      anomaly_score: alert.score,
      root_cause: alert.root_cause,
      root_cause_confidence: alert.confidence,
      duration_seconds: 0,
      summary: alert.summary,
      sourceLabel: "REPLAY",
    }));
    return [...historical, ...liveEpisodes, ...replayAlerts].sort((a, b) =>
      b.timestamp.localeCompare(a.timestamp),
    );
  }, [alertsQuery.data, liveAlertsQuery.data, replay.liveAlerts]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return alerts.filter((alert) => {
      if (!matchesFilter(alert, filter)) return false;
      if (term === "") return true;
      return (
        alert.station_id.toLowerCase().includes(term) ||
        alert.event.toLowerCase().includes(term) ||
        (cleanText(alert.root_cause) ?? "").toLowerCase().includes(term)
      );
    });
  }, [alerts, search, filter]);

  // The API pages: `returned` may be smaller than `total`. Counts below are
  // therefore labelled as "loaded" and only claimed as totals when the backend
  // confirms the page was not capped.
  const paging = useMemo(() => {
    const historicalReturned = alertsQuery.data?.returned ?? 0;
    const storedTotal = alertsQuery.data?.total ?? historicalReturned;
    const limit = alertsQuery.data?.limit ?? 0;
    return { historicalReturned, storedTotal, limit, capped: storedTotal > historicalReturned };
  }, [alertsQuery.data]);

  const counts = useMemo(() => {
    const active = alerts.filter((alert) => !isResolved(alert)).length;
    return { loaded: alerts.length, active, resolved: alerts.length - active };
  }, [alerts]);

  const filtersActive = search.trim() !== "" || filter !== "all";

  const openAlert = (alert: AlertSummary) => {
    const source = sourceOf(alert);
    if (source === "live") {
      navigate({
        to: "/investigations/live/$alertId",
        params: { alertId: alert.alert_id },
      });
      return;
    }
    if (source === "replay") {
      navigate({
        to: "/investigations/replay/$anomalyId",
        params: { anomalyId: alert.alert_id },
      });
      return;
    }
    navigate({ to: "/alerts/$alertId", params: { alertId: alert.alert_id } });
  };

  return (
    <>
      <section
        className="panel flex flex-wrap items-center gap-2 p-3"
        aria-label="Alert triage summary"
      >
        <div className="min-w-0">
          <p className="section-kicker">Triage queue</p>
          <h1 className="mt-0.5 text-lg font-extrabold">What needs attention?</h1>
        </div>{" "}
        <div className="ml-auto flex flex-wrap items-center gap-2 text-[10px] font-bold">
          <span className="rounded-full bg-anomaly-soft px-2.5 py-1 text-anomaly-deep">
            {alertsQuery.isPending ? "…" : counts.active} active loaded
          </span>
          <span className="rounded-full bg-muted px-2.5 py-1 text-muted-foreground">
            {alertsQuery.isPending ? "…" : counts.resolved} resolved loaded
          </span>
          <span className="rounded-full bg-muted px-2.5 py-1 text-muted-foreground">
            {alertsQuery.isPending
              ? "…"
              : paging.capped
                ? `${paging.historicalReturned} shown of ${paging.storedTotal} stored`
                : `${paging.storedTotal} stored`}
          </span>
        </div>
        <p className="w-full text-[10px] text-muted-foreground">
          Operationally compact. Open an alert to review or jump straight to the evidence workspace
          — the full analysis lives in Investigations.
        </p>
        {paging.capped && (
          <p className="w-full text-[10px] text-muted-foreground">
            The API returns the most recent {paging.limit} stored alerts (there are{" "}
            {paging.storedTotal}). Counts above describe the loaded window, not the full history.
          </p>
        )}
      </section>

      <section className="panel flex flex-wrap items-center gap-2 p-3" aria-label="Alert filters">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by station, event or root cause…"
            aria-label="Search alerts"
            className="pl-8"
          />
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Triage filter">
          {triageFilters.map((entry) => (
            <Button
              key={entry.value}
              size="sm"
              variant={filter === entry.value ? "default" : "outline"}
              onClick={() => setFilter(entry.value)}
              aria-pressed={filter === entry.value}
              className={cn(filter !== entry.value && "bg-card")}
            >
              {entry.label}
            </Button>
          ))}
        </div>
        {filtersActive && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setSearch("");
              setFilter("all");
            }}
          >
            <X />
            Clear
          </Button>
        )}
      </section>

      {(alertsQuery.isPending || liveAlertsQuery.isPending) && (
        <LoadingState message="Loading alerts…" />
      )}
      {alertsQuery.isError && (
        <ErrorState
          message={errorMessage(alertsQuery.error)}
          onRetry={() => alertsQuery.refetch()}
        />
      )}
      {!alertsQuery.isPending && !alertsQuery.isError && filtered.length === 0 && (
        <EmptyState
          title="No alerts match"
          message={
            alerts.length === 0
              ? "The API returned no alerts for this operating mode."
              : "No alerts match the current search and filters."
          }
        />
      )}
      {!alertsQuery.isPending && !alertsQuery.isError && filtered.length > 0 && (
        <section className="space-y-1.5" aria-label="Alert queue">
          {filtered.map((alert) => (
            <TriageRow
              key={alert.alert_id}
              alert={alert}
              onOpen={() => openAlert(alert)}
              onInvestigate={() => openAlert(alert)}
            />
          ))}
        </section>
      )}
    </>
  );
}

function TriageRow({
  alert,
  onOpen,
  onInvestigate,
}: {
  alert: TriageAlert;
  onOpen: () => void;
  onInvestigate: () => void;
}) {
  const status: DisplayStatus = normalizeStatus(alert.status, true);
  const source = sourceOf(alert);
  const cause = cleanText(alert.root_cause) ?? "Not diagnosed";
  const resolved = isResolved(alert);

  return (
    <article
      className="panel grid cursor-pointer grid-cols-1 gap-2 p-3 transition-colors hover:border-primary/30 hover:bg-info-soft/40 xl:grid-cols-[150px_minmax(0,1fr)_auto]"
      role="link"
      tabIndex={0}
      aria-label={`Open alert ${alert.event} at ${alert.station_id}`}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
    >
      <div className="min-w-0">
        <p className="text-sm font-extrabold leading-tight">{alert.station_id}</p>
        <p className="mt-0.5 text-[10px] font-semibold text-muted-foreground">
          {alert.sensor ?? "Sensor not isolated"}
        </p>
        <span
          className={cn(
            "mt-1 inline-block rounded-full px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.06em]",
            sourceTone[source],
          )}
        >
          {alert.sourceLabel}
        </span>
      </div>

      <div className="grid min-w-0 grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        <Field label="Event" value={alert.event} />
        <Field label="Root cause" value={cause} />
        <Field label="Anomaly score" value={formatScore(alert.anomaly_score)} />
        <Field
          label="Confidence"
          value={
            alert.root_cause_confidence === null || alert.root_cause_confidence === undefined
              ? "Not available"
              : formatConfidence(alert.root_cause_confidence)
          }
        />
        <Field label="Duration" value={durationLabel(alert.duration_seconds)} />
        <Field label="Detected" value={relativeTime(alert.timestamp)} />
        <Field label="State" value={resolved ? "Resolved" : "Active"} />
        <span className="flex items-center gap-x-2">
          <StatusBadge status={status} />
        </span>
      </div>

      <div className="flex items-center justify-end">
        <Button
          size="sm"
          variant="outline"
          onClick={(event) => {
            event.stopPropagation();
            onInvestigate();
          }}
        >
          Open investigation
        </Button>
      </div>
    </article>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[8px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
        {label}
      </p>
      <p className="truncate text-[11px] font-bold" title={value}>
        {value}
      </p>
    </div>
  );
}
