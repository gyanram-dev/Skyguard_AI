import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { ArrowLeft, Bell, Eye } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DetailStat,
  EmptyState,
  ErrorState,
  FactRow,
  LoadingState,
  StatusBadge,
} from "@/components/common";
import { HistoryChart, toChartPoints } from "@/components/charts";
import { EvidenceList, ExplanationBlock } from "@/components/evidence";
import { normalizeStatus } from "@/lib/api";
import {
  cleanText,
  errorMessage,
  formatConfidence,
  formatDateTime,
  formatHumidity,
  formatPressure,
  formatScore,
  formatTemp,
} from "@/lib/format";
import { useAlert } from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/investigations/$alertId")({
  head: ({ params }) => ({
    meta: [{ title: `Investigation ${params.alertId} | SkyGuard AI` }],
  }),
  component: InvestigationDetailPage,
});

function InvestigationDetailPage() {
  const { alertId } = Route.useParams();
  const navigate = useNavigate();
  const detailQuery = useAlert(alertId);
  const detail = detailQuery.data;

  const historySeries = useMemo(
    () => toChartPoints(detail?.history.series ?? [], detail?.history.variable ?? "temperature"),
    [detail],
  );

  if (detailQuery.isPending) {
    return <LoadingState message={`Loading investigation ${alertId}…`} />;
  }
  if (detailQuery.isError) {
    return (
      <ErrorState message={errorMessage(detailQuery.error)} onRetry={() => detailQuery.refetch()} />
    );
  }
  if (!detail) {
    return (
      <EmptyState
        title="Investigation not found"
        message="The API returned no detail for this alert ID."
      />
    );
  }

  const alert = detail.alert;
  const status = normalizeStatus(alert.status, true);
  const observations = detail.observations;
  const rootCause = cleanText(detail.root_cause.class) ?? cleanText(alert.root_cause);
  const sourceMode = alert.source_mode ?? "HISTORICAL_ALERT";
  const durationMinutes = Math.round((alert.duration_seconds ?? 0) / 60);

  return (
    <>
      <section className="panel p-4" aria-label="What happened">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="section-kicker">
              {sourceMode} · {alert.station_id}
            </p>
            <h2 className="mt-1 text-lg font-extrabold">{alert.event}</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Detected {formatDateTime(alert.timestamp)}
            </p>
            <p className="mt-0.5 break-all text-[10px] text-muted-foreground">{alert.alert_id}</p>
          </div>
          <StatusBadge status={status} />
        </div>
        <p className="mt-2 text-[11px] leading-snug text-muted-foreground">
          {cleanText(alert.summary) ?? "No summary available."}
        </p>
        <div className="mt-2.5 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          <DetailStat label="Anomaly score" value={formatScore(alert.anomaly_score)} emphasis />
          <DetailStat label="Root cause" value={rootCause ?? "—"} tone="bg-surface-blue-tint" />
          <DetailStat
            label="RC confidence"
            value={formatConfidence(detail.root_cause.confidence ?? alert.root_cause_confidence)}
            tone="bg-surface-blue-tint"
          />
          <DetailStat label="Ensemble" value={detail.ensemble_method} tone="bg-surface-blue-tint" />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <section className="panel p-4" aria-label="What was observed">
          <p className="section-kicker">What was observed?</p>
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
          <div className="mt-2.5 divide-y divide-border rounded-xl border border-border px-2.5">
            <FactRow label="Method" value={detail.ensemble_method} />
            <FactRow label="Anomaly score" value={formatScore(alert.anomaly_score)} />
            <FactRow label="Source mode" value={sourceMode} />
            <FactRow label="Data quality" value={detail.data_quality?.status ?? "Not retained"} />
            <FactRow
              label="Evaluation eligible"
              value={detail.data_quality?.evaluation_eligible ? "Yes" : "No"}
            />
            <FactRow label="Sensor scope" value={alert.sensor ?? "Not isolated"} />
            <FactRow
              label="Root-cause confidence"
              value={formatConfidence(detail.root_cause.confidence)}
            />
          </div>
        </section>

        <section className="panel p-4" aria-label="Temporal evidence">
          <p className="section-kicker">
            Temporal evidence · {detail.history.variable} · {detail.history.hours}h
          </p>
          <div className="mt-2">
            <HistoryChart
              data={historySeries}
              height={150}
              ariaLabel={`${detail.history.variable} history for ${alert.station_id}`}
            />
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">
            Missing points remain gaps — the frontend does not interpolate.
          </p>
        </section>
      </div>

      <section className="panel p-4" aria-label="Why flagged">
        <EvidenceList evidence={detail.evidence} loading={false} />
      </section>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <section className="panel p-4" aria-label="Root cause">
          <p className="section-kicker">Root cause & confidence</p>
          <div className="mt-1 divide-y divide-border">
            <FactRow label="Predicted class" value={rootCause ?? "Not available"} />
            <FactRow label="Confidence" value={formatConfidence(detail.root_cause.confidence)} />
            <FactRow label="Ensemble method" value={detail.ensemble_method} />
          </div>
        </section>
        <section className="panel p-4" aria-label="Explainability">
          <ExplanationBlock explanation={detail.explanation} loading={false} />
        </section>
      </div>

      <section className="panel p-4" aria-label="Episode timeline and provenance">
        <p className="section-kicker">Episode timeline & provenance</p>
        <div className="mt-1 divide-y divide-border">
          <FactRow label="First detected" value={formatDateTime(alert.timestamp)} />
          <FactRow
            label="Duration"
            value={durationMinutes === 0 ? "1 sample" : `${durationMinutes} min`}
          />
          <FactRow label="Source" value="Historical Indian validation data" />
          <FactRow label="Persistence" value="Frozen historical detector payload" />
        </div>
      </section>

      <section className="panel p-4" aria-label="Recommended operator action">
        <p className="section-kicker">Recommended operator action</p>
        <p className="mt-1 text-sm">
          {cleanText(detail.recommended_action) ??
            "Preserve the observation, review sensor quality and nearby station context, then verify the instrument before making a field adjustment."}
        </p>
      </section>

      <section className="flex flex-wrap gap-2" aria-label="Investigation actions">
        <Button variant="outline" size="sm" onClick={() => navigate({ to: "/alerts" })}>
          <ArrowLeft />
          Back to Alerts
        </Button>
        <Button
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
