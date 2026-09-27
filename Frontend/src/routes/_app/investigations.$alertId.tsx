import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, Bell, Eye } from "lucide-react";

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
import { useAlert, useStation, useStationHistory } from "@/hooks/useSkyguard";
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

export const Route = createFileRoute("/_app/investigations/$alertId")({
  head: ({ params }) => ({
    meta: [{ title: `Investigation ${params.alertId} | SkyGuard AI` }],
  }),
  component: InvestigationDetailPage,
});

function Step({
  number,
  title,
  children,
}: {
  number: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <SectionCard title={`${number} · ${title}`} className="overflow-hidden">
      {children}
    </SectionCard>
  );
}

function InvestigationDetailPage() {
  const { alertId } = Route.useParams();
  const detailQuery = useAlert(alertId);
  const detail = detailQuery.data;

  // Spatial/context evidence + station history for the alert's station.
  const stationId = detail?.alert.station_id ?? null;
  const stationQuery = useStation(stationId);
  const stationTempHistory = useStationHistory(stationId, "temperature", 24);

  if (detailQuery.isPending) {
    return (
      <SectionCard title="Investigation" subtitle="Loading diagnosis workspace…">
        <LoadingBlock label="Loading investigation from the API…" />
      </SectionCard>
    );
  }

  if (detailQuery.isError || !detail) {
    return (
      <SectionCard title="Investigation" subtitle="Diagnosis workspace">
        <ErrorBlock
          message={detailQuery.isError ? errorMessage(detailQuery.error) : "Alert not found."}
          onRetry={() => detailQuery.refetch()}
        />
      </SectionCard>
    );
  }

  const alert = detail.alert;
  const status = normalizeStatus(alert.status, true);
  const explanation = cleanText(detail.explanation.text);
  const historyVariable = detail.history.variable;
  const eventSeries = detail.history.series.map((point) => {
    const raw = point[historyVariable];
    return {
      time: formatTime(point.timestamp),
      recorded: typeof raw === "number" ? raw : null,
    };
  });
  const contextSeries = (stationTempHistory.data?.points ?? []).map((point) => ({
    time: formatTime(point.timestamp),
    recorded: point.temperature ?? null,
  }));
  const spatial = stationQuery.data?.spatial_context;

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" asChild>
          <Link to="/investigations">
            <ArrowLeft />
            Back to investigations
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link to="/alerts/$alertId" params={{ alertId: alert.alert_id }}>
            <Bell />
            Back to alert
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link to="/stations/$stationId" params={{ stationId: alert.station_id }}>
            <Eye />
            View station
          </Link>
        </Button>
      </div>

      <Step number="1" title="What happened?">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="section-kicker">{alert.station_id} / Investigation</p>
            <h2 className="mt-0.5 text-sm font-extrabold">{alert.event}</h2>
            <p className="mt-1 text-[10px] text-muted-foreground">
              Detected {formatDateTime(alert.timestamp)} · Anomaly score{" "}
              {formatScore(alert.anomaly_score)} · Historical replay
            </p>
          </div>
          <StatusBadge status={status} />
        </div>
        {cleanText(alert.summary) && (
          <p className="mt-2 rounded-xl bg-muted px-3 py-2 text-[10px] leading-snug text-muted-foreground">
            {cleanText(alert.summary)}
          </p>
        )}
      </Step>

      <Step number="2" title="What was observed?">
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
      </Step>

      <Step number="3" title="Why was it flagged?">
        <EvidenceList evidence={detail.evidence} />
      </Step>

      <Step number="4" title="Temporal evidence">
        <p className="mb-2 text-[10px] text-muted-foreground">
          {historyVariable} around the event · Recorded ({alert.station_id}) · gaps are preserved
          missing values
        </p>
        <HistoryChart data={eventSeries} heightClass="h-[140px]" />
      </Step>

      <Step number="5" title="Spatial and station context">
        {stationQuery.isPending && <LoadingBlock label="Loading station context…" />}
        {stationQuery.isError && <ErrorBlock message={errorMessage(stationQuery.error)} />}
        {spatial && (
          <div className="grid grid-cols-1 gap-x-6 md:grid-cols-2">
            <div>
              <InfoRow label="Spatial available" value={spatial.available ? "Yes" : "No"} />
              <InfoRow label="Neighbor count" value={String(spatial.neighbor_count)} />
            </div>
            <div>
              <InfoRow label="Context level" value={spatial.context_level} />
              <InfoRow
                label="Station quality"
                value={stationQuery.data?.data_quality.status ?? "Not available"}
              />
            </div>
          </div>
        )}
      </Step>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Step number="6" title="Root cause">
          <InfoRow
            label="Predicted class"
            value={cleanText(detail.root_cause.class) ?? "Not available"}
          />
          <InfoRow
            label="Confidence"
            value={
              detail.root_cause.confidence !== null && detail.root_cause.confidence !== undefined
                ? `${(detail.root_cause.confidence * 100).toFixed(0)}%`
                : "Not available"
            }
          />
          <InfoRow label="Ensemble method" value={detail.ensemble_method} />
        </Step>
        <Step number="7" title="Confidence and explainability">
          {explanation ? (
            <p className="text-[11px] font-bold leading-snug text-foreground">{explanation}</p>
          ) : (
            <EmptyBlock
              title="Explanation not available"
              message="The backend returned no explanation text for this alert."
            />
          )}
          {detail.explanation.features.length > 0 && (
            <div className="mt-2 space-y-1">
              {detail.explanation.features.map((feature) => (
                <p
                  key={feature.name}
                  className="flex items-baseline justify-between gap-3 text-[11px]"
                >
                  <span className="truncate font-bold text-foreground">{feature.name}</span>
                  <span className="shrink-0 text-muted-foreground">
                    {feature.contribution !== null && feature.contribution !== undefined
                      ? feature.contribution >= 0
                        ? `+${feature.contribution.toFixed(3)}`
                        : feature.contribution.toFixed(3)
                      : "—"}{" "}
                    · {feature.direction}
                  </span>
                </p>
              ))}
            </div>
          )}
        </Step>
      </div>

      <Step number="8" title="Historical context">
        <p className="mb-2 text-[10px] text-muted-foreground">
          Station 24-hour temperature from the history endpoint
        </p>
        {stationTempHistory.isPending && <LoadingBlock label="Loading station history…" />}
        {stationTempHistory.isError && (
          <ErrorBlock message={errorMessage(stationTempHistory.error)} />
        )}
        {!stationTempHistory.isPending && !stationTempHistory.isError && (
          <HistoryChart data={contextSeries} heightClass="h-[140px]" color="var(--chart-blue)" />
        )}
      </Step>
    </>
  );
}
