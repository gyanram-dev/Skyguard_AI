import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ArrowUpRight, Eye } from "lucide-react";

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
import { useAlert } from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/alerts/$alertId")({
  head: ({ params }) => ({
    meta: [{ title: `Alert ${params.alertId} | SkyGuard AI` }],
  }),
  component: AlertDetailPage,
});

function AlertDetailPage() {
  const { alertId } = Route.useParams();
  const navigate = useNavigate();
  const detailQuery = useAlert(alertId);
  const detail = detailQuery.data;

  if (detailQuery.isPending) {
    return <LoadingState message={`Loading alert ${alertId}…`} />;
  }
  if (detailQuery.isError) {
    return (
      <ErrorState message={errorMessage(detailQuery.error)} onRetry={() => detailQuery.refetch()} />
    );
  }
  if (!detail) {
    return (
      <EmptyState title="Alert not found" message="The API returned no detail for this alert ID." />
    );
  }

  const alert = detail.alert;
  const status = normalizeStatus(alert.status, true);
  const rootCause = cleanText(detail.root_cause.class) ?? cleanText(alert.root_cause);
  const sourceMode = alert.source_mode ?? "HISTORICAL_ALERT";
  const durationMinutes = Math.round((alert.duration_seconds ?? 0) / 60);

  return (
    <>
      <section className="panel p-4" aria-label="Alert triage review">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="section-kicker">
              {sourceMode} · {alert.station_id}
            </p>
            <h2 className="mt-1 text-lg font-extrabold">{alert.event}</h2>
            <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(alert.timestamp)}</p>
            <p className="mt-1 break-all text-[10px] text-muted-foreground">{alert.alert_id}</p>
          </div>
          <StatusBadge status={status} />
        </div>
        <p className="mt-3 max-w-3xl text-sm text-muted-foreground">
          {cleanText(alert.summary) ?? "No summary available."}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          <DetailStat label="Anomaly score" value={formatScore(alert.anomaly_score)} emphasis />
          <DetailStat label="Confidence" value={formatConfidence(alert.root_cause_confidence)} />
          <DetailStat label="Root cause" value={rootCause ?? "Needs review"} />
          <DetailStat
            label="Episode duration"
            value={durationMinutes === 0 ? "1 sample" : `${durationMinutes} min`}
          />
        </div>
        <div className="mt-3 divide-y divide-border rounded border border-border px-3">
          <div className="py-2 text-xs">
            <span className="text-muted-foreground">Sensor scope</span>
            <span className="ml-3 font-semibold">{alert.sensor ?? "Not isolated"}</span>
          </div>
          <div className="py-2 text-xs">
            <span className="text-muted-foreground">Source</span>
            <span className="ml-3 font-semibold">Historical Indian validation data</span>
          </div>
        </div>
      </section>

      <section className="flex flex-wrap gap-2" aria-label="Alert actions">
        <Button variant="outline" size="sm" onClick={() => navigate({ to: "/alerts" })}>
          <ArrowLeft />
          Back to alerts
        </Button>
        <Button
          size="sm"
          onClick={() =>
            navigate({ to: "/investigations/$alertId", params: { alertId: alert.alert_id } })
          }
        >
          <ArrowUpRight />
          Open investigation
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            navigate({ to: "/stations/$stationId", params: { stationId: alert.station_id } })
          }
        >
          <Eye />
          View station
        </Button>
      </section>
    </>
  );
}
