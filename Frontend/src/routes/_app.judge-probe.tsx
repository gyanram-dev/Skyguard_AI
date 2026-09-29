import { Link, createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";

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
import { useProbeObservation, useStations } from "@/hooks/useSkyguard";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/judge-probe")({
  head: () => ({
    meta: [{ title: "Judge Probe | SkyGuard AI" }],
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

/**
 * Interactive inference workflow. The observation is scored by the backend
 * through the same frozen SkyGuard pipeline (historical station context,
 * never live sensors); every number rendered comes from POST
 * /api/v1/demo/probe.
 */
function JudgeProbePage() {
  const stationsQuery = useStations();
  const stations = useMemo(() => stationsQuery.data?.stations ?? [], [stationsQuery.data]);
  const availableStations = useMemo(
    () => stations.filter((station) => station.data_available),
    [stations],
  );
  const probe = useProbeObservation();

  const [stationId, setStationId] = useState<string>("");
  const [temperature, setTemperature] = useState("");
  const [humidity, setHumidity] = useState("");
  const [pressure, setPressure] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const selected = useMemo(
    () => availableStations.find((station) => station.station_id === stationId),
    [availableStations, stationId],
  );

  useEffect(() => {
    if (stationId === "" && availableStations.length > 0) {
      const preferred =
        availableStations.find((station) => station.station_id === "DEL-01") ??
        availableStations[0];
      if (preferred) {
        setStationId(preferred.station_id);
        setTemperature(toNumberInput(preferred.temperature));
        setHumidity(toNumberInput(preferred.humidity));
        setPressure(toNumberInput(preferred.pressure));
      }
    }
  }, [availableStations, stationId]);

  const prefill = (id: string) => {
    setStationId(id);
    setFieldErrors({});
    const row = availableStations.find((station) => station.station_id === id);
    if (row) {
      setTemperature(toNumberInput(row.temperature));
      setHumidity(toNumberInput(row.humidity));
      setPressure(toNumberInput(row.pressure));
    }
  };

  /** Presets only fill the form; inference always runs through the backend. */
  const applyPreset = (kind: "normal" | "spike") => {
    const row = availableStations.find((station) => station.station_id === stationId) ?? selected;
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

  return (
    <>
      {stationsQuery.isPending && <LoadingState message="Loading stations for the probe…" />}
      {stationsQuery.isError && (
        <ErrorState
          message={errorMessage(stationsQuery.error)}
          onRetry={() => stationsQuery.refetch()}
        />
      )}
      {!stationsQuery.isPending && !stationsQuery.isError && availableStations.length === 0 && (
        <EmptyState
          title="No stations available"
          message="The API returned no stations with data to probe."
        />
      )}
      {!stationsQuery.isPending && !stationsQuery.isError && availableStations.length > 0 && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <section className="panel p-4" aria-label="Probe input">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="section-kicker">Observation under test</p>
                <h2 className="mt-1 text-lg font-extrabold">Probe Input</h2>
              </div>
              {selected && (
                <StatusBadge status={normalizeStatus(selected.status, selected.data_available)} />
              )}
            </div>

            <div className="mt-3 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="probe-station">Station</Label>
                <Select value={stationId} onValueChange={prefill}>
                  <SelectTrigger
                    id="probe-station"
                    aria-label="Station"
                    className={cn(fieldErrors.station && "border-anomaly")}
                  >
                    <SelectValue placeholder="Select station" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableStations.map((station) => (
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
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label htmlFor="probe-temp">Temperature (°C)</Label>
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
                  <Label htmlFor="probe-humidity">Humidity (% RH)</Label>
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
                <div className="space-y-1.5">
                  <Label htmlFor="probe-pressure">Pressure (hPa)</Label>
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
              </div>

              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={submit} disabled={probe.isPending}>
                  <FlaskConical />
                  {probe.isPending ? "Analyzing…" : "Analyze observation"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => applyPreset("normal")}
                  disabled={probe.isPending}
                  title="Fill the form with the station's latest reading"
                >
                  Normal observation
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => applyPreset("spike")}
                  disabled={probe.isPending}
                  title="Fill the form with an elevated temperature to test"
                >
                  Spike-like observation
                </Button>
              </div>
              <p className="text-[10px] text-muted-foreground">
                Probe against historical station context — inputs are prefilled from the selected
                station&apos;s latest replayed reading and remain editable.
              </p>
            </div>
          </section>

          <section className="panel p-4" aria-label="Probe result" aria-live="polite">
            <p className="section-kicker">Result</p>
            <h2 className="mt-1 text-lg font-extrabold">Analysis</h2>
            {probe.isPending && (
              <p className="mt-2 text-[11px] text-muted-foreground" role="status">
                Analyzing… scoring the observation through the SkyGuard pipeline.
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

function ProbeResultView({ result }: { result: ProbeResponse }) {
  const trusted = !result.result.is_anomalous;
  const spatial = result.evidence.spatial;
  const spatialAvailable = spatial["available"] === true;
  const dq = result.evidence.data_quality;
  const multi = result.evidence.multivariate;

  return (
    <div className="mt-2 space-y-2.5">
      <div
        className={cn(
          "flex items-start gap-2 rounded-xl border p-2.5",
          trusted
            ? "border-success/30 bg-success-soft text-success"
            : "border-anomaly/30 bg-anomaly-soft text-anomaly",
        )}
      >
        <div className="min-w-0 flex-1">
          <p className="section-kicker">Trust assessment</p>
          <p
            className={cn(
              "mt-0.5 text-sm font-extrabold",
              trusted ? "text-success-deep" : "text-anomaly-deep",
            )}
          >
            {trusted ? "Not flagged — consistent with available context" : "Anomaly — needs review"}
          </p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Scored {result.result.anomaly_score?.toFixed(3) ?? "—"} against threshold{" "}
            {result.result.threshold?.toFixed(3) ?? "—"} ({result.result.method}) ·{" "}
            {availabilityLabel(result.result.availability)}
            {result.result.confidence !== null &&
              result.result.confidence !== undefined &&
              ` · Evidence coverage ${(result.result.confidence * 100).toFixed(0)}%`}
          </p>
        </div>
        <StatusBadge status={trusted ? "healthy" : "anomaly"} />
      </div>

      <div className="grid grid-cols-3 gap-1.5">
        <DetailStat
          label="Submitted temperature"
          value={`${result.probe.temperature.toFixed(1)}°C`}
          emphasis={!trusted}
          tone={!trusted ? "bg-anomaly-soft" : undefined}
        />
        <DetailStat
          label="Submitted humidity"
          value={`${result.probe.humidity.toFixed(1)}% RH`}
          tone="bg-surface-blue-tint"
        />
        <DetailStat
          label="Submitted pressure"
          value={`${result.probe.pressure.toFixed(1)} hPa`}
          tone="bg-surface-blue-tint"
        />
      </div>

      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
          Why this assessment?
        </p>
        <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
          {cleanText(result.explanation.text) ?? "Explanation not available."}
        </p>
        <div className="mt-2 divide-y divide-border">
          <FactRow label="Statistical (z max)" value={componentText(result.evidence.statistical)} />
          <FactRow
            label="Isolation Forest"
            value={componentText(result.evidence.isolation_forest)}
          />
          <FactRow label="LSTM reconstruction" value={componentText(result.evidence.lstm)} />
          <FactRow
            label="Multivariate deviation"
            value={
              typeof multi["multivariate_max_abs_robust_deviation_2h"] === "number"
                ? (multi["multivariate_max_abs_robust_deviation_2h"] as number).toFixed(2)
                : "Not available"
            }
          />
          <FactRow
            label="Data quality"
            value={`${String(dq["status"] ?? "Unknown")} · ML ${
              dq["ml_eligible"] ? "eligible" : "ineligible"
            }`}
          />
        </div>
      </div>

      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">Likely cause</p>
        <p className="mt-1.5 text-[11px] leading-snug">
          <strong className="text-foreground">
            {cleanText(result.root_cause.class) ?? "No fault pattern diagnosed"}
          </strong>
          {result.root_cause.confidence !== null && result.root_cause.confidence !== undefined && (
            <span className="text-muted-foreground">
              {" "}
              · {formatConfidence(result.root_cause.confidence)} confidence
            </span>
          )}
          {cleanText(result.root_cause.runner_up) && (
            <span className="text-muted-foreground">
              {" "}
              · runner-up {result.root_cause.runner_up}
            </span>
          )}
        </p>
        <p className="mt-1 text-[10px] text-muted-foreground">
          Model prediction to aid review — not a confirmed physical diagnosis.
        </p>
      </div>

      {result.explanation.features.length > 0 && (
        <ExplanationBlock explanation={result.explanation} loading={false} />
      )}

      <div className="rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
          Spatial context → interpretation
        </p>
        {result.spatial_decision ? (
          <div className="mt-1 divide-y divide-border">
            <FactRow
              label="Base decision"
              value={String(result.spatial_decision.base_decision ?? "—")}
            />
            <FactRow
              label="Interpretation"
              value={String(result.spatial_decision.contextual_decision ?? "—")}
            />
            {result.spatial_decision.description ? (
              <p className="py-1 text-[11px] leading-snug text-muted-foreground">
                {result.spatial_decision.description}
              </p>
            ) : null}
          </div>
        ) : null}
        {spatialAvailable ? (
          <div className="mt-1 divide-y divide-border">
            <FactRow label="Neighbors" value={String(spatial["neighbor_count"] ?? "—")} />
            <FactRow label="Context" value={String(spatial["context"] ?? "—")} />
            <FactRow
              label="Reference median"
              value={
                typeof spatial["reference_median"] === "number"
                  ? `${(spatial["reference_median"] as number).toFixed(1)}°C`
                  : "—"
              }
            />
            <FactRow
              label="Probe difference"
              value={
                typeof spatial["probe_difference"] === "number"
                  ? `${(spatial["probe_difference"] as number) >= 0 ? "+" : ""}${(spatial["probe_difference"] as number).toFixed(1)}°C`
                  : "—"
              }
            />
          </div>
        ) : (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Spatial context unavailable for this station — no neighbor values invented.
          </p>
        )}
      </div>

      <p className="text-[10px] leading-snug text-muted-foreground">
        {result.context.context_note} Data mode: {result.data_mode} (interactive historical replay,
        not a live sensor feed).{" "}
        <Link to="/evaluation" className="font-bold text-info hover:underline">
          View evaluation evidence →
        </Link>
      </p>
    </div>
  );
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
