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

/**
 * Replay controls: station/split/speed selection + start/pause/resume/stop.
 *
 * Fully controlled — the parent (ReplayStage) owns the selection so the
 * station context header always matches what will be (or is being) replayed.
 * `stations` comes from the backend station response: the frozen ensemble
 * station plus every calibrated station-specific statistical detector. A
 * calibrated station replays its own real history, so its split is fixed to
 * HISTORICAL by the backend — the selector reflects that instead of offering a
 * benchmark split that would be ignored.
 */
export function ReplayControls({
  live,
  stations,
  stationId,
  onStationChange,
  split,
  onSplitChange,
  speed,
  onSpeedChange,
}: {
  live: LiveReplay;
  stations: Array<{ id: string; city: string; statistical?: boolean }>;
  stationId: string;
  onStationChange: (stationId: string) => void;
  split: string;
  onSplitChange: (split: string) => void;
  speed: number;
  onSpeedChange: (speed: number) => void;
}) {
  const [showFlow, setShowFlow] = useState(false);
  const readinessQuery = useReadiness();
  const running = live.replay.status === "running";
  const paused = live.replay.status === "paused";
  const busy = running || paused || live.replay.status === "preparing";
  const statistical = stations.find((station) => station.id === stationId)?.statistical === true;
  const effectiveSplit = statistical ? "HISTORICAL" : split;
  const canStart = stationId !== "";

  return (
    <div className="mt-2.5 min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={stationId} onValueChange={onStationChange} disabled={busy}>
          <SelectTrigger className="h-8 w-[132px] text-[11px]" aria-label="Replay station">
            <SelectValue placeholder={stations.length === 0 ? "Loading stations…" : "Station"} />
          </SelectTrigger>
          <SelectContent>
            {stations.map((station) => (
              <SelectItem key={station.id} value={station.id}>
                {station.id} · {station.city}
                {station.statistical ? " · station detector" : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {statistical ? (
          <span
            className="flex h-8 items-center rounded-md border border-border px-2.5 text-[11px] text-muted-foreground"
            title="A calibrated station detector replays this station's own real history; no benchmark split applies."
          >
            HISTORICAL
          </span>
        ) : (
          <Select value={split} onValueChange={onSplitChange} disabled={busy}>
            <SelectTrigger className="h-8 w-[96px] text-[11px]" aria-label="Replay split">
              <SelectValue placeholder="Split" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="OOD">OOD split</SelectItem>
              <SelectItem value="ID">ID split</SelectItem>
            </SelectContent>
          </Select>
        )}
        <Select
          value={String(busy ? (live.replay.speed ?? speed) : speed)}
          onValueChange={(value) => {
            const next = Number(value);
            if (busy) live.setSpeed(next);
            else onSpeedChange(next);
          }}
        >
          <SelectTrigger className="h-8 w-[96px] text-[11px]" aria-label="Replay speed">
            <SelectValue placeholder="Speed" />
          </SelectTrigger>
          <SelectContent>
            {SPEED_PRESETS.map((preset) => (
              <SelectItem key={preset} value={String(preset)}>
                {preset}×
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {!busy ? (
          <Button
            size="sm"
            disabled={!canStart}
            onClick={() => live.start({ station_id: stationId, split: effectiveSplit, speed })}
          >
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
      </div>
      <p className="mt-1.5 text-[10px] text-muted-foreground">
        Historical observations processed through the detection pipeline.
        {statistical && " Station-specific calibrated detector."}
      </p>
      {stations.length === 0 && (
        <p className="mt-1 text-[10px] font-semibold text-offline-deep" role="status">
          Historical replay unavailable — no station with detector coverage was reported by the
          backend.
        </p>
      )}
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
