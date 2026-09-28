import { Pause, Play, Square } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { LiveReplay } from "@/hooks/useLiveReplay";
import { useReadiness } from "@/hooks/useSkyguard";

const SPEED_PRESETS = [1, 10, 60, 300, 900];

const DEMO_FLOW = [
  "Start Historical Replay",
  "Watch station observations",
  "Open an anomaly",
  "Inspect investigation",
  "Try Judge Probe",
  "Open Evaluation",
];

const statusTone: Record<string, string> = {
  running: "bg-success",
  preparing: "bg-info",
  paused: "bg-warning",
  stopped: "bg-offline",
  completed: "bg-success",
  idle: "bg-offline",
};

function statusLabel(live: LiveReplay): string {
  if (live.connection === "connecting") return "Connecting…";
  if (live.connection === "disconnected" && live.replay.status === "idle") {
    return "Replay idle";
  }
  if (live.connection === "disconnected") return "Disconnected";
  switch (live.replay.status) {
    case "preparing":
      return "Preparing replay…";
    case "running":
      return "Replay running";
    case "paused":
      return "Replay paused";
    case "stopped":
      return "Replay stopped";
    case "completed":
      return "Replay complete";
    default:
      return "Replay connected";
  }
}

/** Compact replay controls: station/split/speed + start/pause/resume/stop. */
export function ReplayControls({
  live,
  stations,
}: {
  live: LiveReplay;
  stations: Array<{ id: string; city: string }>;
}) {
  const running = live.replay.status === "running";
  const paused = live.replay.status === "paused";
  const busy = running || paused || live.replay.status === "preparing";
  const dot =
    live.connection !== "connected" ? "bg-offline" : (statusTone[live.replay.status] ?? "bg-info");

  const [stationId, setStationId] = useState("DEL-01");
  const [split, setSplit] = useState("OOD");
  const [speed, setSpeed] = useState(10);
  const [showFlow, setShowFlow] = useState(false);
  const readinessQuery = useReadiness();

  return (
    <div className="min-w-0 flex-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5" role="status">
          <span className={cn("status-dot", dot)} />
          <strong className="text-[11px] font-extrabold">LIVE REPLAY</strong>
          <span className="text-[10px] text-muted-foreground">{statusLabel(live)}</span>
        </span>
        <ReadinessChip
          ready={readinessQuery.data?.ready ?? null}
          missing={readinessQuery.data?.missing ?? []}
        />
        <button
          type="button"
          onClick={() => setShowFlow((value) => !value)}
          aria-expanded={showFlow}
          className="text-[10px] font-bold text-info hover:underline"
        >
          Demo flow
        </button>
        <Select value={stationId} onValueChange={setStationId} disabled={busy}>
          <SelectTrigger className="h-8 w-[132px] text-[11px]" aria-label="Replay station">
            <SelectValue placeholder="Station" />
          </SelectTrigger>
          <SelectContent>
            {stations.map((station) => (
              <SelectItem key={station.id} value={station.id}>
                {station.id} · {station.city}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={split} onValueChange={setSplit} disabled={busy}>
          <SelectTrigger className="h-8 w-[96px] text-[11px]" aria-label="Replay split">
            <SelectValue placeholder="Split" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="OOD">OOD split</SelectItem>
            <SelectItem value="ID">ID split</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={String(busy ? (live.replay.speed ?? speed) : speed)}
          onValueChange={(value) => {
            const next = Number(value);
            if (busy) live.setSpeed(next);
            else setSpeed(next);
          }}
        >
          <SelectTrigger className="h-8 w-[96px] text-[11px]" aria-label="Replay speed">
            <SelectValue placeholder="Speed" />
          </SelectTrigger>
          <SelectContent>
            {SPEED_PRESETS.map((speed) => (
              <SelectItem key={speed} value={String(speed)}>
                {speed}×
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {!busy ? (
          <Button size="sm" onClick={() => live.start({ station_id: stationId, split, speed })}>
            <Play />
            Start
          </Button>
        ) : (
          <>
            {running && (
              <Button size="sm" variant="outline" onClick={live.pause}>
                <Pause />
                Pause
              </Button>
            )}
            {paused && (
              <Button size="sm" onClick={live.resume}>
                <Play />
                Resume
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={live.stop}>
              <Square />
              Stop
            </Button>
          </>
        )}
      </div>
      <p className="mt-1.5 text-[10px] text-muted-foreground">
        Accelerated historical replay — not a live sensor feed.
        {live.replay.processed > 0 &&
          ` ${live.replay.processed} events · ${live.replay.anomalies} anomalies`}
        {live.replay.effectiveSpeed != null && ` · effective ${live.replay.effectiveSpeed}×`}
        {live.completeInfo && ` · done in ${(live.completeInfo.durationMs / 1000).toFixed(1)}s`}
      </p>
      {showFlow && (
        <ol className="mt-1.5 list-decimal space-y-0.5 pl-5 text-[10px] text-muted-foreground">
          {DEMO_FLOW.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      )}
      {live.notice && (
        <p className="mt-1 text-[10px] font-semibold text-offline-deep" role="alert">
          {live.notice}{" "}
          <button
            type="button"
            onClick={live.clearNotice}
            className="font-bold text-info hover:underline"
          >
            Dismiss
          </button>
        </p>
      )}
    </div>
  );
}

/** Non-blocking demo capability chip (never mocks, never blocks the app). */
function ReadinessChip({ ready, missing }: { ready: boolean | null; missing: string[] }) {
  if (ready === null) return null;
  if (ready) {
    return (
      <span className="status-pill bg-success-soft text-success-deep" role="status">
        <span className="status-dot bg-success" />
        Demo Ready
      </span>
    );
  }
  return (
    <span
      className="status-pill bg-offline-soft text-offline-deep"
      role="alert"
      title={missing.length > 0 ? missing.join("; ") : "Demo services unavailable."}
    >
      <span className="status-dot bg-offline" />
      Demo services unavailable
    </span>
  );
}
