import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DetailStat, EmptyState, FactRow, StatusBadge } from "@/components/common";
import { HistoryChart, toChartPoints } from "@/components/charts";
import { EvidenceList, ExplanationBlock, OutcomeBanner } from "@/components/evidence";
import { normalizeStatus, type EvidenceItem } from "@/lib/api";
import {
  cleanText,
  formatConfidence,
  formatHumidity,
  formatPressure,
  formatScore,
  formatTemp,
  formatTime,
} from "@/lib/format";
import {
  alertReason,
  alertSeverity,
  readingConfidence,
  readingContributingFactors,
  readingDetectorLabel,
  readingReason,
  readingSeverity,
  readingShape,
  readingSpatial,
  readingThreshold,
  severityLabel,
} from "@/lib/liveView";
import { useReplaySession } from "@/components/replay/ReplaySessionContext";
import { useStationHistory } from "@/hooks/useSkyguard";
import type { LiveAlert, LiveReading } from "@/lib/live";

export const Route = createFileRoute("/_app/investigations/replay/$anomalyId")({
  head: ({ params }) => ({
    meta: [{ title: `Replay Anomaly ${params.anomalyId} | SkyGuard AI` }],
  }),
  component: ReplayAnomalyPage,
});

function ReplayAnomalyPage() {
  const { anomalyId } = Route.useParams();
  const navigate = useNavigate();
  const { live } = useReplaySession();

  const alert = live.liveAlerts.find((item) => item.alert_id === anomalyId) ?? null;
  const reading = live.anomalyMap[anomalyId] ?? null;

  if (!alert || !reading) {
    return (
      <section className="panel p-4" aria-label="Replay anomaly unavailable">
        <p className="section-kicker">Replay Anomaly</p>
        <h2 className="mt-1 text-lg font-extrabold">Replay anomaly unavailable</h2>
        <p className="mt-1 text-[11px] text-muted-foreground">
          This replay investigation is no longer available in the current replay session. Start a
          new replay or pick an anomaly from the current run.
        </p>
        <div className="mt-3">
          <Button size="sm" variant="outline" onClick={() => navigate({ to: "/" })}>
            <ArrowLeft />
            Back to Replay
          </Button>
        </div>
      </section>
    );
  }

  return <ReplayAnomalyDetail alert={alert} reading={reading} split={live.replay.split} />;
}

