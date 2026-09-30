import { useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { DetailStat } from "@/components/common";
import { ReplayTemperatureChart, type ReplayTemperaturePoint } from "@/components/charts";
import { ReplayControls } from "@/components/replay/ReplayControls";
import { ReplayTimeline } from "@/components/replay/ReplayTimeline";
import { ObservationBadge, observationState } from "@/components/replay/observation";
import { Button } from "@/components/ui/button";
import type { LiveReplay } from "@/hooks/useLiveReplay";
import type { StationSummary } from "@/lib/api";
import {
  cleanText,
  formatConfidence,
  formatDateTime,
  formatDisplayTerm,
  formatHumidity,
  formatPressure,
  formatScore,
  formatTemp,
  formatTime,
} from "@/lib/format";
import type { LiveReading } from "@/lib/live";
import {
  alertReason,
  alertSeverity,
  readingConfidence,
  readingContributingFactors,
  readingDetectorLabel,
  readingReason,
  readingSeverity,
  readingSpatial,
  readingThreshold,
  severityLabel,
} from "@/lib/liveView";
import { cn } from "@/lib/utils";

export interface ReplayStation {
  id: string;
  city: string;
  statistical: boolean;
  api?: StationSummary | undefined;
}

/**
 * Historical replay area: "historical observation → SkyGuard decision".
 *
 * Hierarchy: which station is replayed, what the replay state is, one compact
 * summary strip, the latest observation, the anomaly evidence, then the
 * chronological timeline and a temperature chart. Everything shown comes from
 * the existing replay session state / backend station response — nothing is
 * inferred, and historical observations are never labelled "Offline".
 */
export function ReplayStage({ live, stations }: { live: LiveReplay; stations: ReplayStation[] }) {
  const navigate = useNavigate();
  const [stationId, setStationId] = useState("");
  const [split, setSplit] = useState("OOD");
  const [speed, setSpeed] = useState(10);

  // Selection follows the backend coverage list, never a hardcoded station.
  const selected = useMemo(() => {
    const explicit = stations.find((station) => station.id === stationId);
    if (explicit) return explicit;
    return stations.find((station) => !station.statistical) ?? stations[0] ?? null;
  }, [stations, stationId]);

  // While a replay exists the header describes what is (or was) replayed;
  // the summary/timeline/chart always belong to that same run.
  const contextStation = useMemo(() => {
    if (live.replay.status !== "idle" && live.replay.stationId) {
      return (
        stations.find((station) => station.id === live.replay.stationId) ?? {
          id: live.replay.stationId,
          city: "",
          statistical: false,
          api: undefined,
        }
      );
    }
    return selected;
  }, [live.replay.status, live.replay.stationId, stations, selected]);

  const readings = useMemo(() => {
    const replayedId = live.replay.stationId;
    if (!replayedId) return live.recentReadings;
    return live.recentReadings.filter((row) => row.station_id === replayedId);
  }, [live.recentReadings, live.replay.stationId]);

  const latest = readings.at(-1) ?? null;
  const effectiveSplit = selected?.statistical ? "HISTORICAL" : split;
  const state = replayStateView(live);
  const detectorState = contextStation?.api?.capability?.detector ?? null;
  const cadence = detectorState?.cadence ?? null;
  // Top-level data_mode only: the capability block carries internal enums
  // (REPLAY / HISTORICAL) that must never be shown to operators.
  const contextBits = [
    formatDisplayTerm(contextStation?.api?.data_mode, "Historical replay"),
    cadence != null
      ? `${cadence % 1 === 0 ? cadence.toFixed(0) : cadence.toFixed(1)} min cadence`
      : null,
    cleanText(detectorState?.detector_type),
  ].filter((bit): bit is string => bit !== null && bit !== "");

  return (
    <section className="panel shrink-0 p-4" aria-label="Historical replay">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="section-kicker">Historical replay · observation → decision</p>
          <h2 className="mt-1 min-w-0 truncate text-lg font-extrabold leading-tight">
            {contextStation
              ? contextStation.city
                ? `${contextStation.city} · ${contextStation.id}`
                : contextStation.id
              : "Select a station"}
          </h2>
          <p className="mt-0.5 text-[10px] text-muted-foreground">
            {contextBits.length > 0
              ? contextBits.join(" · ")
              : "Station context unavailable until the backend reports it."}
          </p>
        </div>
        <span className={cn("status-pill", state.tone)} role="status">
          <span className="status-dot" />
          {state.label}
          {state.detail && <span className="font-semibold opacity-80">· {state.detail}</span>}
        </span>
      </div>

      <ReplayControls
        live={live}
        stations={stations}
        stationId={selected?.id ?? ""}
        onStationChange={setStationId}
        split={split}
        onSplitChange={setSplit}
        speed={speed}
        onSpeedChange={setSpeed}
      />

      <ReplaySummaryStrip live={live} />

      <div className="mt-2.5 grid min-w-0 grid-cols-1 gap-2.5 xl:grid-cols-2">
        <LatestObservationCard reading={latest} />
        <AnomalyEvidenceCard
          live={live}
          onInvestigate={(alertId) =>
            navigate({
              to: "/investigations/replay/$anomalyId",
              params: { anomalyId: alertId },
            })
          }
        />
      </div>

      <div className="mt-2.5 grid min-w-0 grid-cols-1 gap-3 border-t border-border pt-2.5 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <ReplayTimeline readings={readings} />
        <TemperatureSection readings={readings} stationId={live.replay.stationId} />
      </div>
    </section>
  );
}

/** Actual replay state for the header pill (READY/RUNNING/PAUSED/COMPLETE…). */
function replayStateView(live: LiveReplay): { label: string; detail: string | null; tone: string } {
  const active =
    live.replay.status === "running" ||
    live.replay.status === "paused" ||
    live.replay.status === "preparing";
  if (active && live.connection === "connecting") {
    return { label: "CONNECTING", detail: null, tone: "bg-info-soft text-info" };
  }
  if (active && live.connection === "disconnected") {
    return { label: "DISCONNECTED", detail: null, tone: "bg-offline-soft text-offline-deep" };
  }
  switch (live.replay.status) {
    case "preparing":
      return { label: "PREPARING", detail: null, tone: "bg-info-soft text-info" };
    case "running":
      return {
        label: "RUNNING",
        detail: live.replay.speed != null ? `${live.replay.speed}×` : null,
        tone: "bg-success-soft text-success-deep",
      };
    case "paused":
      return { label: "PAUSED", detail: null, tone: "bg-warning-soft text-warning-deep" };
    case "stopped":
      return { label: "STOPPED", detail: null, tone: "bg-muted text-muted-foreground" };
    case "completed": {
      const processed = live.completeInfo?.processed ?? live.replay.processed;
      return {
        label: "COMPLETE",
        detail: `${processed} observation${processed === 1 ? "" : "s"} processed`,
        tone: "bg-success-soft text-success-deep",
      };
    }
    default:
      return { label: "READY", detail: null, tone: "bg-muted text-muted-foreground" };
  }
}

/** The ONE summary strip: Observations / Normal / Anomalies. */
function ReplaySummaryStrip({ live }: { live: LiveReplay }) {
  const cells = [
    {
      label: "Observations",
      value: live.summary.observations,
      tone: undefined as string | undefined,
    },
    { label: "Normal", value: live.summary.normal, tone: undefined as string | undefined },
    {
      label: "Anomalies",
      value: live.summary.anomalies,
      tone: live.summary.anomalies > 0 ? "text-anomaly" : undefined,
    },
  ];
  return (
    <div
      className="mt-2.5 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-border bg-muted/40 px-3 py-2"
      aria-label="Replay summary"
    >
      {cells.map((cell) => (
        <div key={cell.label} className="min-w-[72px]">
          <p className="text-[9px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
            {cell.label}
          </p>
          <p className={cn("text-lg font-extrabold leading-tight tabular-nums", cell.tone)}>
            {cell.value}
          </p>
        </div>
      ))}
      <p className="ml-auto max-w-[48ch] text-[9px] leading-snug text-muted-foreground">
        {live.replay.status === "idle"
          ? "Start Historical Replay to process observations."
          : "Streamed historical observations counted once each; alerts are counted per detection."}
      </p>
    </div>
  );
}

/** "What did SkyGuard just see?" — the most recent streamed observation. */
function LatestObservationCard({ reading }: { reading: LiveReading | null }) {
  return (
    <div
      className="min-w-0 rounded-xl border border-border bg-muted/40 p-3"
      aria-label="Latest observation"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="section-kicker">Latest observation</p>
        {reading && <ObservationBadge state={observationState(reading)} />}
      </div>
      {!reading ? (
        <p className="mt-2 text-[10px] text-muted-foreground" role="status">
          Start Historical Replay to process observations.
        </p>
      ) : (
        <>
          <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <h3 className="text-sm font-extrabold">
              {reading.station_id}
              {reading.city ? ` · ${reading.city}` : ""}
            </h3>
            <span className="text-[10px] text-muted-foreground">
              <time title={reading.timestamp}>{formatDateTime(reading.timestamp)}</time>
            </span>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            <DetailStat
              label="Temperature"
              value={formatTemp(reading.observations.temperature_c)}
              emphasis={reading.anomaly.detected}
            />
            <DetailStat
              label="Relative humidity"
              value={formatHumidity(reading.observations.relative_humidity_pct)}
            />
            <DetailStat
              label="Pressure"
              value={formatPressure(reading.observations.pressure_hpa)}
            />
          </div>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[9px] text-muted-foreground">
            <span>
              Detector{" "}
              <strong className="font-extrabold text-foreground">
                {readingDetectorLabel(reading)}
              </strong>
            </span>
            <span>
              Score{" "}
              <strong className="font-extrabold tabular-nums text-foreground">
                {formatScore(reading.anomaly.score)}
                {readingThreshold(reading) !== null
                  ? ` / ${formatScore(readingThreshold(reading))}`
                  : ""}
              </strong>
            </span>
            {readingSeverity(reading) !== null && (
              <span>
                Severity{" "}
                <strong className="font-extrabold text-foreground">
                  {severityLabel(readingSeverity(reading))}
                </strong>
              </span>
            )}
          </div>
          {reading.data_quality.ml_eligible !== true && (
            <p className="mt-1.5 text-[10px] leading-snug text-warning-deep" role="status">
              Data quality {cleanText(reading.data_quality.status) ?? "failed"}
              {cleanText(reading.data_quality.reason)
                ? ` — ${cleanText(reading.data_quality.reason)}`
                : ""}
              . This observation could not be analysed by the detector.
            </p>
          )}
        </>
      )}
    </div>
  );
}

/** Why SkyGuard flagged the most recent anomaly — only real backend fields. */
function AnomalyEvidenceCard({
  live,
  onInvestigate,
}: {
  live: LiveReplay;
  onInvestigate: (alertId: string) => void;
}) {
  const alert = live.liveAlerts[0] ?? null;
  const reading = alert ? (live.anomalyMap[alert.alert_id] ?? null) : null;
  const severity = alert ? severityLabel(alertSeverity(alert)) : null;
  const confidence = alert?.confidence ?? (reading ? readingConfidence(reading) : null);
  const reason = (alert ? alertReason(alert) : null) ?? (reading ? readingReason(reading) : null);
  const factors = reading
    ? readingContributingFactors(reading)
    : (alert?.contributing_factors ?? []);
  const detector = alert?.detector ?? (reading ? readingDetectorLabel(reading) : null);
  const threshold = alert?.threshold ?? (reading ? readingThreshold(reading) : null);
  const spatial = reading ? readingSpatial(reading) : null;

  return (
    <div
      className={cn(
        "min-w-0 rounded-xl border p-3",
        alert ? "border-anomaly/40 bg-anomaly-soft/40" : "border-border bg-muted/40",
      )}
      aria-label="Anomaly evidence"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="section-kicker">Decision evidence</p>
        {alert && (
          <span className="text-[9px] font-extrabold uppercase tracking-[0.06em] text-anomaly-deep">
            Anomaly detected
          </span>
        )}
      </div>
      {!alert ? (
        <p className="mt-2 text-[10px] text-muted-foreground" role="status">
          {live.replay.status === "idle"
            ? "Start Historical Replay to process observations."
            : "No anomalies detected in the observations processed so far."}
        </p>
      ) : (
        <>
          <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <h3 className="text-sm font-extrabold">
              {alert.station_id}
              {alert.city ? ` · ${alert.city}` : ""}
            </h3>
            <span className="text-[10px] text-muted-foreground">
              <time title={alert.timestamp}>{formatDateTime(alert.timestamp)}</time>
            </span>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            <DetailStat
              label="Severity"
              value={severity ?? "Not available"}
              tone="bg-anomaly-soft"
              valueTone="text-anomaly"
            />
            <DetailStat
              label="Confidence"
              value={
                confidence !== null && confidence !== undefined
                  ? formatConfidence(confidence)
                  : "Not available"
              }
            />
            <DetailStat
              label="Score"
              value={`${formatScore(alert.score)}${threshold !== null ? ` / ${formatScore(threshold)}` : ""}`}
            />
          </div>
          <p className="mt-2 text-[10px] leading-snug">
            <span className="font-extrabold">Primary reason: </span>
            <span className="text-muted-foreground">
              {cleanText(reason) ?? "Explanation unavailable for this observation."}
            </span>
          </p>
          {factors.length > 0 ? (
            <div className="mt-1.5">
              <p className="text-[9px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                Evidence
              </p>
              <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-[10px] text-muted-foreground">
                {factors.map((factor) => (
                  <li key={factor}>{factor}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="mt-1.5 text-[9px] text-muted-foreground">
              {reading
                ? "No contributing factors were reported for this observation."
                : "Contributing factors unavailable for this alert."}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
            <p className="min-w-0 text-[9px] text-muted-foreground">
              Detector{" "}
              <strong className="font-extrabold text-foreground">
                {cleanText(detector) ?? "Not available"}
              </strong>
              {spatial?.available ? ` · spatial context ${spatial.level}` : ""}
            </p>
            <Button size="sm" className="ml-auto" onClick={() => onInvestigate(alert.alert_id)}>
              Investigate →
            </Button>
          </div>
          {spatial?.available && (
            <p className="mt-1 text-[9px] leading-snug text-muted-foreground">{spatial.label}</p>
          )}
        </>
      )}
    </div>
  );
}

/** Temperature across the replay; anomaly observations are distinct points. */
function TemperatureSection({
  readings,
  stationId,
}: {
  readings: LiveReading[];
  stationId: string | null;
}) {
  const points: ReplayTemperaturePoint[] = readings.map((reading) => ({
    time: formatTime(reading.timestamp),
    temperature: reading.observations.temperature_c,
    anomaly: reading.anomaly.detected,
  }));
  const usable = points.filter((point) => point.temperature !== null);
  const anomalyCount = points.filter((point) => point.anomaly).length;
  return (
    <div className="min-w-0" aria-label="Temperature during replay">
      <div className="flex items-baseline justify-between gap-2">
        <p className="section-kicker">Temperature during replay</p>
        <span className="flex items-center gap-1.5 text-[9px] text-muted-foreground">
          <span className="inline-block size-2 rounded-full bg-anomaly" aria-hidden="true" />
          anomaly point{anomalyCount === 1 ? "" : "s"}
        </span>
      </div>
      {usable.length < 2 ? (
        <p
          className="mt-1.5 flex h-[150px] items-center justify-center px-4 text-center text-[10px] text-muted-foreground"
          role="status"
        >
          {readings.length === 0
            ? "Start Historical Replay to process observations."
            : "Waiting for enough observations to plot a trend…"}
        </p>
      ) : (
        <ReplayTemperatureChart
          data={points}
          height={150}
          ariaLabel={`Temperature during replay for ${stationId ?? "the replayed station"}`}
        />
      )}
    </div>
  );
}
