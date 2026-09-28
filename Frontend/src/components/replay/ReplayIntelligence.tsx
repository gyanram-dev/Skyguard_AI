import { useNavigate } from "@tanstack/react-router";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/common";
import { SensorSpark } from "@/components/charts";
import { cleanText, formatConfidence, formatScore, formatTemp, formatTime } from "@/lib/format";
import { normalizeStatus } from "@/lib/api";
import type { LiveReplay } from "@/hooks/useLiveReplay";

function statusText(status: string): string {
  switch (status) {
    case "preparing":
      return "Preparing";
    case "running":
      return "Running";
    case "paused":
      return "Paused";
    case "stopped":
      return "Stopped";
    case "completed":
      return "Completed";
    default:
      return "Idle";
  }
}

/**
 * Replay intelligence: session statistics, latest activity, latest
 * detection, and a mini temperature trend. Reads existing
 * ReplaySessionProvider state only — no hook calls, no sockets, no
 * inference, no backend endpoints.
 */
export function ReplayIntelligence({ live }: { live: LiveReplay }) {
  const idle = live.replay.status === "idle";
  return (
    <section className="panel shrink-0 p-3.5" aria-label="Replay intelligence">
      <SessionSection live={live} idle={idle} />
      {!idle && (
        <>
          <ActivitySection live={live} />
          <DetectionSection live={live} />
          <TrendSection live={live} />
        </>
      )}
    </section>
  );
}

function SessionSection({ live, idle }: { live: LiveReplay; idle: boolean }) {
  if (idle) {
    return (
      <div>
        <p className="section-kicker">Replay Session</p>
        <p className="mt-1 text-[10px] text-muted-foreground" role="status">
          Start a historical replay to generate observations.
        </p>
        <p className="mt-2 text-[10px] font-extrabold uppercase tracking-[0.06em]">
          What you&apos;ll see
        </p>
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[10px] text-muted-foreground">
          <li>streamed sensor observations</li>
          <li>anomaly detections</li>
          <li>replay session statistics</li>
          <li>investigation links</li>
        </ul>
      </div>
    );
  }
  const cells = [
    { label: "Observations", value: String(live.summary.observations) },
    { label: "Normal", value: String(live.summary.normal) },
    { label: "Anomalies", value: String(live.summary.anomalies) },
  ];
  return (
    <div>
      <p className="section-kicker">Replay Session</p>
      <div className="mt-1 grid grid-cols-3 gap-1.5">
        {cells.map((cell) => (
          <div key={cell.label} className="rounded-xl bg-muted p-2">
            <p className="text-[9px] font-semibold text-muted-foreground">{cell.label}</p>
            <p className="text-base font-extrabold leading-tight tabular-nums">{cell.value}</p>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground">
        <span>
          Replay status{" "}
          <strong className="text-foreground">{statusText(live.replay.status)}</strong>
        </span>
        {live.replay.stationId && (
          <span>
            Station <strong className="text-foreground">{live.replay.stationId}</strong>
          </span>
        )}
        {live.replay.split && (
          <span>
            Split <strong className="text-foreground">{live.replay.split}</strong>
          </span>
        )}
        {live.replay.speed != null && (
          <span>
            Speed <strong className="text-foreground">{live.replay.speed}×</strong>
          </span>
        )}
      </div>
    </div>
  );
}

function ActivitySection({ live }: { live: LiveReplay }) {
  const rows = live.recentReadings.slice(-4).reverse();
  return (
    <div className="mt-2.5 border-t border-border pt-2">
      <p className="section-kicker">Latest Activity</p>
      {rows.length === 0 ? (
        <p className="mt-1 text-[10px] text-muted-foreground" role="status">
          Waiting for streamed readings…
        </p>
      ) : (
        <ul className="mt-1 space-y-1">
          {rows.map((reading) => {
            const anomalous = reading.anomaly.detected;
            const known = !!reading.root_cause.class && reading.root_cause.class !== "UNKNOWN";
            return (
              <li
                key={`${reading.station_id}-${reading.sequence}`}
                className="flex items-center gap-2 text-[10px]"
                title={`${reading.station_id} · ${reading.timestamp}`}
              >
                <time className="shrink-0 font-semibold text-muted-foreground">
                  {formatTime(reading.timestamp)}
                </time>
                {anomalous ? (
                  <>
                    <strong className="shrink-0 font-extrabold">
                      {reading.root_cause.class ?? "Anomaly"}
                    </strong>
                    <span className="ml-auto">
                      <StatusBadge status={known ? "anomaly" : "review"} />
                    </span>
                  </>
                ) : (
                  <>
                    <span className="text-muted-foreground">Normal</span>
                    <span className="ml-auto">
                      <StatusBadge
                        status={reading.data_quality.ml_eligible ? "healthy" : "offline"}
                      />
                    </span>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function DetectionSection({ live }: { live: LiveReplay }) {
  const navigate = useNavigate();
  const alert = live.liveAlerts[0] ?? null;
  const reading = alert ? (live.anomalyMap[alert.alert_id] ?? null) : null;
  return (
    <div className="mt-2.5 border-t border-border pt-2">
      <p className="section-kicker">Latest Detection</p>
      {!alert || !reading ? (
        <p className="mt-1 text-[10px] text-muted-foreground" role="status">
          No anomalies detected in this replay yet.
        </p>
      ) : (
        <div className="mt-1 rounded-xl border border-border p-2.5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-extrabold">
              {reading.station_id} · {cleanText(alert.root_cause) ?? alert.event}
            </p>
            <StatusBadge status={normalizeStatus(alert.status, true)} />
          </div>
          <div className="mt-1.5 grid grid-cols-2 gap-1.5">
            <div className="rounded-xl bg-muted p-2">
              <p className="text-[9px] font-semibold text-muted-foreground">Score</p>
              <p className="text-sm font-extrabold tabular-nums">{formatScore(alert.score)}</p>
            </div>
            <div className="rounded-xl bg-muted p-2">
              <p className="text-[9px] font-semibold text-muted-foreground">Confidence</p>
              <p className="text-sm font-extrabold tabular-nums">
                {alert.confidence !== null && alert.confidence !== undefined
                  ? formatConfidence(alert.confidence)
                  : "Not available"}
              </p>
            </div>
          </div>
          <Button
            size="sm"
            className="mt-2 w-full"
            onClick={() =>
              navigate({
                to: "/investigations/replay/$anomalyId",
                params: { anomalyId: alert.alert_id },
              })
            }
          >
            Investigate →
          </Button>
        </div>
      )}
    </div>
  );
}

function TrendSection({ live }: { live: LiveReplay }) {
  const stationId = live.replay.stationId;
  const values = (
    stationId ? live.recentReadings.filter((row) => row.station_id === stationId) : []
  )
    .slice(-30)
    .map((row, index) => ({ index, value: row.observations.temperature_c }));
  const usable = values.filter(
    (entry): entry is { index: number; value: number } => entry.value !== null,
  );
  return (
    <div className="mt-2.5 border-t border-border pt-2">
      <p className="section-kicker">Temperature trend · streamed</p>
      {usable.length < 2 ? (
        <p className="mt-1 text-[10px] text-muted-foreground" role="status">
          Waiting for enough observations…
        </p>
      ) : (
        <div className="mt-1 h-[64px]">
          <SensorSpark values={values} color="var(--chart-alert)" gradientId="fill-replay-trend" />
        </div>
      )}
      <p className="mt-1 text-[9px] text-muted-foreground">
        Contextual replay history — not a diagnostic chart.
      </p>
    </div>
  );
}