function ReplayAnomalyDetail({
  alert,
  reading,
  split,
}: {
  alert: LiveAlert;
  reading: LiveReading;
  split: string | null;
}) {
  const navigate = useNavigate();
  const historyQuery = useStationHistory(alert.station_id, "temperature", 24);

  const historySeries = useMemo(
    () => toChartPoints(historyQuery.data?.points ?? [], "temperature"),
    [historyQuery.data],
  );
  const explanationFeatures = useMemo(
    () =>
      (reading?.explanation.features ?? []).map((feature) => ({
        name: String(feature["name"] ?? "feature"),
        value: typeof feature["value"] === "number" ? (feature["value"] as number) : null,
        contribution:
          typeof feature["contribution"] === "number" ? (feature["contribution"] as number) : null,
        direction: String(feature["direction"] ?? "unknown"),
      })),
    [reading],
  );

  if (!alert || !reading) {
    return (
      <section className="panel p-4" aria-label="Replay anomaly unavailable">
        <p className="section-kicker">Replay Anomaly</p>
        <h2 className="mt-1 text-lg font-extrabold">Replay anomaly unavailable</h2>
        <p className="mt-1 text-[11px] text-muted-foreground">
          This replay investigation is no longer available in the current replay session.
        </p>
        <div className="mt-3">
          <Button size="sm" variant="outline" onClick={() => navigate({ to: "/" })}>
            <ArrowLeft />
            Back to Replay
          </Button>
        </div>
      </section>
    );
  }

  const status = normalizeStatus(alert.status, true);
  // Two real detector shapes reach the socket. Read whichever evidence the
  // backend actually sent; never render a component it did not provide.
  const shape = readingShape(reading);
  const reason = readingReason(reading) ?? alertReason(alert);
  const factors = readingContributingFactors(reading);
  const spatialView = readingSpatial(reading);
  const severity = readingSeverity(reading) ?? alertSeverity(alert);
  const confidence = alert.confidence ?? readingConfidence(reading);
  const threshold = readingThreshold(reading);
  const statistical = reading.evidence.statistical ?? null;
  const isolationForest = reading.evidence.isolation_forest ?? null;
  const lstmEvidence = reading.evidence.lstm ?? null;
  const multi = reading.evidence.multivariate ?? {};
  const spatialDetail = spatialView.available
    ? [
        spatialView.referenceMedian !== null
          ? `Reference median ${spatialView.referenceMedian.toFixed(1)}°C`
          : null,
        spatialView.neighborCount !== null
          ? `${spatialView.neighborCount} compatible neighbour(s)`
          : null,
        `context ${spatialView.level}`,
      ]
        .filter((part): part is string => part !== null)
        .join(" · ") + "."
    : "Spatial context unavailable — no neighbour values invented.";
  const evidence: EvidenceItem[] =
    shape === "station-statistical"
      ? [
          {
            title: "Station detector verdict",
            detail:
              reason ??
              "The calibrated station detector flagged this observation without a pattern label.",
            source: "statistical",
          },
          {
            title: "Detector",
            detail: `${readingDetectorLabel(reading)} · severity ${severityLabel(severity) ?? "—"}${
              confidence !== null
                ? ` · confidence ${formatConfidence(confidence)}`
                : " · confidence not available"
            }.`,
            source: "detector",
          },
          {
            title: "Contributing factors",
            detail:
              factors.length > 0
                ? factors.join(" · ")
                : "The detector reported no additional contributing factors for this observation.",
            source: "factors",
          },
          {
            title: "Spatial evidence",
            detail: spatialDetail,
            source: "spatial",
          },
          {
            title: "Data-quality evidence",
            detail: `${reading.data_quality.status}; ML ${reading.data_quality.ml_eligible ? "eligible" : "ineligible"}${
              cleanText(reading.data_quality.reason) ? ` (${reading.data_quality.reason})` : ""
            }.`,
            source: "quality",
          },
        ]
      : [
          {
            title: "Statistical evidence",
            detail: `max|z|=${statistical?.raw?.toFixed(2) ?? "—"} (calibrated ${statistical?.calibrated?.toFixed(3) ?? "—"}).`,
            source: "statistical",
          },
          {
            title: "Isolation Forest evidence",
            detail: `raw score=${isolationForest?.raw?.toFixed(3) ?? "—"} (calibrated ${isolationForest?.calibrated?.toFixed(3) ?? "—"}).`,
            source: "isolation_forest",
          },
          {
            title: "LSTM reconstruction evidence",
            detail: `target MSE=${lstmEvidence?.raw?.toFixed(3) ?? "—"} (calibrated ${lstmEvidence?.calibrated?.toFixed(3) ?? "—"}).`,
            source: "lstm",
          },
          {
            title: "Ensemble decision",
            detail: `score=${reading.anomaly.score?.toFixed(3) ?? "—"} vs threshold ${threshold?.toFixed(3) ?? "—"}; availability=${reading.anomaly.availability ?? "—"}.`,
            source: "ensemble",
          },
          {
            title: "Multivariate evidence",
            detail:
              typeof multi["multivariate_max_abs_robust_deviation_2h"] === "number"
                ? `max robust deviation=${(multi["multivariate_max_abs_robust_deviation_2h"] as number).toFixed(2)}.`
                : "Multivariate context unavailable for this event.",
            source: "multivariate",
          },
          {
            title: "Spatial evidence",
            detail: spatialDetail,
            source: "spatial",
          },
          {
            title: "Data-quality evidence",
            detail: `${reading.data_quality.status}; ML ${reading.data_quality.ml_eligible ? "eligible" : "ineligible"}.`,
            source: "quality",
          },
        ];

  const severityText = severityLabel(severity);

  return (
    <>
      <section className="flex flex-wrap items-center gap-2" aria-label="Replay navigation">
        <Button size="sm" variant="outline" onClick={() => navigate({ to: "/" })}>
          <ArrowLeft />
          Back to Replay
        </Button>
        <div>
          <p className="section-kicker">Replay Anomaly Investigation</p>
          <h2 className="text-lg font-extrabold">
            {alert.station_id} · {reading.city}
          </h2>
          <p className="text-[11px] text-muted-foreground">
            Historical Replay · {split ?? "—"} · {formatTime(reading.timestamp)}
          </p>
        </div>
        <span className="ml-auto">
          <StatusBadge status={status} />
        </span>
      </section>

      <section className="panel p-4" aria-label="Anomaly summary">
        <p className="section-kicker">Anomaly summary</p>
        <div className="mt-2 grid grid-cols-2 gap-1.5 xl:grid-cols-5">
          <DetailStat
            label="Anomaly"
            value={
              threshold !== null
                ? `${formatScore(reading.anomaly.score)} / ${formatScore(threshold)} threshold`
                : `${formatScore(reading.anomaly.score)} detected`
            }
            emphasis
            tone="bg-anomaly-soft"
          />
          {severityText !== null && (
            <DetailStat label="Severity" value={severityText} tone="bg-anomaly-soft" />
          )}
          <DetailStat
            label="Confidence"
            value={confidence !== null ? formatConfidence(confidence) : "Not available"}
            tone="bg-surface-blue-tint"
          />
          <DetailStat
            label={shape === "station-statistical" ? "Primary reason" : "Root cause"}
            value={reason ?? "Not available"}
            tone="bg-surface-blue-tint"
          />
          <DetailStat
            label="Data quality"
            value={reading.data_quality.status}
            tone="bg-surface-blue-tint"
          />
        </div>
      </section>

      <section className="panel p-4" aria-label="Observation">
        <p className="section-kicker">Observation</p>
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          <DetailStat
            label="Temperature"
            value={formatTemp(reading.observations.temperature_c)}
            emphasis
            tone="bg-anomaly-soft"
          />
          <DetailStat
            label="Humidity"
            value={formatHumidity(reading.observations.relative_humidity_pct)}
            tone="bg-surface-blue-tint"
          />
          <DetailStat
            label="Pressure"
            value={formatPressure(reading.observations.pressure_hpa)}
            tone="bg-surface-blue-tint"
            valueTone="text-info"
          />
        </div>
        <div className="mt-2 divide-y divide-border rounded-xl border border-border px-2.5">
          <FactRow label="Timestamp" value={reading.timestamp} />
          <FactRow label="Station" value={`${alert.station_id} · ${reading.city}`} />
          <FactRow label="Sequence" value={String(reading.sequence)} />
        </div>
      </section>

      <section className="panel p-4" aria-label="Why flagged">
        <p className="section-kicker">Why SkyGuard flagged it</p>
        <div className="mt-2">
          <EvidenceList evidence={evidence} loading={false} />
        </div>
      </section>

      <section className="panel p-4" aria-label="Root cause">
        <p className="section-kicker">
          {shape === "station-statistical" ? "Detection reason" : "Root cause"}
        </p>
        <p className="mt-2 text-[12px] leading-snug">
          <strong className="text-foreground">{reason ?? "Not available"}</strong>
          {severityText !== null && (
            <span className="text-muted-foreground"> · severity {severityText}</span>
          )}
          {confidence !== null && (
            <span className="text-muted-foreground">
              {" "}
              · {formatConfidence(confidence)} confidence
            </span>
          )}
          {cleanText(reading.root_cause.runner_up) && (
            <span className="text-muted-foreground">
              {" "}
              · runner-up {reading.root_cause.runner_up} (uncertainty preserved)
            </span>
          )}
        </p>
        {factors.length > 0 && (
          <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[11px] text-muted-foreground">
            {factors.map((factor) => (
              <li key={factor}>{factor}</li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[10px] text-muted-foreground">
          Detector: {readingDetectorLabel(reading)} · Spatial context {spatialView.level} —{" "}
          {spatialView.label}
        </p>
        <div className="mt-2">
          <OutcomeBanner
            status={status}
            outcome={reason ?? alert.event}
            message={
              cleanText(reading.explanation.text) ??
              "Streamed replay event assessed by the frozen pipeline."
            }
            rootCauseConfidence={confidence}
            ensembleMethod={shape === "ensemble" ? reading.anomaly.method : null}
            anomalyScore={shape === "ensemble" ? reading.anomaly.score : null}
          />
        </div>
      </section>

      <section className="panel p-4" aria-label="Explanation">
        <ExplanationBlock
          explanation={{ text: reading.explanation.text, features: explanationFeatures }}
          loading={false}
        />
      </section>

      <section className="panel p-4" aria-label="Temporal context">
        <p className="section-kicker">Temporal context · station history</p>
        <div className="mt-2">
          {historyQuery.isPending ? (
            <p
              className="flex h-[120px] items-center justify-center text-[10px] text-muted-foreground"
              role="status"
            >
              Loading station history…
            </p>
          ) : historyQuery.isError ? (
            <p
              className="flex h-[120px] items-center justify-center text-[10px] text-muted-foreground"
              role="alert"
            >
              Station history unavailable.
            </p>
          ) : (
            <HistoryChart
              data={historySeries}
              height={120}
              ariaLabel={`Temperature history for ${alert.station_id}`}
            />
          )}
        </div>
      </section>

      <section className="flex flex-wrap gap-2" aria-label="Replay investigation actions">
        <Button size="sm" variant="outline" onClick={() => navigate({ to: "/" })}>
          <ArrowLeft />
          Back to Replay
        </Button>
        <Button size="sm" variant="outline" asChild>
          <Link to="/stations/$stationId" params={{ stationId: alert.station_id }}>
            View station
          </Link>
        </Button>
      </section>
    </>
  );
}
