import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo } from "react";
import { ArrowLeft, FlaskConical, Home } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError, normalizeStatus } from "@/lib/api";
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
import { useAlerts, useStation, useStationHistory } from "@/hooks/useSkyguard";
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

export const Route = createFileRoute("/_app/stations/$stationId")({
  head: ({ params }) => ({
    meta: [{ title: `${params.stationId} | SkyGuard AI` }],
  }),
  component: StationDetailPage,
});

function StationDetailPage() {
  const { stationId } = Route.useParams();
  const detailQuery = useStation(stationId);
  const alertsQuery = useAlerts();
  const tempHistory = useStationHistory(stationId, "temperature", 24);
  const humidityHistory = useStationHistory(stationId, "humidity", 24);
  const pressureHistory = useStationHistory(stationId, "pressure", 24);
  const detail = detailQuery.data;

  const relatedAlert = useMemo(() => {
    const all = alertsQuery.data?.alerts ?? [];
    return all.find((alert) => alert.station_id === stationId) ?? null;
  }, [alertsQuery.data, stationId]);

  if (detailQuery.isPending) {
    return (
      <SectionCard title={stationId} subtitle="Loading station detail…">
        <LoadingBlock label="Loading station detail from the API…" />
      </SectionCard>
    );
  }

  if (detailQuery.isError || !detail) {
    const notFound =
      detailQuery.isError &&
      detailQuery.error instanceof ApiError &&
      detailQuery.error.status === 404;
    return (
      <>
        <StationNav stationId={stationId} relatedAlertId={null} />
        <SectionCard title={stationId} subtitle="Station detail">
          {notFound ? (
            <EmptyBlock
              title="Station unavailable"
              message={`No backend data for ${stationId} in historical replay. Measurements are not fabricated for unavailable stations.`}
            />
          ) : (
            <ErrorBlock
              message={detailQuery.isError ? errorMessage(detailQuery.error) : "Station not found."}
              onRetry={() => detailQuery.refetch()}
            />
          )}
        </SectionCard>
      </>
    );
  }

  const status = normalizeStatus(detail.station.status, true);
  const chartData = (
    query: typeof tempHistory,
    variable: "temperature" | "humidity" | "pressure",
  ) =>
    (query.data?.points ?? []).map((point) => {
      const raw = point[variable];
      return {
        time: formatTime(point.timestamp),
        recorded: typeof raw === "number" ? raw : null,
      };
    });

  return (
    <>
      <StationNav stationId={stationId} relatedAlertId={relatedAlert?.alert_id ?? null} />

      <SectionCard
        title={`${detail.station.station_id} · ${detail.station.city}`}
        subtitle={`Historical replay · Last updated ${formatDateTime(detail.station.last_updated)}`}
        action={<StatusBadge status={status} />}
      >
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

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <SectionCard title="Data quality" subtitle="Integrity gate result">
          <InfoRow label="Status" value={detail.data_quality.status} />
          <InfoRow label="ML eligible" value={detail.data_quality.ml_eligible ? "Yes" : "No"} />
          <InfoRow
            label="Flags"
            value={
              detail.data_quality.flags.length > 0 ? detail.data_quality.flags.join(", ") : "None"
            }
          />
        </SectionCard>
        <SectionCard title="Anomaly" subtitle={`Method: ${detail.anomaly.method}`}>
          <InfoRow label="Detected" value={detail.anomaly.detected ? "Yes" : "No"} />
          <InfoRow label="Score" value={formatScore(detail.anomaly.score)} />
          <InfoRow
            label="Confidence"
            value={
              detail.anomaly.confidence !== null && detail.anomaly.confidence !== undefined
                ? `${(detail.anomaly.confidence * 100).toFixed(0)}%`
                : "Not available"
            }
          />
        </SectionCard>
        <SectionCard title="Root cause & context" subtitle="Diagnosis and neighborhood">
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
          <InfoRow
            label="Spatial context"
            value={detail.spatial_context.available ? "Available" : "Unavailable"}
          />
          <InfoRow label="Neighbors" value={String(detail.spatial_context.neighbor_count)} />
          <InfoRow label="Context level" value={detail.spatial_context.context_level} />
        </SectionCard>
      </div>

      <SectionCard title="24-hour history" subtitle="Missing values are preserved as gaps.">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          {(
            [
              {
                label: "Temperature",
                query: tempHistory,
                variable: "temperature",
                color: "var(--chart-alert)",
              },
              {
                label: "Humidity",
                query: humidityHistory,
                variable: "humidity",
                color: "var(--chart-green)",
              },
              {
                label: "Pressure",
                query: pressureHistory,
                variable: "pressure",
                color: "var(--chart-blue)",
              },
            ] as const
          ).map((panel) => (
            <div key={panel.label} className="rounded-xl border border-border p-2.5">
              <p className="text-[9px] font-extrabold uppercase tracking-[0.04em]">{panel.label}</p>
              <div className="mt-1">
                {panel.query.isPending ? (
                  <LoadingBlock label="Loading history…" />
                ) : panel.query.isError ? (
                  <ErrorBlock message={errorMessage(panel.query.error)} />
                ) : (
                  <HistoryChart
                    data={chartData(panel.query, panel.variable)}
                    heightClass="h-[110px]"
                    color={panel.color}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </>
  );
}

function StationNav({
  stationId,
  relatedAlertId,
}: {
  stationId: string;
  relatedAlertId: string | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" asChild>
        <Link to="/stations">
          <ArrowLeft />
          Back to Stations
        </Link>
      </Button>
      <Button variant="outline" size="sm" asChild>
        <Link to="/">
          <Home />
          Overview
        </Link>
      </Button>
      {relatedAlertId ? (
        <Button size="sm" asChild>
          <Link to="/investigations/$alertId" params={{ alertId: relatedAlertId }}>
            <FlaskConical />
            Open related investigation
          </Link>
        </Button>
      ) : (
        <span className="text-[10px] text-muted-foreground">
          No related investigation for {stationId} in the current queue.
        </span>
      )}
    </div>
  );
}
