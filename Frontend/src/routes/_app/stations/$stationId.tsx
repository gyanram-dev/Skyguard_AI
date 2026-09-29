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

  const relatedAlerts = useMemo(
    () => (alertsQuery.data?.alerts ?? []).filter((alert) => alert.station_id === stationId),
    [alertsQuery.data, stationId],
  );
  const relatedAlert = relatedAlerts[0] ?? null;

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
  // Phase-25 explicit capability block (falls back to derived fields).
  const capability = summaryRow.capability;
  const variables = new Set(capability?.variables_available ?? summaryRow.available_variables ?? []);
  const variableRow = (label: string, key: string, present: boolean) => (
    <FactRow
      label={label}
      value={
        present ? (
          <span className="text-success-deep">✓ available</span>
        ) : (
          <span className="text-muted-foreground">— not in source data</span>
        )
      }
    />
  );
  const detectorLabel =
    capability?.detector_capability === "FULL_TPR"
      ? "FULL T/P/RH"
      : capability?.detector_capability === "PARTIAL"
        ? "PARTIAL"
        : capability?.detector_capability === "CONTEXT_ONLY"
          ? "CONTEXT ONLY — no detector verdict"
          : capability?.detector_capability === "UNAVAILABLE"
            ? "UNAVAILABLE"
            : summaryRow.probe_available
              ? "FULL T/P/RH"
              : "CONTEXT ONLY — no detector verdict";
  const anomalyAllowed =
    (capability?.detector_capability ?? (summaryRow.probe_available ? "FULL_TPR" : "CONTEXT_ONLY")) ===
    "FULL_TPR";

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
              Data: {capability?.data_source ?? summaryRow.source_mode} ·{" "}
              {capability?.data_mode === "REPLAY" ? "Historical Replay" : "Historical"} ·{" "}
              {capability?.country ?? "India"}
              {capability?.state ? ` · ${capability.state}` : ""}
            </p>
            {capability && (
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                Observation period: {capability.start_time ?? "—"} → {capability.end_time ?? "—"} ·{" "}
                {capability.observation_count.toLocaleString()} observations
                {capability.pressure_basis
                  ? ` · pressure basis: ${capability.pressure_basis.replace(/_/g, " ")}`
                  : ""}
              </p>
            )}
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Scope:{" "}
              {summaryRow.operational_scope === "benchmark_internal"
                ? "Internal benchmark (not an Indian operational station)"
                : summaryRow.operational_scope === "offline"
                  ? "Offline placeholder"
                  : "Indian operational network"}
            </p>
            {(detail?.station.capability_notes ?? summaryRow.capability_notes ?? []).map((note) => (
              <p key={note} className="mt-0.5 text-[10px] text-muted-foreground">
                {note}
              </p>
            ))}
          </div>
          <div className="flex flex-col items-end gap-1">
            <StatusBadge status={status} />
            {!anomalyAllowed && (
              <span
                className="rounded-md bg-warning-soft px-1.5 py-0.5 text-[9px] font-extrabold text-warning-deep"
                title="No detector models cover this station; historical observations are served as network context."
              >
                NO DETECTOR VERDICT
              </span>
            )}
          </div>
        </div>
        {!hasBackendData && (
          <div className="mt-3">
            <EmptyState
              title="Station unavailable"
              message="No backend data exists for this station in historical replay. No readings are fabricated."
            />
          </div>
        )}
        {hasBackendData && (
          <div className="mt-3 grid grid-cols-1 gap-x-6 border-t border-border pt-2 sm:grid-cols-2">
            <div aria-label="Available variables">
              <p className="text-[10px] font-extrabold uppercase tracking-[0.06em] text-muted-foreground">
                Available variables (source data)
              </p>
              {variableRow("Temperature", "temperature", variables.has("temperature"))}
              {variableRow(
                "Relative Humidity",
                "relative_humidity",
                variables.has("relative_humidity"),
              )}
              {variableRow("Pressure", "pressure", variables.has("pressure"))}
            </div>
            <div aria-label="Detector capability">
              <p className="text-[10px] font-extrabold uppercase tracking-[0.06em] text-muted-foreground">
                AI detection
              </p>
              <FactRow label="Capability" value={detectorLabel} />
              <FactRow
                label="Anomaly status"
                value={
                  anomalyAllowed ? (
                    status === "anomaly" ? (
                      "Anomaly detected"
                    ) : status === "review" ? (
                      "Needs review"
                    ) : (
                      "Normal (detector evaluated)"
                    )
                  ) : (
                    <span className="text-muted-foreground">
                      Not evaluated — detector does not cover this station
                    </span>
                  )
                }
              />
              {capability?.spatial_context_capability && (
                <FactRow
                  label="Spatial context"
                  value={capability.spatial_context_capability.replace(/_/g, " ")}
                />
              )}
            </div>
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

              <section className="grid grid-cols-1 gap-3 xl:grid-cols-2" aria-label="Sensor health">
                <div className="panel p-4" aria-label="Station trust factors">
                  <p className="section-kicker">Sensor health</p>
                  <h3 className="mt-1 text-sm font-extrabold">Can I trust this station?</h3>
                  <div className="mt-2 divide-y divide-border">
                    <FactRow label="Data quality" value={detail.data_quality.status} />
                    <FactRow
                      label="Recent anomalies"
                      value={
                        relatedAlerts.length > 0
                          ? `${relatedAlerts.length} in the stored window`
                          : "None in the stored window"
                      }
                    />
                    <FactRow
                      label="Freeze evidence"
                      value={
                        detail.data_quality.flags.length > 0
                          ? detail.data_quality.flags.join(", ")
                          : "Unavailable"
                      }
                    />
                    <FactRow label="Drift evidence" value="Unavailable" />
                    <FactRow
                      label="Communication status"
                      value="Historical replay — no live link"
                    />
                    <FactRow
                      label="Spatial context"
                      value={
                        detail.spatial_context.available
                          ? detail.spatial_context.context_level
                          : "Unavailable"
                      }
                    />
                    <FactRow
                      label="Maintenance review"
                      value={
                        typeof detail.maintenance?.["state"] === "string"
                          ? `${String(detail.maintenance["state"]).replace(/_/g, " ")} (${String(detail.maintenance["episodes_30d"] ?? 0)} episodes / 30d)`
                          : "Unavailable"
                      }
                    />
                  </div>
                  <p className="mt-1.5 text-[10px] text-muted-foreground">
                    Factors the backend does not expose are shown as Unavailable — a missing
                    measurement is never treated as healthy.
                  </p>
                </div>
                <div className="panel p-4" aria-label="Recent station alerts">
                  <p className="section-kicker">Recent alerts</p>
                  <h3 className="mt-1 text-sm font-extrabold">Station anomaly history</h3>
                  {alertsQuery.isPending ? (
                    <p className="mt-2 text-[11px] text-muted-foreground" role="status">
                      Loading alerts…
                    </p>
                  ) : relatedAlerts.length === 0 ? (
                    <p className="mt-2 text-[11px] text-muted-foreground">
                      No stored alerts for this station in the current window.
                    </p>
                  ) : (
                    <div className="mt-2 space-y-1.5">
                      {relatedAlerts.slice(0, 5).map((alert) => (
                        <div
                          key={alert.alert_id}
                          className="rounded-xl border border-border bg-card p-2"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <p className="truncate text-[11px] font-extrabold">{alert.event}</p>
                            <span className="shrink-0 text-[11px] font-extrabold tabular-nums">
                              {formatScore(alert.anomaly_score)}
                            </span>
                          </div>
                          <p className="mt-0.5 text-[10px] text-muted-foreground">
                            {formatDateTime(alert.timestamp)} ·{" "}
                            {cleanText(alert.root_cause) ?? "Root cause not diagnosed"} · Source{" "}
                            {alert.source_mode ?? "HISTORICAL_ALERT"}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>

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
        {relatedAlert ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              navigate({
                to: "/alerts/$alertId",
                params: { alertId: relatedAlert.alert_id },
              })
            }
          >
            <ArrowUpRight />
            Review in alerts
          </Button>
        ) : null}
      </section>
    </>
  );
}
