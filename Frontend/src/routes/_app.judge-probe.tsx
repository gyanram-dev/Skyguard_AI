import { Link, createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
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
import { ApiError, normalizeStatus, type ProbeResponse } from "@/lib/api";
import { cleanText, errorMessage, formatConfidence, formatTemp } from "@/lib/format";
import { useProbeObservation, useReadiness, useStations } from "@/hooks/useSkyguard";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/judge-probe")({
  head: () => ({
    meta: [{ title: "Test an Observation | SkyGuard AI" }],
  }),
  component: JudgeProbePage,
});

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
  const stations = useMemo(() => stationsQuery.data?.stations ?? [], [stationsQuery.data]);

  // Does this backend report per-station detector coverage at all? An absent
  // field is NOT the same as "no station is probeable", so the two cases are
  // handled separately and the empty state only claims what we can prove.
  const capabilityReported = useMemo(
    () => stations.some((station) => typeof station.probe_available === "boolean"),
    [stations],
  );

  // Only stations with detector coverage can be probed; contextual-only
  // stations would dead-end, so they are surfaced separately instead. When the
  // backend does not report the flag, the readiness endpoint is the remaining
  // authoritative signal for whether interactive inference can run.
  const fallbackStationId =
    !capabilityReported && readinessQuery.data?.probe_available
      ? (readinessQuery.data.default_station ?? null)
      : null;
  const probeableStations = useMemo(() => {
    if (capabilityReported) {
      return stations.filter((station) => station.probe_available === true);
    }
    if (fallbackStationId) {
      return stations.filter((station) => station.station_id === fallbackStationId);
    }
    return [];
  }, [stations, capabilityReported, fallbackStationId]);
  const usingReadinessFallback = !capabilityReported && probeableStations.length > 0;
  const contextualOnlyCount = capabilityReported ? stations.length - probeableStations.length : 0;
  // Confirmed dead end only when the backend itself reports zero coverage.
  const coverageConfirmedEmpty =
    !stationsQuery.isPending &&
    !stationsQuery.isError &&
    capabilityReported &&
    probeableStations.length === 0;
  const capabilityUnknown =
    !stationsQuery.isPending &&
    !stationsQuery.isError &&
    !capabilityReported &&
    probeableStations.length === 0;
  const probe = useProbeObservation();

  const [stationId, setStationId] = useState<string>("");
  const [temperature, setTemperature] = useState("");
  const [humidity, setHumidity] = useState("");
  const [pressure, setPressure] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const selected = useMemo(
    () => probeableStations.find((station) => station.station_id === stationId),
    [probeableStations, stationId],
  );

  useEffect(() => {
    if (stationId === "" && probeableStations.length > 0) {
      const preferred =
        probeableStations.find((station) => station.station_id === "DEL-01") ??
        probeableStations[0];
      if (preferred) {
        setStationId(preferred.station_id);
        setTemperature(toNumberInput(preferred.temperature));
        setHumidity(toNumberInput(preferred.humidity));
        setPressure(toNumberInput(preferred.pressure));
      }
    }
  }, [probeableStations, stationId]);

  const prefill = (id: string) => {
    setStationId(id);
    setFieldErrors({});
    const row = probeableStations.find((station) => station.station_id === id);
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
    const row = probeableStations.find((station) => station.station_id === stationId) ?? selected;
    if (!row) return;
    setFieldErrors({});
    if (kind === "normal" || row.temperature === null || row.temperature === undefined) {
      setTemperature(toNumberInput(row.temperature));
      setHumidity(toNumberInput(row.humidity));
      setPressure(toNumberInput(row.pressure));
      return;
    }
    setTemperature(Math.min(row.temperature + 25, 69.9).toFixed(1));
    setHumidity(toNumberInput(row.humidity));
    setPressure(toNumberInput(row.pressure));
  };

  const submit = () => {
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

  const scenarios: Array<{
    label: string;
    description: string;
    kind: "normal" | "spike";
    available: boolean;
  }> = [
    {
      label: "Normal",
      description: "Latest replayed reading for the selected station.",
      kind: "normal",
      available: true,
    },
    {
      label: "Spike-like",
      description: "Elevated temperature, other variables held at the station reading.",
      kind: "spike",
      available: true,
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
      {coverageConfirmedEmpty && (
        <EmptyState
          title="No stations currently have interactive detector coverage."
          message="The backend reports detector coverage for zero stations. Contextual-only stations still appear on the network map."
        />
      )}
      {capabilityUnknown &&
        (readinessQuery.isPending ? (
          <LoadingState message="Checking interactive probe capability…" />
        ) : (
          <section className="panel p-4" aria-label="Probe capability unknown">
            <p className="text-xs font-extrabold">Probe capability could not be confirmed</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              This backend did not report per-station detector coverage, and the readiness check did
              not confirm a probe station. This is not a statement that no station has coverage —
              restart the backend on the current build and retry.
            </p>
            <Button
              className="mt-2"
              size="sm"
              variant="outline"
              onClick={() => {
                stationsQuery.refetch();
                readinessQuery.refetch();
              }}
            >
              Retry
            </Button>
          </section>
        ))}
      {!stationsQuery.isPending && !stationsQuery.isError && probeableStations.length > 0 && (
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
              Pick a station, enter Temperature, Pressure and Relative Humidity, then let SkyGuard
              score the observation through the same pipeline used for operational alerts.
            </p>

            <div className="mt-3 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="probe-station">1. Station</Label>
                <Select value={stationId} onValueChange={prefill}>
                  <SelectTrigger
                    id="probe-station"
                    aria-label="Station"
                    className={cn(fieldErrors.station && "border-anomaly")}
                  >
                    <SelectValue placeholder="Select station" />
                  </SelectTrigger>
                  <SelectContent>
                    {probeableStations.map((station) => (
                      <SelectItem key={station.station_id} value={station.station_id}>
                        {station.station_id} · {station.city} · {formatTemp(station.temperature)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {fieldErrors.station && (
                  <p className="text-[10px] font-semibold text-anomaly-deep" role="alert">
                    {fieldErrors.station}
                  </p>
                )}
                {contextualOnlyCount > 0 && (
                  <p className="flex items-start gap-1 text-[10px] text-muted-foreground">
                    <Info className="mt-0.5 size-3 shrink-0" />
                    {contextualOnlyCount} other Indian station(s) carry historical context
                    observations only — no detector covers them, so they are not probeable.
                  </p>
                )}
                {usingReadinessFallback && (
                  <p className="flex items-start gap-1 text-[10px] text-muted-foreground">
                    <Info className="mt-0.5 size-3 shrink-0" />
                    This backend does not report per-station coverage; the readiness check confirms
                    that interactive inference can run.
                  </p>
                )}
              </div>

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
                  <Label htmlFor="probe-pressure">3. Pressure (hPa)</Label>
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

              <Button size="sm" onClick={submit} disabled={probe.isPending}>
                <FlaskConical />
                {probe.isPending ? "Running SkyGuard…" : "5. Run SkyGuard"}
              </Button>
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
                Configure an observation and run the analysis. The result is generated by the
                backend through the frozen inference pipeline.
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
      </div>

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
            Seasonal reference unavailable for this observation — descriptive history only,
            never a substitute for detection.
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
