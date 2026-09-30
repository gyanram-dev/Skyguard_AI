/**
 * Judge-facing showcase panels, all driven by backend responses.
 *
 * The historical-analysis forensics panel (dataset, timeline, detector
 * events, event evidence, spatial context) lives in
 * ``components/forensics.tsx``.
 * - InvestigationPanel: the target station against its audited nearby
 *   stations, using the backend's existing spatial decision
 *   (LOCAL_SENSOR_ANOMALY / POSSIBLE_REGIONAL_EVENT / INSUFFICIENT).
 * - FaultDemoPanel: the controlled fault-injection demo. Real observations
 *   plus benchmark injections, always labelled CONTROLLED DEMO.
 *
 * Nothing here computes a verdict, invents a neighbour value, or renders an
 * unavailable measurement as healthy.
 */

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { ErrorState, FactRow } from "@/components/common";
import { severityColor } from "@/components/charts";
import {
  type FaultDemoResponse,
  type FaultDemoRow,
  type InvestigationResponse,
  type NearbyStation,
  type SpatialVariableEvidence,
} from "@/lib/api";
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
import { useFaultSequence, useStationInvestigation } from "@/hooks/useSkyguard";

function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  return `${(value * 100).toFixed(0)}%`;
}

function signed(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}`;
}

/** Human label for the backend's contextual classification (verbatim enum). */
function interpretationLabel(decision: string): string {
  switch (decision) {
    case "LOCAL_SENSOR_ANOMALY":
      return "LOCAL SENSOR ANOMALY";
    case "POSSIBLE_REGIONAL_EVENT":
      return "POSSIBLE REGIONAL EVENT";
    case "ANOMALY_WITHOUT_SPATIAL_CONFIRMATION":
      return "ANOMALY WITHOUT SPATIAL CONFIRMATION";
    case "INSUFFICIENT_EVIDENCE":
      return "INSUFFICIENT EVIDENCE";
    case "NORMAL":
      return "NO ANOMALY FLAGGED";
    default:
      return cleanText(decision) ?? "Not available";
  }
}

function interpretationTone(decision: string): string {
  if (decision === "LOCAL_SENSOR_ANOMALY") return "text-anomaly-deep";
  if (decision === "POSSIBLE_REGIONAL_EVENT") return "text-warning-deep";
  if (decision === "ANOMALY_WITHOUT_SPATIAL_CONFIRMATION") return "text-warning-deep";
  return "text-muted-foreground";
}

// ---------------------------------------------------------------------------
// 2. Investigation: target vs audited nearby stations
// ---------------------------------------------------------------------------

function neighborValueLabel(
  neighbor: NearbyStation,
  variable: "temperature" | "humidity" | "pressure",
) {
  if (variable === "humidity") return formatHumidity(neighbor.humidity);
  if (variable === "pressure")
    return neighbor.pressure === null
      ? "Not comparable"
      : `${formatPressure(neighbor.pressure)}${neighbor.pressure_basis ? ` (${neighbor.pressure_basis})` : ""}`;
  return formatTemp(neighbor.temperature);
}

function VariableEvidenceRow({
  label,
  evidence,
  unit,
}: {
  label: string;
  evidence: SpatialVariableEvidence | undefined;
  unit: string;
}) {
  if (!evidence) return null;
  const statusLabel =
    evidence.status === "SPATIAL_CONTRADICTED"
      ? "Contradicted by neighbours"
      : evidence.status === "SPATIAL_SUPPORTED"
        ? "Supported by neighbours"
        : evidence.status === "SPATIAL_INSUFFICIENT"
          ? "Insufficient neighbour evidence"
          : "Unavailable";
  return (
    <FactRow
      label={label}
      value={
        <span>
          {statusLabel}
          {evidence.reference_median !== null && (
            <>
              {" "}
              · median {evidence.reference_median.toFixed(1)} {unit}
            </>
          )}
          {evidence.deviation !== null && (
            <>
              {" "}
              · deviation {signed(evidence.deviation)} {unit}
            </>
          )}
          {evidence.robust_score !== null && (
            <> · robust score {evidence.robust_score.toFixed(2)}</>
          )}
          {` · ${evidence.usable_neighbor_count}/${evidence.neighbor_count} neighbours`}
        </span>
      }
    />
  );
}

export function InvestigationPanel({
  stationId,
  anchor,
  onResetAnchor,
}: {
  stationId: string;
  /** Station-local timestamp selected on the timeline (or null). */
  anchor: string | null;
  onResetAnchor: () => void;
}) {
  const investigationQuery = useStationInvestigation(stationId, anchor);

  if (investigationQuery.isPending) {
    return (
      <section className="panel p-4" aria-label="Station investigation">
        <p className="section-kicker">Investigation</p>
        <p className="mt-2 text-[11px] text-muted-foreground" role="status">
          Comparing the target station with its audited neighbours…
        </p>
      </section>
    );
  }
  if (investigationQuery.isError) {
    return (
      <section className="panel p-4" aria-label="Station investigation">
        <p className="section-kicker">Investigation</p>
        <div className="mt-2">
          <ErrorState
            message={errorMessage(investigationQuery.error)}
            onRetry={() => investigationQuery.refetch()}
          />
        </div>
      </section>
    );
  }
  const data: InvestigationResponse | undefined = investigationQuery.data;
  if (!data) return null;
  const target = data.target_observation;
  const comparison = data.comparison;
  const decision = data.interpretation;

  return (
    <section className="panel p-4" aria-label="Station investigation">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="section-kicker">Investigation</p>
          <h3 className="mt-1 text-base font-extrabold">
            TARGET · {data.station_id} · {data.city}
          </h3>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Anchored at {formatDateTime(data.anchor.timestamp)} ({data.anchor.time_basis} basis) ·{" "}
            {data.anchor.basis.replace(/_/g, " ").toLowerCase()}
            {data.anchor.requested ? " · selected from the timeline" : ""}
          </p>
        </div>
        <div className={`text-right ${interpretationTone(decision.contextual_decision)}`}>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.08em]">
            Real weather or sensor failure?
          </p>
          <p className="text-[15px] font-extrabold">
            {interpretationLabel(decision.contextual_decision)}
          </p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-3">
        <div className="rounded-xl border border-border p-3">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.06em] text-muted-foreground">
            Target observation
          </p>
          <div className="mt-1 divide-y divide-border">
            <FactRow label="Temperature" value={formatTemp(target.temperature_c)} />
            <FactRow label="Humidity" value={formatHumidity(target.relative_humidity_pct)} />
            <FactRow
              label="Pressure"
              value={
                target.pressure_hpa === null
                  ? "Not available"
                  : `${formatPressure(target.pressure_hpa)}${
                      data.pressure_basis ? ` (${data.pressure_basis})` : ""
                    }`
              }
            />
            <FactRow
              label="Neighbour median (T)"
              value={
                comparison.neighbor_median_temperature === null
                  ? "No neighbour values"
                  : formatTemp(comparison.neighbor_median_temperature)
              }
            />
            <FactRow
              label="Deviation (T)"
              value={
                comparison.temperature_deviation === null
                  ? "Not computable"
                  : `${signed(comparison.temperature_deviation)} °C`
              }
            />
            <FactRow
              label="Spatial robust score"
              value={formatScore(comparison.temperature.robust_score)}
            />
            <FactRow
              label="Neighbours used"
              value={`${data.usable_neighbors} of ${data.expected_neighbors} audited`}
            />
          </div>
        </div>

        <div className="rounded-xl border border-border p-3 xl:col-span-2">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.06em] text-muted-foreground">
            Nearby stations (real, causally aligned observations)
          </p>
          {data.nearby.length === 0 ? (
            <p className="mt-1 text-[11px] text-warning-deep">
              Spatial context unavailable — no neighbour values are invented.
            </p>
          ) : (
            <div className="mt-1 overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-left uppercase tracking-[0.06em] text-muted-foreground">
                    <th className="py-1 pr-2 font-extrabold">Station</th>
                    <th className="py-1 pr-2 font-extrabold">Distance</th>
                    <th className="py-1 pr-2 font-extrabold">Temperature</th>
                    <th className="py-1 pr-2 font-extrabold">RH</th>
                    <th className="py-1 pr-2 font-extrabold">Pressure</th>
                    <th className="py-1 pr-2 font-extrabold">Observed at</th>
                    <th className="py-1 font-extrabold">Freshness</th>
                  </tr>
                </thead>
                <tbody>
                  {data.nearby.map((neighbor) => (
                    <tr key={neighbor.station_id} className="border-t border-border">
                      <td className="py-1 pr-2 font-semibold">
                        {neighbor.station_id} · {neighbor.city}
                      </td>
                      <td className="py-1 pr-2 tabular-nums text-muted-foreground">
                        {neighbor.distance_km === null
                          ? "—"
                          : `${neighbor.distance_km.toFixed(0)} km`}
                      </td>
                      <td className="py-1 pr-2 tabular-nums">
                        {neighborValueLabel(neighbor, "temperature")}
                      </td>
                      <td className="py-1 pr-2 tabular-nums">
                        {neighborValueLabel(neighbor, "humidity")}
                      </td>
                      <td className="py-1 pr-2 tabular-nums">
                        {neighborValueLabel(neighbor, "pressure")}
                      </td>
                      <td className="py-1 pr-2 text-muted-foreground">
                        {neighbor.aligned_timestamp
                          ? formatDateTime(neighbor.aligned_timestamp)
                          : "No aligned record"}
                      </td>
                      <td className="py-1 text-muted-foreground">
                        {neighbor.age_minutes === null
                          ? (cleanText(neighbor.data_freshness) ?? "—")
                          : `${neighbor.age_minutes.toFixed(0)} min before target`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="rounded-xl border border-border p-3" aria-label="Spatial evidence">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.06em] text-muted-foreground">
            Spatial evidence
          </p>
          <div className="mt-1 divide-y divide-border">
            <VariableEvidenceRow label="Temperature" evidence={comparison.temperature} unit="°C" />
            <VariableEvidenceRow label="Humidity" evidence={comparison.humidity} unit="% RH" />
            <VariableEvidenceRow label="Pressure" evidence={comparison.pressure} unit="hPa" />
          </div>
          <p className="mt-1.5 text-[10px] text-muted-foreground">{decision.description}</p>
        </div>

        <div className="rounded-xl border border-border p-3" aria-label="Detection evidence">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.06em] text-muted-foreground">
            Detection evidence at the anchor
          </p>
          <div className="mt-1 divide-y divide-border">
            <FactRow
              label="Base decision"
              value={decision.base_decision.replace(/_/g, " ").toLowerCase()}
            />
            <FactRow label="Spatial influence" value={decision.spatial_influence} />
            <FactRow
              label="Temporal (max |z|, causal window)"
              value={formatScore(
                (data.detector_verdict["z_max_abs"] as number | null | undefined) ?? null,
              )}
            />
            <FactRow
              label="Temporal (T change °C/h)"
              value={signed(
                (data.detector_verdict["temperature_rate_per_hour"] as number | null) ?? null,
                2,
              )}
            />
            <FactRow
              label="Multivariate deviation"
              value={(() => {
                const value =
                  (data.detector_verdict["multivariate_max_abs_robust_deviation_2h"] as
                    number | null | undefined) ?? null;
                if (value === null) return "Not available";
                // A zero-width comparison window yields a degenerate ratio;
                // printing it as a meaningful magnitude would misstate the
                // evidence.
                if (value > 1000) {
                  return `${formatScore(value)} — not interpretable (zero-width comparison window)`;
                }
                return formatScore(value);
              })()}
            />
            <FactRow
              label="Data quality"
              value={
                (data.detector_verdict["data_quality_status"] as string | undefined) ??
                "Not available"
              }
            />
            <FactRow
              label="Statistical flag"
              value={data.detector_verdict["statistical_flag"] === true ? "Yes" : "No"}
            />
            <FactRow
              label="Declared detector"
              value={
                data.detector_verdict["available"] === false
                  ? "No detector verdict at this anchor"
                  : "Frozen detector (this station)"
              }
            />
          </div>
          <p className="mt-1.5 text-[10px] text-muted-foreground">
            Automated explanation and detection evidence — the spatial context is the existing
            Phase-22 decision layer; it never creates an anomaly, it only re-interprets an
            already-flagged observation.
          </p>
        </div>
      </div>

      {data.notes.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-[10px] text-muted-foreground">
          {data.notes.map((note) => (
            <li key={note}>• {note}</li>
          ))}
        </ul>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={onResetAnchor} disabled={anchor === null}>
          Reset to the latest flagged observation
        </Button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// 3. Controlled fault demo
// ---------------------------------------------------------------------------

const PHASE_ORDER = ["NORMAL", "SPIKE", "FROZEN", "DRIFT", "CROSS_VARIABLE"] as const;

function PhaseSummary({ data }: { data: FaultDemoResponse }) {
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
      {PHASE_ORDER.map((phase) => {
        const entry = data.summary.by_phase[phase];
        if (!entry) return null;
        const detected = entry.detected > 0;
        return (
          <div
            key={phase}
            className={`rounded-xl border p-2 ${
              detected ? "border-anomaly/30 bg-anomaly-soft" : "border-border bg-card"
            }`}
          >
            <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">{phase}</p>
            <p className="mt-0.5 text-[11px] font-semibold">
              {phase === "NORMAL"
                ? detected
                  ? `${entry.detected} false positive(s)`
                  : "No false positives"
                : detected
                  ? "DETECTED"
                  : "Not detected"}
            </p>
            <p className="text-[10px] text-muted-foreground">
              {entry.detected}/{entry.rows} rows flagged
            </p>
            {entry.first_detection && (
              <p className="mt-0.5 text-[10px] text-muted-foreground">
                {entry.first_detection.root_cause ?? "—"} ·{" "}
                {formatConfidence(entry.first_detection.confidence)} ·{" "}
                {cleanText(entry.first_detection.severity) ?? "—"}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function FaultDemoRowLine({ row }: { row: FaultDemoRow }) {
  const detection = row.detection;
  return (
    <div
      className={`rounded-lg border px-2 py-1 ${
        detection.anomaly ? "border-anomaly/30 bg-anomaly-soft" : "border-border bg-card"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-1 text-[10px]">
        <span className="flex items-center gap-1.5">
          <i
            className="size-2 rounded-full"
            style={{
              backgroundColor: detection.anomaly
                ? severityColor(detection.severity)
                : "var(--muted-foreground)",
            }}
          />
          <span className="font-extrabold">{row.phase}</span>
          <span className="text-muted-foreground">{formatDateTime(row.timestamp)}</span>
        </span>
        <span className="tabular-nums">
          {formatTemp(row.temperature_c)} · {formatHumidity(row.relative_humidity_pct)} ·{" "}
          {formatPressure(row.pressure_hpa)}
        </span>
        <span
          className={`font-bold ${detection.anomaly ? "text-anomaly-deep" : "text-success-deep"}`}
        >
          {detection.anomaly
            ? `DETECTED · ${cleanText(detection.root_cause) ?? "anomaly"}`
            : "normal"}
          {detection.anomaly && detection.confidence !== null
            ? ` · ${formatConfidence(detection.confidence)}`
            : ""}
          {detection.anomaly && detection.severity ? ` · ${detection.severity}` : ""}
        </span>
      </div>
      {detection.anomaly && (
        <p className="mt-0.5 text-[10px] text-muted-foreground">
          trigger: {detection.trigger ?? "—"} · score {formatScore(detection.score)} / threshold{" "}
          {formatScore(detection.threshold)} · {detection.reason}
        </p>
      )}
    </div>
  );
}

