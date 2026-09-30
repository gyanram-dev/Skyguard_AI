import { Link, createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FlaskConical, Info, Snowflake, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DetailStat,
  EmptyState,
  ErrorState,
  FactRow,
  LoadingState,
  StatusBadge,
} from "@/components/common";
import { ExplanationBlock } from "@/components/evidence";
import { ApiError, normalizeStatus, type ProbeResponse, type StationSummary } from "@/lib/api";
import {
  cleanText,
  errorMessage,
  formatCompactCount,
  formatConfidence,
  formatDisplayTerm,
  formatHumidity,
  formatPressure,
  formatTemp,
} from "@/lib/format";
import { useProbeObservation, useReadiness, useStations } from "@/hooks/useSkyguard";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/judge-probe")({
  head: () => ({
    meta: [{ title: "Test an Observation | SkyGuard AI" }],
  }),
  component: JudgeProbePage,
});

/** True when the backend reports a calibrated station-specific detector. */
function hasCalibratedDetector(station: StationSummary | undefined): boolean {
  return station?.capability?.detector?.detector_available === true;
}

function toNumberInput(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

type FieldErrors = {
  station?: string | undefined;
  temperature?: string | undefined;
  humidity?: string | undefined;
  pressure?: string | undefined;
};

function parseField(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return null;
  return value;
}

/** camel/snake case → readable label (multivariate_* stripped for brevity). */
function humanizeKey(key: string): string {
  const cleaned = key.replace(/^multivariate_/, "").replace(/^(temp|pres|rh)_/, "$1 ");
  return cleaned
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatEvidenceValue(value: unknown): string {
  if (value === null || value === undefined) return "Not available";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }
  if (typeof value === "string") return cleanText(value) ?? "Not available";
  return String(value);
}

function evidenceRows(record: Record<string, unknown>): Array<{ label: string; value: string }> {
  return (
    Object.entries(record)
      // Nested structures (e.g. per-variable maps) are not flattened into
      // meaningless "[object Object]" rows; they are omitted instead.
      .filter(([, value]) => value === null || typeof value !== "object")
      .map(([key, value]) => ({
        label: humanizeKey(key),
        value: formatEvidenceValue(value),
      }))
  );
}

/**
 * Interactive inference workflow. The observation is scored by the backend
 * through the same frozen SkyGuard pipeline (historical station context,
 * never live sensors); every number rendered comes from POST
 * /api/v1/demo/probe.
 */
function JudgeProbePage() {
  const stationsQuery = useStations();
  const readinessQuery = useReadiness();
  // Every station the backend registry exposes is listed — the dropdown is the
  // API response, never a local station list.
  const stations = useMemo(() => stationsQuery.data?.stations ?? [], [stationsQuery.data]);

  // Does this backend report per-station probe capability at all? An absent
  // field is NOT the same as "no station is probeable", so the two cases are
  // handled separately and the UI only claims what the backend actually said.
  const capabilityReported = useMemo(
    () => stations.some((station) => typeof station.probe_available === "boolean"),
    [stations],
  );
  // Legacy fallback: a backend without the per-station flag can still confirm
  // interactive inference through the readiness endpoint.
  const fallbackStationId =
    !capabilityReported && readinessQuery.data?.probe_available
      ? (readinessQuery.data.default_station ?? null)
      : null;
  const probeCapabilityKnown = capabilityReported || fallbackStationId !== null;

  /**
   * Interactive-probe capability, read from the backend flag only — never from
   * a hardcoded station list. The probe executes the frozen ensemble; stations
   * covered solely by a calibrated station-specific detector are listed with
   * their real metadata and are scored during historical replay, so their Run
   * control is gated instead of dead-ending in a 422.
   */
  const probeRunnable = useCallback(
    (station: StationSummary | undefined): boolean => {
      if (!station) return false;
      if (station.probe_available === true) return true;
      return !capabilityReported && station.station_id === fallbackStationId;
    },
    [capabilityReported, fallbackStationId],
  );
  const runnableStations = useMemo(
    () => stations.filter((station) => probeRunnable(station)),
    [stations, probeRunnable],
  );
  const calibratedCount = useMemo(
    () => stations.filter((station) => hasCalibratedDetector(station)).length,
    [stations],
  );
  const contextOnlyCount = Math.max(0, stations.length - runnableStations.length - calibratedCount);
  const probe = useProbeObservation();

  const [stationId, setStationId] = useState<string>("");
  const [temperature, setTemperature] = useState("");
  const [humidity, setHumidity] = useState("");
  const [pressure, setPressure] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const selected = useMemo(
    () => stations.find((station) => station.station_id === stationId) ?? null,
    [stations, stationId],
  );
  const selectedRunnable = probeRunnable(selected ?? undefined);

  useEffect(() => {
    if (stationId !== "" || stations.length === 0) return;
    // Default to the first station the backend can actually score; otherwise
    // the first station it lists. No station ID is hardcoded here.
    const preferred = runnableStations[0] ?? stations[0];
    if (!preferred) return;
    setStationId(preferred.station_id);
    setTemperature(toNumberInput(preferred.temperature));
    setHumidity(toNumberInput(preferred.humidity));
    setPressure(toNumberInput(preferred.pressure));
  }, [stations, runnableStations, stationId]);

  /** Selecting a station loads its real latest observation into the form. */
  const selectStation = (id: string) => {
    setStationId(id);
    setFieldErrors({});
    const row = stations.find((station) => station.station_id === id);
    if (row) {
      setTemperature(toNumberInput(row.temperature));
      setHumidity(toNumberInput(row.humidity));
      setPressure(toNumberInput(row.pressure));
    }
  };

  /**
   * Demo scenarios only fill the form; inference always runs through the
   * backend. Values are scripted inputs, so they are labelled CONTROLLED.
   */
  const applyScenario = (kind: "normal" | "spike") => {
    if (!selected) return;
    setFieldErrors({});
    if (kind === "normal" || selected.temperature === null || selected.temperature === undefined) {
      setTemperature(toNumberInput(selected.temperature));
      setHumidity(toNumberInput(selected.humidity));
      setPressure(toNumberInput(selected.pressure));
      return;
    }
    setTemperature(Math.min(selected.temperature + 25, 69.9).toFixed(1));
    setHumidity(toNumberInput(selected.humidity));
    setPressure(toNumberInput(selected.pressure));
  };

  const submit = () => {
    // Gated station: never send an observation the backend cannot score, so
    // the UI can never imply a verdict that will not exist.
    if (!selectedRunnable) return;
    const errors: FieldErrors = {};
    if (!stationId) errors.station = "Select a station for historical context.";
    const temp = parseField(temperature);
    const hum = parseField(humidity);
    const pres = parseField(pressure);
    if (temp === null) errors.temperature = "Enter a finite temperature in °C.";
    if (hum === null) errors.humidity = "Enter a finite humidity value.";
    else if (hum < 0 || hum > 100) errors.humidity = "Humidity must be within 0–100% RH.";
    if (pres === null) errors.pressure = "Enter a finite pressure in hPa.";
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0 || temp === null || hum === null || pres === null) {
      return;
    }
    probe.mutate({ station_id: stationId, temperature: temp, pressure: pres, humidity: hum });
  };

  // Backend capability metadata for the selected station (real values only).
  const capability = selected?.capability ?? null;
  const detectorState = capability?.detector ?? null;
  const detectorType = cleanText(detectorState?.detector_type);
  const cadence = detectorState?.cadence ?? null;
  const pressureBasis = cleanText(capability?.pressure_basis);
  const qnhPressure = pressureBasis === "altimeter_qnh_hpa";
  const rhProvenance = cleanText(detectorState?.rh_provenance);
  const capabilityNotes = selected?.capability_notes ?? [];
  const historicalWindow = capability
    ? `${formatCompactCount(capability.observation_count) ?? "0"} observations${
        capability.start_time && capability.end_time
          ? ` · ${capability.start_time.slice(0, 10)} → ${capability.end_time.slice(0, 10)}`
          : ""
      }`
    : "Not reported";
  const latestParts = selected
    ? [
        selected.temperature != null ? formatTemp(selected.temperature) : null,
        selected.humidity != null ? formatHumidity(selected.humidity) : null,
        selected.pressure != null ? formatPressure(selected.pressure) : null,
      ].filter((part): part is string => part !== null)
    : [];
  const latestObservation = latestParts.length > 0 ? latestParts.join(" · ") : null;
  const selectedHasDetector = hasCalibratedDetector(selected ?? undefined);
  const capabilityTone = selectedRunnable
    ? "bg-success-soft text-success-deep"
    : selectedHasDetector
      ? "bg-info-soft text-info"
      : "bg-muted text-muted-foreground";
  const capabilityPill = selectedRunnable
    ? "Interactive probe available"
    : selectedHasDetector
      ? "Scored during historical replay"
      : "No detector coverage";

  const scenarios: Array<{
    label: string;
    description: string;
    kind: "normal" | "spike";
  }> = [
    {
      label: "Normal",
      description: "Latest replayed reading for the selected station.",
      kind: "normal",
    },
    {
      label: "Spike-like",
      description: "Elevated temperature, other variables held at the station reading.",
      kind: "spike",
    },
  ];

  return (
    <>
      {stationsQuery.isPending && <LoadingState message="Loading stations for the probe…" />}
      {stationsQuery.isError && (
        <ErrorState
          message={errorMessage(stationsQuery.error)}
          onRetry={() => stationsQuery.refetch()}
        />
      )}
      {!stationsQuery.isPending && !stationsQuery.isError && stations.length === 0 && (
        <EmptyState
          title="No stations reported by the backend."
          message="GET /api/v1/stations returned an empty registry, so no observation can be contextualised. This is not a claim about the network — restart the backend on the current build and retry."
        />
      )}
      {!stationsQuery.isPending && !stationsQuery.isError && stations.length > 0 && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <section className="panel p-4" aria-label="Probe input">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="section-kicker">Observation under test</p>
                <h2 className="mt-1 text-lg font-extrabold">Test an Observation</h2>
              </div>
              {selected && (
                <StatusBadge status={normalizeStatus(selected.status, selected.data_available)} />
              )}
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Pick any station the backend exposes, review its real detector coverage, then enter
              Temperature, Pressure and Relative Humidity. Run SkyGuard sends the observation to the
              backend and renders the backend&apos;s own verdict.
            </p>

            <div className="mt-3 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="probe-station">1. Station</Label>
                <Select value={stationId} onValueChange={selectStation}>
                  <SelectTrigger
                    id="probe-station"
                    aria-label="Station"
                    className={cn(fieldErrors.station && "border-anomaly")}
                  >
                    <SelectValue
                      placeholder={
                        stations.length === 0 ? "No stations reported" : "Select station"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {stations.map((station) => (
                      <SelectItem key={station.station_id} value={station.station_id}>
                        {station.station_id} · {station.city}
                        {probeRunnable(station)
                          ? " · probe available"
                          : hasCalibratedDetector(station)
                            ? " · detector via replay"
                            : " · context only"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {fieldErrors.station && (
                  <p className="text-[10px] font-semibold text-anomaly-deep" role="alert">
                    {fieldErrors.station}
                  </p>
                )}
                {calibratedCount > 0 && (
                  <p className="flex items-start gap-1 text-[10px] text-muted-foreground">
                    <Info className="mt-0.5 size-3 shrink-0" />
                    {calibratedCount} station(s) are scored by their own calibrated station-specific
                    detector during historical replay
                    {contextOnlyCount > 0
                      ? `, and ${contextOnlyCount} carry historical context observations only (no detector)`
                      : ""}
                    . The interactive probe runs the frozen ensemble, so only the{" "}
                    {runnableStations.length} station(s) it covers can be run here.
                  </p>
                )}
                {!probeCapabilityKnown && (
                  <p
                    className="flex items-start gap-1 text-[10px] text-muted-foreground"
                    role="status"
                  >
                    <Info className="mt-0.5 size-3 shrink-0" />
                    This backend did not report interactive probe capability, so no station can be
                    run until it is confirmed.{" "}
                    <button
                      type="button"
                      className="font-bold text-info hover:underline"
                      onClick={() => {
                        stationsQuery.refetch();
                        readinessQuery.refetch();
                      }}
                    >
                      Retry
                    </button>
                  </p>
                )}
              </div>

              {selected && (
                <div
                  className="rounded-xl border border-border p-2.5"
                  aria-label="Selected station capability"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
                      Station capability
                    </p>
                    <span className={cn("status-pill text-[9px]", capabilityTone)}>
                      <span className="status-dot" />
                      {capabilityPill}
                    </span>
                  </div>
                  <div className="mt-1 divide-y divide-border">
                    <FactRow
                      label="Detector coverage"
                      value={formatDisplayTerm(capability?.detector_capability, "Not reported")}
                    />
                    {detectorType && <FactRow label="Detector" value={detectorType} />}
                    <FactRow
                      label="Data source"
                      value={capability?.data_source ?? "Not reported"}
                    />
                    {cadence != null && (
                      <FactRow
                        label="Cadence"
                        value={`${cadence % 1 === 0 ? cadence.toFixed(0) : cadence.toFixed(1)} min`}
                      />
                    )}
                    <FactRow label="Historical data" value={historicalWindow} />
                    <FactRow
                      label="Pressure basis"
                      value={formatDisplayTerm(capability?.pressure_basis, "Not reported")}
                    />
                    {rhProvenance && (
                      <FactRow label="RH provenance" value={formatDisplayTerm(rhProvenance)} />
                    )}
                    {latestObservation && (
                      <FactRow label="Latest observation" value={latestObservation} />
                    )}
                  </div>
                  {capabilityNotes.length > 0 && (
                    <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[10px] leading-snug text-muted-foreground">
                      {capabilityNotes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {selected && !selectedRunnable && (
                <div className="rounded-xl border border-border bg-muted/50 p-2.5" role="status">
                  <p className="text-[11px] font-extrabold">
                    Interactive probe is not available for {selected.station_id}
                  </p>{" "}
                  <p className="mt-1 text-[10px] leading-snug text-muted-foreground">
                    {selectedHasDetector ? (
                      <>
                        {detectorType ? `${detectorType} · ` : ""}
                        this station&apos;s calibrated detector runs on its own real history during
                        historical replay; the frozen ensemble the probe executes does not cover it,
                        so a single observation cannot be scored here.{" "}
                        <Link to="/" className="font-bold text-info hover:underline">
                          Open Historical Replay →
                        </Link>
                      </>
                    ) : (
                      <>
                        No detector covers this station — it carries real historical context
                        observations only, so neither the interactive probe nor historical replay
                        produces a station-level verdict for it.{" "}
                        <Link to="/network-health" className="font-bold text-info hover:underline">
                          View it on the network map →
                        </Link>
                      </>
                    )}
                  </p>
                </div>
              )}

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label htmlFor="probe-temp">2. Temperature (°C)</Label>
                  <Input
                    id="probe-temp"
                    inputMode="decimal"
                    value={temperature}
                    disabled={probe.isPending}
                    onChange={(event) => {
                      setTemperature(event.target.value);
                      setFieldErrors((prev) => ({ ...prev, temperature: undefined }));
                    }}
                    className={cn(fieldErrors.temperature && "border-anomaly")}
                  />
                  {fieldErrors.temperature && (
                    <p className="text-[10px] font-semibold text-anomaly-deep" role="alert">
                      {fieldErrors.temperature}
                    </p>
                  )}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="probe-pressure">
                    {qnhPressure ? "3. Pressure (hPa · QNH altimeter)" : "3. Pressure (hPa)"}
                  </Label>
                  <Input
                    id="probe-pressure"
                    inputMode="decimal"
                    value={pressure}
                    disabled={probe.isPending}
                    onChange={(event) => {
                      setPressure(event.target.value);
                      setFieldErrors((prev) => ({ ...prev, pressure: undefined }));
                    }}
                    className={cn(fieldErrors.pressure && "border-anomaly")}
                  />
                  {qnhPressure && (
                    <p className="text-[10px] leading-snug text-muted-foreground">
                      {formatDisplayTerm(pressureBasis)} — carried as the backend reports it, never
                      relabelled as station pressure.
                    </p>
                  )}
                  {fieldErrors.pressure && (
                    <p className="text-[10px] font-semibold text-anomaly-deep" role="alert">
                      {fieldErrors.pressure}
                    </p>
                  )}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="probe-humidity">4. Humidity (% RH)</Label>
                  <Input
                    id="probe-humidity"
                    inputMode="decimal"
                    value={humidity}
                    disabled={probe.isPending}
                    onChange={(event) => {
                      setHumidity(event.target.value);
                      setFieldErrors((prev) => ({ ...prev, humidity: undefined }));
                    }}
                    className={cn(fieldErrors.humidity && "border-anomaly")}
                  />
                  {fieldErrors.humidity && (
                    <p className="text-[10px] font-semibold text-anomaly-deep" role="alert">
                      {fieldErrors.humidity}
                    </p>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  onClick={submit}
                  disabled={probe.isPending || !selectedRunnable}
                  title={
                    selectedRunnable
                      ? undefined
                      : "The interactive probe runs the frozen ensemble, which does not cover this station."
                  }
                >
                  <FlaskConical />
                  {probe.isPending ? "Running SkyGuard…" : "5. Run SkyGuard"}
                </Button>
                {selected && !selectedRunnable && (
                  <span className="text-[10px] text-muted-foreground">
                    Gated: {selected.station_id} is evaluated during historical replay.
                  </span>
                )}
              </div>
            </div>

            <div className="mt-4 rounded-xl border border-border p-3" aria-label="Demo scenarios">
              <div className="flex items-center gap-2">
                <p className="section-kicker">Demo scenarios</p>
                <span className="rounded-full bg-warning-soft px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-[0.06em] text-warning-deep">
                  Controlled
                </span>
              </div>
              <p className="mt-1 text-[10px] leading-snug text-muted-foreground">
                Scenarios fill the form with scripted values; the decision still comes from the real
                backend pipeline. They are not naturally observed events.
              </p>
              <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {scenarios.map((scenario) => (
                  <button
                    key={scenario.label}
                    type="button"
                    disabled={probe.isPending}
                    onClick={() => applyScenario(scenario.kind)}
                    className="rounded-xl border border-border bg-card p-2.5 text-left transition-colors hover:border-primary/30 hover:bg-info-soft/50 disabled:opacity-60"
                  >
                    <p className="text-[11px] font-extrabold">{scenario.label}</p>
                    <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">
                      {scenario.description}
                    </p>
                  </button>
                ))}
                <div className="rounded-xl border border-dashed border-border bg-muted/50 p-2.5 sm:col-span-2">
                  <p className="flex items-center gap-1.5 text-[11px] font-extrabold">
                    <Snowflake className="size-3.5" />
                    <TrendingUp className="size-3.5" />
                    Frozen / drift scenarios
                  </p>
                  <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">
                    These faults need a sustained series, not a single observation, so the probe
                    cannot generate them reliably. Use{" "}
                    <Link to="/live" className="font-bold text-info hover:underline">
                      live / replay
                    </Link>{" "}
                    to demonstrate continuous behaviour instead.
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section className="panel p-4" aria-label="Probe result" aria-live="polite">
            <p className="section-kicker">Decision & evidence</p>
            <h2 className="mt-1 text-lg font-extrabold">Result</h2>
            {probe.isPending && (
              <p className="mt-2 text-[11px] text-muted-foreground" role="status">
                Scoring the observation through the SkyGuard pipeline…
              </p>
            )}
            {!probe.isPending && probe.isError && (
              <div className="mt-2">
                <ErrorState
                  message={probeErrorMessage(probe.error)}
                  onRetry={() => {
                    if (probe.variables) probe.mutate(probe.variables);
                  }}
                />
              </div>
            )}
            {!probe.isPending && !probe.isError && !probe.data && (
              <p className="mt-2 text-[11px] text-muted-foreground">
                {selected && !selectedRunnable
                  ? `${selected.station_id} is not scored by the interactive probe — its calibrated station-specific detector runs during historical replay, so no probe verdict exists for this station.`
                  : "Configure an observation and run the analysis. The result is generated by the backend through the frozen inference pipeline."}
              </p>
            )}
            {!probe.isPending && probe.data && <ProbeResultView result={probe.data} />}
          </section>
        </div>
      )}
    </>
  );
}

function probeErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code) {
    return `${error.message} (code: ${error.code})`;
  }
  return errorMessage(error);
}

function availabilityLabel(availability: string): string {
  if (availability === "FULL_EVIDENCE") return "Full evidence";
  if (availability === "PARTIAL_EVIDENCE") return "Partial evidence";
  return "Insufficient evidence";
}

function componentText(component: {
  available: boolean;
  raw: number | null;
  calibrated: number | null;
}): string {
  if (!component.available) return "Unavailable";
  const raw =
    component.raw !== null && component.raw !== undefined ? component.raw.toFixed(3) : "—";
  const cal =
    component.calibrated !== null && component.calibrated !== undefined
      ? component.calibrated.toFixed(3)
      : "—";
  return `raw ${raw} · calibrated ${cal}`;
}

function ProbeResultView({ result }: { result: ProbeResponse }) {
  const anomalous = result.result.is_anomalous;
  const spatial = result.evidence.spatial;
  const spatialAvailable = spatial["available"] === true;
  const dq = result.evidence.data_quality;
  const multi = result.evidence.multivariate;
  const hasMultivariate = Object.values(multi).some((value) => value !== null);
  const statistical = result.evidence.statistical;
  const spatialDecision = result.spatial_decision ?? null;

  // Only checks that the backend actually supports are rendered; an absent
  // spatial comparison is never turned into a green tick.
  const consistencyChecks: Array<{ label: string; ok: boolean | null }> = [
    {
      label: statistical.available
        ? "Temporal behaviour consistent"
        : "Temporal behaviour not evaluated",
      ok: statistical.available ? true : null,
    },
    {
      label: hasMultivariate
        ? "Multivariate relationship consistent"
        : "Multivariate relationship not evaluated",
      ok: hasMultivariate ? true : null,
    },
    {
      label: spatialAvailable ? "Spatial context consistent" : "Spatial context unavailable",
      ok: spatialAvailable ? true : null,
    },
  ];

  return (
    <div className="mt-2 space-y-2.5">
      {/* Decision first: the verdict is the point of the demo. */}
      <div
        className={cn(
          "rounded-xl border p-3",
          anomalous
            ? "border-anomaly/30 bg-anomaly-soft text-anomaly"
            : "border-success/30 bg-success-soft text-success",
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="section-kicker">
              {anomalous ? "Anomaly detected" : "Not flagged — consistent with context"}
            </p>
            <p
              className={cn(
                "mt-0.5 text-base font-extrabold",
                anomalous ? "text-anomaly-deep" : "text-success-deep",
              )}
            >
              {anomalous ? "SENSOR ANOMALY" : "NORMAL"}
            </p>
            {anomalous && (
              <p className="mt-0.5 text-[11px] font-semibold text-muted-foreground">
                Root cause:{" "}
                <strong className="text-foreground">
                  {cleanText(result.root_cause.class) ?? "Not diagnosed"}
                </strong>
                {result.root_cause.confidence !== null &&
                  result.root_cause.confidence !== undefined && (
                    <> · {formatConfidence(result.root_cause.confidence)} confidence</>
                  )}
              </p>
            )}
          </div>
          <StatusBadge status={anomalous ? "anomaly" : "healthy"} />
        </div>
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          <DetailStat
            label="Anomaly score"
            value={result.result.anomaly_score?.toFixed(3) ?? "—"}
            emphasis={anomalous}
          />
          <DetailStat
            label="Confidence"
            value={formatConfidence(result.result.confidence)}
            tone="bg-surface-blue-tint"
          />
          <DetailStat
            label="Threshold"
            value={result.result.threshold?.toFixed(3) ?? "—"}
            tone="bg-surface-blue-tint"
          />
        </div>
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          Method {result.result.method} · {availabilityLabel(result.result.availability)}
        </p>
        {result.result.confidence_basis ? (
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            Confidence basis: {result.result.confidence_basis}
          </p>
        ) : null}
      </div>

      {/* Fields are rendered only when the backend actually sent them. The
          frozen ensemble path reports its detector label and severity; the
          calibrated station detectors additionally report contributing
          factors. Nothing here is inferred. */}
      {result.detector ||
      result.severity ||
      result.primary_reason ||
      (result.contributing_factors?.length ?? 0) > 0 ? (
        <div className="rounded-xl border border-border p-2.5">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
            Detector evidence
          </p>
          <div className="mt-1 divide-y divide-border">
            {result.detector ? <FactRow label="Detector" value={result.detector} /> : null}
            {result.severity ? <FactRow label="Severity" value={result.severity} /> : null}
            {result.primary_reason ? (
              <FactRow label="Primary reason" value={result.primary_reason} />
            ) : null}
          </div>
          {(result.contributing_factors?.length ?? 0) > 0 ? (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[11px] text-muted-foreground">
              {result.contributing_factors?.map((factor) => (
                <li key={factor}>{factor}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="grid grid-cols-3 gap-1.5">
        <DetailStat
          label="Temperature"
          value={`${result.probe.temperature.toFixed(1)} °C`}
          emphasis={anomalous}
        />
        <DetailStat
          label="Pressure"
          value={`${result.probe.pressure.toFixed(1)} hPa`}
          tone="bg-surface-blue-tint"
        />
        <DetailStat
          label="Humidity"
          value={`${result.probe.humidity.toFixed(1)} %`}
          tone="bg-surface-blue-tint"
        />
      </div>

      {!anomalous && (
        <div className="rounded-xl border border-border p-2.5">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">Why?</p>
          <ul className="mt-1.5 space-y-1">
            {consistencyChecks.map((check) => (
              <li key={check.label} className="flex items-start gap-1.5 text-[11px]">
                <span
                  className={cn(
                    "mt-0.5 font-extrabold",
                    check.ok === true
                      ? "text-success-deep"
                      : check.ok === false
                        ? "text-anomaly-deep"
                        : "text-muted-foreground",
                  )}
                >
                  {check.ok === true ? "✓" : check.ok === false ? "✕" : "–"}
                </span>
                <span className="text-muted-foreground">{check.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
          Why this assessment?
        </p>
        <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
          {cleanText(result.explanation.text) ?? "Explanation not available."}
        </p>
      </div>

      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">Temporal evidence</p>
        <div className="mt-1 divide-y divide-border">
          <FactRow label="Statistical (z max)" value={componentText(statistical)} />
          <FactRow
            label="Data quality"
            value={`${String(dq["status"] ?? "Unknown")} · ML ${
              dq["ml_eligible"] ? "eligible" : "ineligible"
            }`}
          />
        </div>
      </div>

      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
          Multivariate evidence
        </p>
        {hasMultivariate ? (
          <div className="mt-1 divide-y divide-border">
            {Object.entries(multi).map(([key, value]) => (
              <FactRow key={key} label={humanizeKey(key)} value={formatEvidenceValue(value)} />
            ))}
          </div>
        ) : (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Multivariate evidence unavailable for this observation.
          </p>
        )}
      </div>

      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">Spatial evidence</p>
        {spatialDecision ? (
          <div className="mt-1 divide-y divide-border">
            <FactRow label="Base decision" value={String(spatialDecision.base_decision ?? "—")} />
            <FactRow
              label="Interpretation"
              value={String(spatialDecision.contextual_decision ?? "—")}
            />
            {spatialDecision.description ? (
              <p className="py-1 text-[11px] leading-snug text-muted-foreground">
                {spatialDecision.description}
              </p>
            ) : null}
          </div>
        ) : null}
        {spatialAvailable ? (
          <div className="mt-1 divide-y divide-border">
            {evidenceRows(spatial).map((row) => (
              <FactRow key={row.label} label={row.label} value={row.value} />
            ))}
          </div>
        ) : (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Spatial context unavailable for this station — no neighbour values invented.
          </p>
        )}
      </div>

      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
          Seasonal reference (same hour, earlier days)
        </p>
        {result.evidence.seasonal && result.evidence.seasonal["available"] === true ? (
          <div className="mt-1 divide-y divide-border">
            <FactRow
              label="Same-hour median"
              value={
                typeof result.evidence.seasonal["same_hour_median"] === "number"
                  ? `${(result.evidence.seasonal["same_hour_median"] as number).toFixed(1)}°C`
                  : "—"
              }
            />
            <FactRow
              label="Deviation"
              value={
                typeof result.evidence.seasonal["deviation"] === "number"
                  ? `${(result.evidence.seasonal["deviation"] as number) >= 0 ? "+" : ""}${(result.evidence.seasonal["deviation"] as number).toFixed(1)}°C`
                  : "—"
              }
            />
            <FactRow
              label="Days of history"
              value={String(result.evidence.seasonal["n_days"] ?? "—")}
            />
          </div>
        ) : (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Seasonal reference unavailable for this observation — descriptive history only, never a
            substitute for detection.
          </p>
        )}
      </div>

      {result.recommended_action ? (
        <div className="rounded-xl border border-border p-2.5">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
            Recommended operator action
          </p>
          <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
            {result.recommended_action} (Recommendation, not a physical repair.)
          </p>
        </div>
      ) : null}

      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">Model evidence</p>
        <div className="mt-1 divide-y divide-border">
          <FactRow
            label="Isolation Forest"
            value={componentText(result.evidence.isolation_forest)}
          />
          <FactRow label="LSTM reconstruction" value={componentText(result.evidence.lstm)} />
          <FactRow
            label="Root cause"
            value={
              cleanText(result.root_cause.class) === null
                ? "No fault pattern diagnosed"
                : `${cleanText(result.root_cause.class)}${
                    result.root_cause.confidence !== null &&
                    result.root_cause.confidence !== undefined
                      ? ` · ${formatConfidence(result.root_cause.confidence)}`
                      : ""
                  }`
            }
          />
          {cleanText(result.root_cause.runner_up) && (
            <FactRow label="Runner-up" value={String(result.root_cause.runner_up)} />
          )}
        </div>
        <p className="mt-1 text-[10px] text-muted-foreground">
          Root cause is a model prediction to aid review — not a confirmed physical diagnosis.
        </p>
      </div>

      {result.explanation.features.length > 0 && (
        <ExplanationBlock explanation={result.explanation} loading={false} />
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="outline">
          <Link to="/alerts">Open alerts queue →</Link>
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link to="/investigations">Open investigations →</Link>
        </Button>
      </div>

      <p className="text-[10px] leading-snug text-muted-foreground">
        {result.context.context_note} Data mode: {result.data_mode} (interactive historical replay,
        not a live sensor feed). This probe does not create a stored alert — open an alert or a
        replay anomaly to see the investigation workspace.
      </p>
    </div>
  );
}
