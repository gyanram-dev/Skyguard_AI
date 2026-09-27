import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ArrowUpRight, Eye } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DetailStat, EmptyState, ErrorState, LoadingState, StatusBadge } from "@/components/common";
import { HistoryChart, toChartPoints } from "@/components/charts";
import { EvidenceList, ExplanationBlock, OutcomeBanner } from "@/components/evidence";
import { normalizeStatus } from "@/lib/api";
import {
  cleanText,
  errorMessage,
  formatDateTime,
  formatHumidity,
  formatPressure,
  formatScore,
  formatTemp,
} from "@/lib/format";
import { useAlert } from "@/hooks/useSkyguard";
import { useMemo } from "react";

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

  const historySeries = useMemo(
    () => toChartPoints(detail?.history.series ?? [], detail?.history.variable ?? "temperature"),
    [detail],
  );

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
  const observations = detail.observations;

  return (
    <>
      <section className="panel p-4" aria-label="Alert header">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="section-kicker">
              {alert.station_id} · {formatDateTime(alert.timestamp)}
            </p>
            <h2 className="mt-1 text-lg font-extrabold">{alert.event}</h2>
            <p className="mt-0.5 break-all text-[10px] text-muted-foreground">{alert.alert_id}</p>
          </div>
          <StatusBadge status={status} />
        </div>
        <div className="mt-2.5 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          <DetailStat label="Anomaly score" value={formatScore(alert.anomaly_score)} emphasis />
          <DetailStat
            label="Root cause"
            value={cleanText(detail.root_cause.class) ?? cleanText(alert.root_cause) ?? "—"}
            tone="bg-surface-blue-tint"
          />
          <DetailStat
            label="Ensemble method"
            value={detail.ensemble_method}
            tone="bg-surface-blue-tint"
          />
          <DetailStat
            label="Observed temperature"
            value={formatTemp(observations.temperature_c)}
            tone="bg-surface-blue-tint"
          />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <section className="panel p-4" aria-label="Observed values">
          <p className="section-kicker">Observed values</p>
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            <DetailStat
              label="Temperature"
              value={formatTemp(observations.temperature_c)}
              emphasis
            />
            <DetailStat
              label="Humidity"
              value={formatHumidity(observations.relative_humidity_pct)}
              tone="bg-surface-blue-tint"
            />
            <DetailStat
              label="Pressure"
              value={formatPressure(observations.pressure_hpa)}
              tone="bg-surface-blue-tint"
            />
          </div>
          <div className="mt-2.5">
            <OutcomeBanner
              status={status}
              outcome={cleanText(detail.root_cause.class) ?? alert.event}
              message={
                cleanText(detail.explanation.text) ??
                cleanText(alert.summary) ??
                "No explanation available."
              }
              rootCauseConfidence={detail.root_cause.confidence}
              ensembleMethod={detail.ensemble_method}
            />
          </div>
        </section>

        <section className="panel p-4" aria-label="History">
          <p className="section-kicker">
            {detail.history.variable} history · {detail.history.hours} hours
          </p>
          <div className="mt-2">
            <HistoryChart
              data={historySeries}
              height={150}
              ariaLabel={`${detail.history.variable} history for ${alert.station_id}`}
            />
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <section className="panel p-4" aria-label="Evidence">
          <EvidenceList evidence={detail.evidence} loading={false} />
        </section>
        <section className="panel p-4" aria-label="Explanation">
          <ExplanationBlock explanation={detail.explanation} loading={false} />
        </section>
      </div>

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
