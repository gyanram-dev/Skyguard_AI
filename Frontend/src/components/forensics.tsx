/**
 * Station forensic analysis: dataset -> timeline -> detector events ->
 * selected event -> evidence -> spatial context.
 *
 * Every value rendered here comes from the backend responses already in use
 * (timeline artifact, investigation hub). The panel never computes a verdict,
 * never invents a neighbour value, and states "Not available" instead of
 * filling a gap.
 */

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/common";
import {
  severityColor,
  StationForensicsChart,
  VARIABLE_COLORS,
  type ForensicsVariable,
  type ForensicsSeries,
} from "@/components/charts";
import {
  type InvestigationResponse,
  type SpatialVariableEvidence,
  type TimelineEvent,
  type TimelineResponse,
} from "@/lib/api";
import {
  cleanText,
  errorMessage,
  formatConfidence,
  formatHumidity,
  formatPressure,
  formatScore,
  formatTemp,
} from "@/lib/format";
import { useStationInvestigation, useStationTimeline } from "@/hooks/useSkyguard";

const VARIABLES: Array<{ key: ForensicsVariable; label: string }> = [
  { key: "temperature", label: "Temperature" },
  { key: "humidity", label: "Relative Humidity" },
  { key: "pressure", label: "Pressure" },
];

const SEVERITY_LEGEND = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

