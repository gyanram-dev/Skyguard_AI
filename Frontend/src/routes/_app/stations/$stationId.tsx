import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { ArrowLeft, ArrowUpRight, Home } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, FactRow, LoadingState, StatusBadge } from "@/components/common";
import { HistoryChart, toChartPoints } from "@/components/charts";
import { normalizeStatus, type HistoryVariable } from "@/lib/api";
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
import { cityForStationId } from "@/lib/mapMeta";
import { useAlerts, useStation, useStationHistory, useStations } from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/stations/$stationId")({
  head: ({ params }) => ({
    meta: [{ title: `Station ${params.stationId} | SkyGuard AI` }],
  }),
  component: StationDetailPage,
});

const HISTORY_VARIABLES: Array<{ variable: HistoryVariable; label: string }> = [
  { variable: "temperature", label: "Temperature · 24 hours" },
  { variable: "humidity", label: "Humidity · 24 hours" },
  { variable: "pressure", label: "Pressure · 24 hours" },
];

function StationHistoryBlock({
  stationId,
  variable,
  label,
}: {
  stationId: string;
  variable: HistoryVariable;
  label: string;
}) {
  const historyQuery = useStationHistory(stationId, variable, 24);
  const chartPoints = useMemo(
    () => toChartPoints(historyQuery.data?.points ?? [], variable),
    [historyQuery.data, variable],
  );
  if (historyQuery.isPending) {
    return (
      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">{label}</p>
        <p className="mt-2 text-[11px] text-muted-foreground" role="status">
          Loading history…
        </p>
      </div>
    );
  }
  if (historyQuery.isError) {
    return (
      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">{label}</p>
        <div className="mt-2">
          <ErrorState
            message={errorMessage(historyQuery.error)}
            onRetry={() => historyQuery.refetch()}
          />
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-border p-2.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">{label}</p>
        <span className="flex items-center gap-1 text-[9px] font-semibold text-muted-foreground">
          <i className="size-1.5 rounded-full bg-anomaly" />
          Recorded ({stationId})
        </span>
      </div>
      <div className="mt-1">
        <HistoryChart data={chartPoints} height={110} ariaLabel={`${label} for ${stationId}`} />
      </div>
    </div>
  );
}

function StationDetailPage() {
  const { stationId } = Route.useParams();
  const navigate = useNavigate();
  const stationsQuery = useStations();
  const alertsQuery = useAlerts(1000);

  const summaryRow = useMemo(
    () => (stationsQuery.data?.stations ?? []).find((row) => row.station_id === stationId),
    [stationsQuery.data, stationId],
  );
  const hasBackendData = summaryRow?.data_available === true;
  const detailQuery = useStation(hasBackendData ? stationId : null);

  const relatedAlert = useMemo(
    () => (alertsQuery.data?.alerts ?? []).find((alert) => alert.station_id === stationId),
    [alertsQuery.data, stationId],
  );

  if (stationsQuery.isPending) {
    return <LoadingState message={`Loading ${stationId}…`} />;
  }
  if (stationsQuery.isError) {
    return (
      <ErrorState
        message={errorMessage(stationsQuery.error)}
        onRetry={() => stationsQuery.refetch()}
      />
    );
  }
  if (!summaryRow) {
    return (
      <EmptyState
        title={`Unknown station "${stationId}"`}
        message="The API has no station with this ID. Check the stations list for valid IDs."
      />
    );
  }

  const city = cityForStationId(stationId, stationsQuery.data?.stations ?? []) ?? summaryRow.city;
  const status = normalizeStatus(summaryRow.status, summaryRow.data_available);
  const detail = detailQuery.data;

  return (
    <>
      <section className="panel p-4" aria-label="Station identity">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="section-kicker">Station detail</p>
            <h2 className="mt-1 text-lg font-extrabold">
              {stationId} · {city}
            </h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Data mode: {summaryRow.data_mode} · Last updated:{" "}
              {formatDateTime(summaryRow.last_updated)}
            </p>
          </div>
          <StatusBadge status={status} />
        </div>
        {!hasBackendData && (
          <div className="mt-3">
            <EmptyState
              title="Station unavailable"
              message="No backend data exists for this station in historical replay. No readings are fabricated."
            />
          </div>
        )}
      </section>

      {hasBackendData && (
        <>
          {detailQuery.isPending && <LoadingState message="Loading station detail…" />}
          {detailQuery.isError && (
            <ErrorState
              message={errorMessage(detailQuery.error)}
              onRetry={() => detailQuery.refetch()}
            />
          )}
          {detail && (
            <>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <section className="panel p-4" aria-label="Current observations">
                  <p className="section-kicker">Observations</p>
                  <div className="mt-1 divide-y divide-border">
                    <FactRow label="Temperature" value={formatTemp(summaryRow.temperature)} />
                    <FactRow
                      label="Humidity"
                      value={
                        summaryRow.humidity !== null && summaryRow.humidity !== undefined
                          ? `${summaryRow.humidity.toFixed(1)}% RH`
                          : "Not available"
                      }
                    />
                    <FactRow
                      label="Pressure"
                      value={
                        summaryRow.pressure !== null && summaryRow.pressure !== undefined
                          ? `${summaryRow.pressure.toFixed(1)} hPa`
                          : "Not available"
                      }
                    />
                    <FactRow label="Anomaly score" value={formatScore(detail.anomaly.score)} />
                  </div>
                </section>

                <section className="panel p-4" aria-label="Data quality and anomaly">
                  <p className="section-kicker">Quality & anomaly</p>
                  <div className="mt-1 divide-y divide-border">
                    <FactRow label="Data quality" value={detail.data_quality.status} />
                    <FactRow
                      label="ML eligible"
                      value={detail.data_quality.ml_eligible ? "Yes" : "No"}
                    />
                    <FactRow
                      label="Anomaly detected"
                      value={detail.anomaly.detected ? "Yes" : "No"}
                    />
                    <FactRow label="Method" value={detail.anomaly.method} />
                    <FactRow
                      label="Confidence"
                      value={formatConfidence(detail.anomaly.confidence)}
                    />
                  </div>
                </section>

                <section className="panel p-4" aria-label="Root cause and spatial context">
                  <p className="section-kicker">Diagnosis & context</p>
                  <div className="mt-1 divide-y divide-border">
                    <FactRow
                      label="Root cause"
                      value={cleanText(detail.root_cause.class) ?? "Not available"}
                    />
                    <FactRow
                      label="RC confidence"
                      value={formatConfidence(detail.root_cause.confidence)}
                    />
                    <FactRow
                      label="Spatial available"
                      value={detail.spatial_context.available ? "Yes" : "No"}
                    />
                    <FactRow
                      label="Neighbors"
                      value={String(detail.spatial_context.neighbor_count)}
                    />
                    <FactRow label="Context" value={detail.spatial_context.context_level} />
                  </div>
                </section>
              </div>

              {(detail.data_quality.flags.length > 0 ||
                detail.observations.temperature_c !== null) && (
                <section className="panel p-4" aria-label="Observation detail">
                  <p className="section-kicker">Snapshot detail</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Temperature {formatTemp(detail.observations.temperature_c)} · Humidity{" "}
                    {formatHumidity(detail.observations.relative_humidity_pct)} · Pressure{" "}
                    {formatPressure(detail.observations.pressure_hpa)}
                    {detail.data_quality.flags.length > 0 &&
                      ` · Flags: ${detail.data_quality.flags.join(", ")}`}
                  </p>
                </section>
              )}

              <section className="grid grid-cols-1 gap-3 xl:grid-cols-3" aria-label="Histories">
                {HISTORY_VARIABLES.map((entry) => (
                  <StationHistoryBlock
                    key={entry.variable}
                    stationId={stationId}
                    variable={entry.variable}
                    label={entry.label}
                  />
                ))}
              </section>
            </>
          )}
        </>
      )}

      <section className="flex flex-wrap gap-2" aria-label="Station actions">
        <Button variant="outline" size="sm" onClick={() => navigate({ to: "/stations" })}>
          <ArrowLeft />
          Back to Stations
        </Button>
        <Button variant="outline" size="sm" onClick={() => navigate({ to: "/" })}>
          <Home />
          Return to Overview
        </Button>
        {relatedAlert ? (
          <Button
            size="sm"
            onClick={() =>
              navigate({
                to: "/investigations/$alertId",
                params: { alertId: relatedAlert.alert_id },
              })
            }
          >
            <ArrowUpRight />
            Open related investigation
          </Button>
        ) : (
          <span className="inline-flex items-center px-2 text-[11px] text-muted-foreground">
            {alertsQuery.isPending ? "Checking for related alerts…" : "No related alert."}
          </span>
        )}
      </section>
    </>
  );
}
