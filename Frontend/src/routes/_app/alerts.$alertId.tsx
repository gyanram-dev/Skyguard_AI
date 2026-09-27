import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, Eye, FlaskConical } from "lucide-react";

import { Button } from "@/components/ui/button";
import { normalizeStatus } from "@/lib/api";
import {
  cleanText,
  errorMessage,
  formatDateTime,
  formatHumidity,
  formatPressure,
  formatScore,
  formatTemp,
  formatTime,
} from "@/lib/format";
import { useAlert } from "@/hooks/useSkyguard";
import {
  DetailStat,
  EmptyBlock,
  ErrorBlock,
  InfoRow,
  LoadingBlock,
  SectionCard,
  StatusBadge,
} from "@/components/shared";
import { HistoryChart } from "@/components/HistoryChart";
import { EvidenceList } from "@/components/EvidenceList";

export const Route = createFileRoute("/_app/alerts/$alertId")({
  head: ({ params }) => ({
    meta: [{ title: `Alert ${params.alertId} | SkyGuard AI` }],
  }),
  component: AlertDetailPage,
});

function AlertDetailPage() {
  const { alertId } = Route.useParams();
  const detailQuery = useAlert(alertId);
  const detail = detailQuery.data;

  if (detailQuery.isPending) {
    return (
      <SectionCard title="Alert detail" subtitle="Loading alert evidence…">
        <LoadingBlock label="Loading alert evidence from the API…" />
      </SectionCard>
    );
  }

  if (detailQuery.isError || !detail) {
    return (
      <SectionCard title="Alert detail" subtitle="Alert evidence">
        <ErrorBlock
          message={detailQuery.isError ? errorMessage(detailQuery.error) : "Alert not found."}
          onRetry={() => detailQuery.refetch()}
        />
      </SectionCard>
    );
  }

  const alert = detail.alert;
  const status = normalizeStatus(alert.status, true);
  const historyVariable = detail.history.variable;
  const historySeries = detail.history.series.map((point) => {
    const raw = point[historyVariable];
    return {
      time: formatTime(point.timestamp),
      recorded: typeof raw === "number" ? raw : null,
    };
  });
  const explanation = cleanText(detail.explanation.text);

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" asChild>
          <Link to="/alerts">
            <ArrowLeft />
            Back to alerts
          </Link>
        </Button>
        <Button size="sm" asChild>
          <Link to="/investigations/$alertId" params={{ alertId: alert.alert_id }}>
            <FlaskConical />
            Open investigation
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link to="/stations/$stationId" params={{ stationId: alert.station_id }}>
            <Eye />
            View station
          </Link>
        </Button>
      </div>

      <SectionCard
        title={`${alert.station_id} · ${alert.event}`}
        subtitle={`Detected ${formatDateTime(alert.timestamp)} · Historical replay`}
        action={<StatusBadge status={status} />}
      >
        <div className="grid grid-cols-1 gap-x-6 md:grid-cols-2">
          <div>
            <InfoRow label="Alert ID" value={alert.alert_id} />
            <InfoRow label="Station" value={alert.station_id} />
            <InfoRow label="Event" value={alert.event} />
          </div>
          <div>
            <InfoRow label="Anomaly score" value={formatScore(alert.anomaly_score)} />
            <InfoRow label="Root cause" value={cleanText(alert.root_cause) ?? "Not available"} />
            <InfoRow
              label="RC confidence"
              value={
                alert.root_cause_confidence !== null && alert.root_cause_confidence !== undefined
                  ? `${(alert.root_cause_confidence * 100).toFixed(0)}%`
                  : "Not available"
              }
            />
          </div>
        </div>
        {cleanText(alert.summary) && (
          <p className="mt-2 rounded-xl bg-muted px-3 py-2 text-[10px] leading-snug text-muted-foreground">
            {cleanText(alert.summary)}
          </p>
        )}
      </SectionCard>

      <SectionCard title="Observed values" subtitle="Station readings behind this alert">
        <div className="grid grid-cols-3 gap-1.5">
          <DetailStat
            label="Temperature"
            value={formatTemp(detail.observations.temperature_c)}
            emphasis
            tone="bg-anomaly-soft"
          />
          <DetailStat
            label="Humidity"
            value={formatHumidity(detail.observations.relative_humidity_pct)}
            tone="bg-surface-blue-tint"
          />
          <DetailStat
            label="Pressure"
            value={formatPressure(detail.observations.pressure_hpa)}
            tone="bg-surface-blue-tint"
            valueTone="text-info"
          />
        </div>
      </SectionCard>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <SectionCard title="Evidence" subtitle="Why this observation was flagged">
          <EvidenceList evidence={detail.evidence} />
        </SectionCard>
        <SectionCard
          title={`${historyVariable} history · ${detail.history.hours} hours`}
          subtitle={`Recorded (${alert.station_id}) · gaps are preserved missing values`}
        >
          <HistoryChart data={historySeries} heightClass="h-[140px]" />
        </SectionCard>
      </div>

      <SectionCard title="Diagnosis" subtitle="Root cause, explanation and ensemble">
        <div className="grid grid-cols-1 gap-x-6 md:grid-cols-2">
          <div>
            <InfoRow
              label="Root cause"
              value={cleanText(detail.root_cause.class) ?? "Not available"}
            />
            <InfoRow
              label="RC confidence"
              value={
                detail.root_cause.confidence !== null && detail.root_cause.confidence !== undefined
                  ? `${(detail.root_cause.confidence * 100).toFixed(0)}%`
                  : "Not available"
              }
            />
            <InfoRow label="Ensemble method" value={detail.ensemble_method} />
          </div>
          <div>
            <p className="py-1 text-[11px] text-muted-foreground">Explanation</p>
            {explanation ? (
              <p className="text-[11px] font-bold leading-snug text-foreground">{explanation}</p>
            ) : (
              <EmptyBlock
                title="Explanation not available"
                message="The backend returned no explanation text for this alert."
              />
            )}
          </div>
        </div>
        {detail.explanation.features.length > 0 && (
          <div className="mt-3 overflow-x-auto">
            <div className="min-w-[520px]">
              <div
                className="grid grid-cols-[minmax(0,1fr)_120px_120px_100px] gap-2 px-2.5 text-[9px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground"
                aria-hidden="true"
              >
                <span>Feature</span>
                <span>Value</span>
                <span>Contribution</span>
                <span className="text-right">Direction</span>
              </div>
              <div className="mt-1.5 space-y-1.5">
                {detail.explanation.features.map((feature) => (
                  <div
                    key={feature.name}
                    className="grid grid-cols-[minmax(0,1fr)_120px_120px_100px] items-center gap-2 rounded-xl border border-border bg-card px-2.5 py-2"
                  >
                    <strong className="truncate text-[11px] font-extrabold">{feature.name}</strong>
                    <span className="text-[11px] text-muted-foreground">
                      {feature.value !== null && feature.value !== undefined
                        ? feature.value.toFixed(3)
                        : "—"}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      {feature.contribution !== null && feature.contribution !== undefined
                        ? feature.contribution.toFixed(3)
                        : "—"}
                    </span>
                    <span className="text-right text-[11px] font-semibold text-muted-foreground">
                      {feature.direction}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </SectionCard>
    </>
  );
}