/** Full date with year: a multi-year station record must not read as days. */
function fullDate(value: string | null | undefined): string {
  if (!value) return "Not available";
  const date = new Date(value.replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  return `${(value * 100).toFixed(0)}%`;
}

function signed(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "Not available";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function variableOf(event: TimelineEvent | null): ForensicsVariable {
  const name = (event?.variable ?? event?.baseline_variable ?? "").toLowerCase();
  if (name.startsWith("pressure")) return "pressure";
  if (name.startsWith("hum")) return "humidity";
  return "temperature";
}

function valueFor(event: TimelineEvent, variable: ForensicsVariable): number | null {
  if (variable === "humidity") return event.humidity ?? null;
  if (variable === "pressure") return event.pressure ?? null;
  return event.temperature ?? event.observed ?? null;
}

function formatVariableValue(
  value: number | null | undefined,
  variable: ForensicsVariable,
): string {
  if (value === null || value === undefined) return "Not available";
  if (variable === "humidity") return formatHumidity(value);
  if (variable === "pressure") return formatPressure(value);
  return formatTemp(value);
}

function variableLabel(variable: ForensicsVariable): string {
  return variable === "humidity"
    ? "Relative humidity"
    : variable === "pressure"
      ? "Pressure"
      : "Temperature";
}

function evidenceStatusLabel(status: string | undefined): string {
  switch (status) {
    case "SPATIAL_CONTRADICTED":
      return "CONTRADICTED";
    case "SPATIAL_SUPPORTED":
      return "SUPPORTED";
    case "SPATIAL_INSUFFICIENT":
      return "INSUFFICIENT";
    default:
      return "UNAVAILABLE";
  }
}

function evidenceStatusTone(status: string | undefined): string {
  if (status === "SPATIAL_CONTRADICTED") return "text-anomaly-deep";
  if (status === "SPATIAL_SUPPORTED") return "text-warning-deep";
  return "text-muted-foreground";
}

/** Spatial evidence for the selected event, from the existing spatial layer. */
function EventSpatialContext({
  investigation,
  loading,
  error,
  onRetry,
}: {
  investigation: InvestigationResponse | undefined;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (loading && !investigation) {
    return (
      <p className="text-[11px] text-muted-foreground" role="status">
        Comparing with nearby stations…
      </p>
    );
  }
  if (error && !investigation) {
    return <ErrorState message={error} onRetry={onRetry} />;
  }
  if (!investigation) return null;
  const comparison = investigation.comparison;
  const temperature = comparison.temperature;
  const nearby = investigation.nearby;
  const humidity = comparison.humidity;
  // Per-dimension neighbour relations exactly as the spatial layer returned
  // them — a neighbour is never labelled corroborating or differing by us.
  const relations: Array<{
    key: string;
    label: string;
    support: Set<string>;
    against: Set<string>;
  }> = [
    {
      key: "temperature",
      label: "temperature",
      support: new Set(temperature.supporting_neighbors ?? []),
      against: new Set(temperature.contradicting_neighbors ?? []),
    },
    {
      key: "humidity",
      label: "RH",
      support: new Set(humidity?.supporting_neighbors ?? []),
      against: new Set(humidity?.contradicting_neighbors ?? []),
    },
  ];
  const neighbourRelation = (backendId: string | null | undefined): string => {
    const bits: string[] = [];
    for (const relation of relations) {
      if (relation.against.has(backendId ?? "")) bits.push(`${relation.label} differs`);
      else if (relation.support.has(backendId ?? "")) bits.push(`${relation.label} near group`);
    }
    return bits.length > 0 ? bits.join(" · ") : "not comparable";
  };
  const decision = investigation.interpretation.contextual_decision;
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
          Spatial context
        </p>
        <p className={`text-[11px] font-extrabold ${evidenceStatusTone(temperature.status)}`}>
          {decision.replace(/_/g, " ")}
        </p>
      </div>
      {nearby.length === 0 ? (
        <p className="mt-1 text-[11px] text-warning-deep">
          Insufficient nearby observations — no neighbour values are invented.
        </p>
      ) : (
        <>
          <div className="mt-1 overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-left uppercase tracking-[0.06em] text-muted-foreground">
                  <th className="py-0.5 pr-2 font-extrabold">Station</th>
                  <th className="py-0.5 pr-2 font-extrabold">Distance</th>
                  <th className="py-0.5 pr-2 font-extrabold">Temperature</th>
                  <th className="py-0.5 pr-2 font-extrabold">RH</th>
                  <th className="py-0.5 font-extrabold">Vs group</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t border-border bg-anomaly-soft/40">
                  <td className="py-1 pr-2 font-extrabold">{investigation.station_id} (target)</td>
                  <td className="py-1 pr-2 text-muted-foreground">—</td>
                  <td className="py-1 pr-2 font-bold tabular-nums">
                    {formatTemp(investigation.target_observation.temperature_c)}
                  </td>
                  <td className="py-1 pr-2 tabular-nums">
                    {formatHumidity(investigation.target_observation.relative_humidity_pct)}
                  </td>
                  <td className="py-1 font-bold text-anomaly-deep">
                    {evidenceStatusLabel(temperature.status)}
                  </td>
                </tr>
                {nearby.map((neighbor) => (
                  <tr key={neighbor.station_id} className="border-t border-border">
                    <td className="py-1 pr-2">
                      {neighbor.station_id} · {neighbor.city}
                    </td>
                    <td className="py-1 pr-2 tabular-nums text-muted-foreground">
                      {neighbor.distance_km === null
                        ? "—"
                        : `${neighbor.distance_km.toFixed(0)} km`}
                    </td>
                    <td className="py-1 pr-2 tabular-nums">{formatTemp(neighbor.temperature)}</td>
                    <td className="py-1 pr-2 tabular-nums">{formatHumidity(neighbor.humidity)}</td>
                    <td className="py-1 text-muted-foreground">
                      {neighbourRelation(neighbor.backend_station_id)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-1.5 grid grid-cols-3 gap-2 text-[11px]">
            <div className="rounded-lg border border-border bg-card px-2 py-1">
              <p className="text-[10px] text-muted-foreground">Neighbour median</p>
              <p className="font-bold tabular-nums">
                {formatTemp(comparison.neighbor_median_temperature)}
              </p>
            </div>
            <div className="rounded-lg border border-border bg-card px-2 py-1">
              <p className="text-[10px] text-muted-foreground">Deviation</p>
              <p className="font-bold tabular-nums">
                {comparison.temperature_deviation === null
                  ? "Not available"
                  : `${signed(comparison.temperature_deviation)} °C`}
              </p>
            </div>
            <div className="rounded-lg border border-border bg-card px-2 py-1">
              <p className="text-[10px] text-muted-foreground">Robust score</p>
              <p className="font-bold tabular-nums">{formatScore(temperature.robust_score)}</p>
            </div>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground">
            {(
              [
                ["Temperature", comparison.temperature],
                ["Relative humidity", comparison.humidity],
                ["Pressure", comparison.pressure],
              ] as Array<[string, SpatialVariableEvidence]>
            ).map(([label, evidence]) => (
              <span key={label}>
                {label}:{" "}
                <span className="font-semibold text-foreground">
                  {evidenceStatusLabel(evidence.status)}
                </span>
              </span>
            ))}
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {temperature.usable_neighbor_count}/{temperature.neighbor_count} audited neighbours
            usable · {investigation.interpretation.description}
            {temperature.reason ? ` · ${temperature.reason.replace(/_/g, " ")}` : ""}
          </p>
        </>
      )}
    </div>
  );
}

function EvidenceItem({
  label,
  children,
  tone,
}: {
  label: string;
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-border py-1 last:border-0">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className={`text-[13px] font-semibold tabular-nums ${tone ?? ""}`}>{children}</span>
    </div>
  );
}

function EventEvidence({
  event,
  stationId,
  eventsHint,
}: {
  event: TimelineEvent | null;
  stationId: string;
  eventsHint: string;
}) {
  const variable = variableOf(event);
  const investigation = useStationInvestigation(stationId, event?.timestamp ?? null);
  if (!event) {
    return (
      <div className="flex h-full min-h-[260px] flex-col" aria-label="Event evidence empty state">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
          Event evidence
        </p>
        <div className="flex flex-1 flex-col items-center justify-center border-y border-dashed border-border py-6 text-center">
          <p className="text-[13px] font-semibold">
            Select a detector event to inspect its evidence.
          </p>
          <p className="mt-1 max-w-[320px] text-[11px] text-muted-foreground">
            The selected event shows its parameter, observed value, causal station baseline,
            deviation, anomaly score, confidence, primary reason, contributing factors, data
            quality, detector evidence and spatial context.
          </p>
        </div>
        <p className="mt-1 text-[10px] text-muted-foreground">{eventsHint}</p>
      </div>
    );
  }
  const observed = valueFor(event, variable);
  const baseline = event.baseline_median ?? null;
  const deviation = event.deviation ?? null;
  const evidence = event.evidence ?? {};
  const rawEvidence: Array<[string, string]> = [];
  for (const [key, value] of Object.entries(evidence)) {
    if (value === null || value === undefined || value === "") continue;
    rawEvidence.push([key.replace(/_/g, " "), String(value)]);
  }
  return (
    <div aria-label="Event evidence">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
            Event evidence
          </p>
          <h4 className="mt-0.5 text-[15px] font-extrabold">
            {cleanText(event.pattern) ?? "Detector event"} · {variableLabel(variable)}
          </h4>
          <p className="text-[11px] text-muted-foreground">{fullDate(event.timestamp)}</p>
        </div>
        <span
          className="rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.06em]"
          style={{
            color: severityColor(event.severity),
            border: `1px solid ${severityColor(event.severity)}`,
          }}
        >
          {cleanText(event.severity) ?? "severity not available"}
        </span>
      </div>

      <div className="mt-2">
        <EvidenceItem label="Observed">{formatVariableValue(observed, variable)}</EvidenceItem>
        <EvidenceItem label="Station baseline">
          {baseline === null ? (
            <span className="text-muted-foreground">Not available</span>
          ) : (
            formatVariableValue(baseline, variable)
          )}
        </EvidenceItem>
        <EvidenceItem
          label="Deviation"
          tone={deviation !== null && Math.abs(deviation) > 2 ? "text-anomaly-deep" : ""}
        >
          {deviation === null
            ? "Not available"
            : `${signed(deviation, variable === "humidity" ? 1 : 2)} ${
                variable === "humidity" ? "% RH" : variable === "pressure" ? "hPa" : "°C"
              }`}
        </EvidenceItem>
        <EvidenceItem label="Anomaly score">{formatScore(event.score)}</EvidenceItem>
        <EvidenceItem label="Threshold">{formatScore(event.threshold)}</EvidenceItem>
        <EvidenceItem label="Confidence">{formatConfidence(event.confidence)}</EvidenceItem>
        <EvidenceItem label="Detector">
          <span className="font-normal">{cleanText(event.detector) ?? "Not available"}</span>
        </EvidenceItem>
        <EvidenceItem label="Trigger">{cleanText(event.trigger) ?? "Not available"}</EvidenceItem>
        <EvidenceItem label="Data quality">
          {cleanText(event.data_quality) ?? "Not available"}
        </EvidenceItem>
      </div>

      {event.reason && (
        <div className="mt-2">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
            Primary reason
          </p>
          <p className="mt-0.5 text-[12px] leading-snug">{event.reason}</p>
        </div>
      )}
      {(event.contributing_factors ?? []).length > 0 && (
        <div className="mt-2">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
            Contributing factors
          </p>
          <ul className="mt-0.5 space-y-0.5">
            {(event.contributing_factors ?? []).map((factor) => (
              <li key={factor} className="text-[12px] leading-snug">
                • {factor}
              </li>
            ))}
          </ul>
        </div>
      )}
      {rawEvidence.length > 0 && (
        <div className="mt-2">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
            Detector evidence
          </p>
          <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
            {rawEvidence.map(([key, value]) => (
              <span key={key} className="text-[11px] text-muted-foreground">
                {key}: <span className="font-semibold text-foreground">{value}</span>
              </span>
            ))}
          </div>
        </div>
      )}
      {event.baseline_basis && (
        <p className="mt-1 text-[10px] text-muted-foreground">
          Baseline definition: {event.baseline_basis}.
        </p>
      )}

      <div className="mt-3 border-t border-border pt-2">
        <EventSpatialContext
          investigation={investigation.data}
          loading={investigation.isPending}
          error={investigation.isError ? errorMessage(investigation.error) : null}
          onRetry={() => investigation.refetch()}
        />
      </div>
    </div>
  );
}

function DetectorMetadata({ data }: { data: TimelineResponse }) {
  const detector = data.detector;
  return (
    <div className="grid grid-cols-1 gap-x-4 gap-y-1 border-y border-border py-2 sm:grid-cols-2 lg:grid-cols-4">
      <div>
        <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
          Detector
        </p>
        <p className="text-[12px] font-semibold">
          {cleanText(detector.detector_type) ?? "No detector covers this station"}
        </p>
      </div>
      <div>
        <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
          Coverage
        </p>
        <p className="text-[12px] font-semibold">
          {detector.coverage.replace(/_/g, " ")}
          {detector.threshold !== null
            ? ` · rule threshold ${detector.threshold}${
                detector.iqr_factor ? ` / IQR ${detector.iqr_factor}` : ""
              }`
            : ""}
        </p>
      </div>
      <div>
        <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
          Verdict window
        </p>
        <p className="text-[12px] font-semibold">
          {detector.coverage_window
            ? `${fullDate(detector.coverage_window.start)} → ${fullDate(detector.coverage_window.end)}`
            : "Not covered"}
        </p>
      </div>
      <div>
        <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
          Detector-flagged observations
        </p>
        <p className="text-[12px] font-semibold tabular-nums">
          {detector.flags_total.toLocaleString()}
          {detector.flag_rate !== null && detector.flag_rate !== undefined
            ? ` · ${percent(detector.flag_rate)} of rows`
            : ""}
        </p>
        <p className="text-[10px] text-muted-foreground">
          {data.events_returned.toLocaleString()} sampled evenly across the period for display
        </p>
      </div>
    </div>
  );
}

export function StationForensicsPanel({
  stationId,
  selectedTimestamp,
  onSelectEvent,
}: {
  stationId: string;
  selectedTimestamp: string | null;
  onSelectEvent: (timestamp: string | null) => void;
}) {
  const timelineQuery = useStationTimeline(stationId);
  const [variable, setVariable] = useState<ForensicsVariable>("temperature");

  const data = timelineQuery.data;
  const events = useMemo(() => data?.events ?? [], [data]);
  const selectedEvent = useMemo(
    () => events.find((event) => event.timestamp === selectedTimestamp) ?? null,
    [events, selectedTimestamp],
  );

  if (timelineQuery.isPending) {
    return (
      <section className="panel p-4" aria-label="Historical timeline">
        <p className="section-kicker">Historical analysis</p>
        <p className="mt-2 text-[12px] text-muted-foreground" role="status">
          Loading the station record…
        </p>
      </section>
    );
  }
  if (timelineQuery.isError) {
    return (
      <section className="panel p-4" aria-label="Historical timeline">
        <p className="section-kicker">Historical analysis</p>
        <div className="mt-2">
          <ErrorState
            message={errorMessage(timelineQuery.error)}
            onRetry={() => timelineQuery.refetch()}
          />
        </div>
      </section>
    );
  }
  if (!data) return null;

  const series: ForensicsSeries = {
    timestamps: data.series.timestamps ?? [],
    temperature: data.series.temperature ?? [],
    humidity: data.series.humidity ?? [],
    pressure: data.series.pressure ?? [],
  };
  const detector = data.detector;

  return (
    <section className="panel p-4" aria-label="Historical timeline">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="section-kicker">Historical analysis</p>
          <h3 className="mt-1 text-[20px] font-extrabold leading-tight">
            {data.station_id} · {data.city} — recorded period
          </h3>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            {fullDate(data.period.start)} → {fullDate(data.period.end)} ·{" "}
            {data.observations.toLocaleString()} real observations
            {data.cadence_min ? ` · ${data.cadence_min} min cadence` : ""} ·{" "}
            {cleanText(data.data_source) ?? "source not recorded"}
            {data.pressure_basis
              ? ` · pressure basis: ${data.pressure_basis.replace(/_/g, " ")}`
              : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Variable switcher">
          {VARIABLES.map((entry) => (
            <Button
              key={entry.key}
              size="sm"
              variant={entry.key === variable ? "default" : "outline"}
              className="h-7 px-2.5 text-[11px]"
              onClick={() => setVariable(entry.key)}
            >
              {entry.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="mt-2">
        <DetectorMetadata data={data} />
      </div>

      {!detector.available && (
        <div
          className="mt-2 rounded-lg border border-warning/40 bg-warning-soft px-3 py-2 text-[11px] text-warning-deep"
          role="note"
        >
          <p className="font-extrabold">HISTORICAL DATA — DETECTOR VERDICT UNAVAILABLE</p>
          <p className="mt-0.5">
            {detector.note ??
              "No stored detector output covers this station, so no anomaly verdict is available."}
          </p>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
        {VARIABLES.map((entry) => (
          <span key={entry.key} className="flex items-center gap-1.5 text-[11px]">
            <i
              className="size-2.5 rounded-full"
              style={{ backgroundColor: VARIABLE_COLORS[entry.key] }}
            />
            <span className={entry.key === variable ? "font-semibold" : "text-muted-foreground"}>
              {entry.label}
            </span>
          </span>
        ))}
        <span className="mx-1 h-3 w-px bg-border" />
        <span className="text-[11px] uppercase tracking-[0.06em] text-muted-foreground">
          Detector event severity
        </span>
        {SEVERITY_LEGEND.map((band) => (
          <span key={band} className="flex items-center gap-1.5 text-[11px]">
            <i className="size-2.5 rounded-full" style={{ backgroundColor: severityColor(band) }} />
            <span className="text-muted-foreground">{band.toLowerCase()}</span>
          </span>
        ))}
      </div>

      <div className="mt-1">
        <StationForensicsChart
          series={series}
          events={events}
          primary={variable}
          selectedTimestamp={selectedTimestamp}
          onSelectMarker={(timestamp) =>
            onSelectEvent(timestamp === selectedTimestamp ? null : timestamp)
          }
          ariaLabel={`${data.station_id} full-period timeline with detector events`}
        />
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Coloured line: real recorded observations (missing values stay gaps; no smoothing). Dots:
        detector events on this station's own record. Click a dot or an event below to inspect its
        evidence.
      </p>

      <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,55fr)_minmax(0,45fr)]">
        <div
          className="rounded-lg border border-border bg-card/40 p-2"
          aria-label="Detector events"
        >
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
              Detector events
            </p>
            <span className="text-[10px] text-muted-foreground tabular-nums">
              {data.events_returned.toLocaleString()} of {detector.flags_total.toLocaleString()}{" "}
              flagged
            </span>
          </div>
          {events.length === 0 ? (
            <p className="mt-2 text-[12px] text-muted-foreground">
              No detector-flagged observations are stored for this station.
            </p>
          ) : (
            <div className="mt-1 max-h-[420px] space-y-0.5 overflow-y-auto pr-1">
              {events.map((event) => {
                const active = event.timestamp === selectedTimestamp;
                const eventVariable = variableOf(event);
                return (
                  <button
                    key={`${event.timestamp}-${event.pattern ?? ""}-${event.variable ?? ""}`}
                    type="button"
                    onClick={() => onSelectEvent(active ? null : event.timestamp)}
                    className={`flex w-full items-center justify-between gap-2 rounded-md border px-2 py-1 text-left ${
                      active
                        ? "border-primary/60 bg-primary/10"
                        : "border-transparent hover:border-border hover:bg-card"
                    }`}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <i
                        className="size-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: severityColor(event.severity) }}
                      />
                      <span className="truncate text-[13px] font-semibold">
                        {cleanText(event.pattern) ?? "EVENT"} · {variableLabel(eventVariable)}
                      </span>
                    </span>
                    <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                      {fullDate(event.timestamp)}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-border bg-card/40 p-2">
          <EventEvidence
            event={selectedEvent}
            stationId={stationId}
            eventsHint={
              detector.available
                ? `${detector.detector_type ?? "Detector"} · ${data.events_returned.toLocaleString()} events listed from ${detector.flags_total.toLocaleString()} flagged observations.`
                : "No detector covers this station, so no event evidence exists."
            }
          />
        </div>
      </div>
    </section>
  );
}
