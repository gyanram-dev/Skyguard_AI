import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { ArrowUpRight, FileSearch } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DetailStat, EmptyState, ErrorState, LoadingState, StatusBadge } from "@/components/common";
import { normalizeStatus } from "@/lib/api";
import {
  cleanText,
  errorMessage,
  formatConfidence,
  formatDateTime,
  formatScore,
} from "@/lib/format";
import { useAlerts, useLiveAlerts } from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/investigations/")({
  head: () => ({
    meta: [{ title: "Investigations | SkyGuard AI" }],
  }),
  component: InvestigationsPage,
});

/**
 * Investigations is the analysis workspace, not a second alert table.
 * Alerts answers "what needs attention?"; this page answers "why did
 * SkyGuard make this decision?" and routes into the evidence bundle.
 */
function InvestigationsPage() {
  const navigate = useNavigate();
  const alertsQuery = useAlerts(1000);
  const liveAlertsQuery = useLiveAlerts();
  const alerts = useMemo(() => alertsQuery.data?.alerts ?? [], [alertsQuery.data]);
  const liveEpisodes = useMemo(() => liveAlertsQuery.data?.episodes ?? [], [liveAlertsQuery.data]);

  const diagnosed = useMemo(
    () => alerts.filter((alert) => cleanText(alert.root_cause) !== null).length,
    [alerts],
  );
  const latest = alerts[0] ?? null;
  const latestLive = liveEpisodes[0] ?? null;

  const sections = [
    "Observation & decision",
    "Root cause & confidence",
    "Sensor history",
    "Temporal · statistical · Isolation Forest · LSTM evidence",
    "Multivariate consistency",
    "Spatial context",
    "SHAP contributions",
    "Data quality & provenance",
    "Episode timeline",
    "Operator recommendation",
  ];

  return (
    <>
      <section className="panel p-4" aria-label="Investigation workspace">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="section-kicker">Evidence workspace</p>
            <h1 className="mt-1 text-lg font-extrabold">Why did SkyGuard decide this?</h1>
            <p className="mt-1 max-w-3xl text-[11px] text-muted-foreground">
              Investigations is the analytical view. It renders the full evidence bundle for one
              decision — only the sections the backend actually supports, never empty placeholders.
            </p>
          </div>
          <FileSearch className="hidden size-6 text-sky sm:block" />
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {sections.map((section) => (
            <span
              key={section}
              className="rounded-full bg-muted px-2.5 py-1 text-[9px] font-bold text-muted-foreground"
            >
              {section}
            </span>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-4" aria-label="Investigation summary">
        <DetailStat
          label="Historical candidates"
          value={alertsQuery.isPending ? "…" : String(alerts.length)}
        />
        <DetailStat
          label="With a root cause"
          value={alertsQuery.isPending ? "…" : String(diagnosed)}
        />
        <DetailStat
          label="Live episodes"
          value={liveAlertsQuery.isPending ? "…" : String(liveEpisodes.length)}
        />
        <DetailStat label="Review state recorded" value="Not recorded" />
      </div>

      {alertsQuery.isPending && <LoadingState message="Loading analysis candidates…" />}
      {alertsQuery.isError && (
        <ErrorState
          message={errorMessage(alertsQuery.error)}
          onRetry={() => alertsQuery.refetch()}
        />
      )}
      {!alertsQuery.isPending && !alertsQuery.isError && alerts.length === 0 && (
        <EmptyState
          title="No historical candidates"
          message="No stored historical alerts are available for analysis in this operating mode."
        />
      )}

      {!alertsQuery.isPending && !alertsQuery.isError && latest && (
        <section className="panel p-4" aria-label="Latest analysis candidate">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="section-kicker">
                {latest.source_mode ?? "HISTORICAL_ALERT"} · {latest.station_id}
              </p>
              <h2 className="mt-1 text-base font-extrabold">{latest.event}</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {formatDateTime(latest.timestamp)}
              </p>
              <div className="mt-1.5">
                <StatusBadge status={normalizeStatus(latest.status, true)} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <DetailStat label="Anomaly score" value={formatScore(latest.anomaly_score)} />
              <DetailStat
                label="Root cause confidence"
                value={formatConfidence(latest.root_cause_confidence)}
              />
            </div>
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            {cleanText(latest.summary) ?? "No summary available."}
          </p>
          <Button
            className="mt-3"
            size="sm"
            onClick={() =>
              navigate({
                to: "/investigations/$alertId",
                params: { alertId: latest.alert_id },
              })
            }
          >
            <ArrowUpRight />
            Open evidence workspace
          </Button>
        </section>
      )}

      {latestLive && (
        <section className="panel p-4" aria-label="Latest live episode">
          <p className="section-kicker">Latest live episode · LIVE_ALERT</p>
          <h2 className="mt-1 text-base font-extrabold">
            {latestLive.station_id} · {latestLive.interpretation}
          </h2>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {latestLive.detection_count} detections · {latestLive.status} · last seen{" "}
            {formatDateTime(latestLive.last_seen_at)}
          </p>
          <Button
            className="mt-3"
            size="sm"
            variant="outline"
            onClick={() =>
              navigate({
                to: "/investigations/live/$alertId",
                params: { alertId: latestLive.alert_id },
              })
            }
          >
            <ArrowUpRight />
            Open live investigation
          </Button>
        </section>
      )}
    </>
  );
}