export function FaultDemoPanel({ stationId }: { stationId: string }) {
  const demo = useFaultSequence();
  const [visible, setVisible] = useState(0);
  const [playing, setPlaying] = useState(false);
  const rows = demo.data?.rows ?? [];

  useEffect(() => {
    if (!playing) return;
    const timer = setTimeout(() => {
      setVisible((current) => {
        if (current >= rows.length) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 60);
    return () => clearTimeout(timer);
  }, [playing, visible, rows.length]);

  const run = () => {
    setVisible(0);
    demo.mutate(undefined, {
      onSuccess: () => {
        setPlaying(true);
      },
    });
  };

  return (
    <section className="panel p-4" aria-label="Controlled fault demo">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="section-kicker">Controlled fault demo</p>
          <h3 className="mt-1 text-sm font-extrabold">
            Watch SkyGuard catch spike, frozen, drift and cross-variable faults
          </h3>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Real Delhi observations (DEL-01) plus the repository's existing benchmark injections.
            Injected values exist only in this stream — the stored record is never modified.
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={run} disabled={demo.isPending}>
            {demo.isPending ? "Scoring…" : demo.data ? "Run again" : "Run Fault Detection Demo"}
          </Button>
          {demo.data && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPlaying((current) => !current)}
              disabled={visible >= rows.length}
            >
              {playing ? "Pause" : "Play"}
            </Button>
          )}
        </div>
      </div>

      {demo.isPending && (
        <p className="mt-2 text-[11px] text-muted-foreground" role="status">
          Scoring real observations through the frozen ensemble — the first run loads the models and
          can take up to a minute.
        </p>
      )}
      {demo.isError && (
        <div className="mt-2">
          <ErrorState message={errorMessage(demo.error)} onRetry={run} />
        </div>
      )}

      {demo.data && (
        <>
          <div className="mt-2 rounded-xl border border-warning/30 bg-warning-soft p-2 text-[11px] text-warning-deep">
            <p className="font-extrabold">
              {demo.data.label} — NOT LIVE IMD DATA (station {demo.data.station_id})
            </p>
            <p className="mt-0.5">{demo.data.disclaimer}</p>
            <p className="mt-0.5">
              Detector: {demo.data.detector} · anchor {demo.data.anchor} · {demo.data.context_rows}{" "}
              unmodified real observations used as causal context · stored data modified:{" "}
              {demo.data.stored_data_modified ? "yes" : "no"}
            </p>
          </div>
          <div className="mt-2">
            <PhaseSummary data={demo.data} />
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Faults detected: {demo.data.summary.faults_detected}/{demo.data.summary.faults_total} ·
            false positives on real normal observations: {demo.data.summary.normal_false_positives}
          </p>
          <div className="mt-2 max-h-[280px] space-y-1 overflow-y-auto pr-1">
            {rows.slice(0, visible).map((row) => (
              <FaultDemoRowLine key={`${row.phase}-${row.index}`} row={row} />
            ))}
          </div>
          {visible < rows.length && (
            <p className="mt-1 text-[10px] text-muted-foreground">
              Streaming… {visible}/{rows.length} observations revealed.
            </p>
          )}
        </>
      )}
    </section>
  );
}
