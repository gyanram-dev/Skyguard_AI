import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { type ReactNode, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  Bell,
  Database,
  Droplets,
  FlaskConical,
  Gauge,
  GitBranch,
  Network,
  Radio,
  ShieldAlert,
  ShieldCheck,
  Snowflake,
  Thermometer,
  TrendingUp,
  Waves,
} from "lucide-react";
import { ResponsiveContainer } from "recharts";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { SensorSpark } from "@/components/charts";
import { ReplayStage } from "@/components/replay/ReplayStage";
import { useReplaySession } from "@/components/replay/ReplaySessionContext";
import type { LiveReading } from "@/lib/live";
import { hasDetectorCoverage, type StationDetailResponse } from "@/lib/api";
import {
  errorMessage,
  formatDisplayTerm,
  formatHumidity,
  formatPressure,
  formatTemp,
} from "@/lib/format";
import { mergeStations, stationMapCapability, type MergedStation } from "@/lib/mapMeta";
import { useNetworkSummary, useStation, useStationHistory, useStations } from "@/hooks/useSkyguard";
import type { HistoryVariable, NetworkSummary } from "@/lib/api";

const indiaAsset = { url: "/assets/india.png" };

export const Route = createFileRoute("/_app/")({
  head: () => ({
    meta: [
      { title: "SkyGuard AI | AI-Powered AWS Anomaly Detection" },
      {
        name: "description",
        content:
          "Detect faulty weather sensors without mistaking genuine extreme weather for sensor failure. Context-aware quality control for Temperature, Pressure and Relative Humidity.",
      },
      { property: "og:title", content: "SkyGuard AI — AI-Powered AWS Anomaly Detection" },
      {
        property: "og:description",
        content:
          "Context-aware quality control for Temperature, Pressure and Relative Humidity observations across India's station network.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: LiveOverview,
});

function LiveOverview() {
  // No station is forced as the default: the Overview opens on the network as
  // a whole and then follows whichever station the user picks on the map.
  const [selectedStationId, setSelectedStationId] = useState<string | null>(null);

  // Replay session lives in the AppShell-level provider: navigating between
  // routes remounts this page but never destroys the stream or counters.
  // Anomaly selection is URL-driven (/investigations/replay/$anomalyId).
  const { live } = useReplaySession();
  const navigate = useNavigate();
  const liveActive =
    live.replay.status === "running" ||
    live.replay.status === "paused" ||
    live.replay.status === "preparing";

  const networkQuery = useNetworkSummary();
  const stationsQuery = useStations();

  const mergedStations = useMemo(
    () => mergeStations(stationsQuery.data?.stations ?? []),
    [stationsQuery.data],
  );

  // Historical replay is offered for every station the backend reports a
  // detector for: the frozen ensemble (Delhi) plus each calibrated
  // station-specific statistical detector. Coverage is read from the API
  // response, never hardcoded here.
  const replayStations = useMemo(() => {
    const covered = mergedStations.filter((station) => hasDetectorCoverage(station.api));
    return covered.map((station) => ({
      id: station.id,
      city: station.city,
      statistical: station.api?.capability?.detector?.detector_available === true,
      api: station.api,
    }));
  }, [mergedStations]);

  const liveStations = useMemo<(MergedStation & { live?: LiveReading })[]>(
    () =>
      mergedStations.map((station) => {
        const reading = liveActive ? live.latestByStation[station.id] : undefined;
        if (!reading) return station;
        const anomalous = reading.anomaly.detected;
        const known = !!reading.root_cause.class && reading.root_cause.class !== "UNKNOWN";
        return {
          ...station,
          status: anomalous
            ? known
              ? ("anomaly" as const)
              : ("review" as const)
            : reading.data_quality.ml_eligible
              ? station.status
              : // A historical observation that fails data-quality checks is
                // not "offline" — it needs review before any verdict.
                ("review" as const),
          temperature: formatTemp(reading.observations.temperature_c),
          live: reading,
        };
      }),
    [mergedStations, live.latestByStation, liveActive],
  );

  const selectedStation = useMemo(
    () => liveStations.find((station) => station.id === selectedStationId) ?? null,
    [liveStations, selectedStationId],
  );

  const selectedLive =
    liveActive && selectedStationId ? (live.latestByStation[selectedStationId] ?? null) : null;

  const liveSeries = useMemo(() => {
    const rows = live.recentReadings.filter((row) => row.station_id === selectedStationId);
    const pick = (get: (row: LiveReading) => number | null) =>
      rows.map((row, index) => ({ index, value: get(row) }));
    return {
      temperature: pick((row) => row.observations.temperature_c),
      pressure: pick((row) => row.observations.pressure_hpa),
      humidity: pick((row) => row.observations.relative_humidity_pct),
    };
  }, [live.recentReadings, selectedStationId]);

  // Station detail is only requested for stations that actually have backend
  // data; offline/unmapped stations render an unavailable state instead of
  // erroring against a 404.
  const detailStationId = selectedStation?.api?.data_available === true ? selectedStation.id : null;
  const stationDetailQuery = useStation(detailStationId);

  const selectStation = (stationId: string) => setSelectedStationId(stationId);

  const spatial = stationDetailQuery.data?.spatial_context ?? null;

  return (
    <>
      <Hero
        summary={networkQuery.data}
        loading={networkQuery.isPending}
        error={networkQuery.isError ? errorMessage(networkQuery.error) : null}
        onTestObservation={() => navigate({ to: "/judge-probe" })}
        onViewAlerts={() => navigate({ to: "/alerts" })}
      >
        <MapLab
          stations={liveStations}
          selectedStation={selectedStation}
          stationsLoading={stationsQuery.isPending}
          stationsError={stationsQuery.isError ? errorMessage(stationsQuery.error) : null}
          stationCount={networkQuery.data?.indian_operational_monitored ?? null}
          onSelectStation={selectStation}
        />
      </Hero>

      <NetworkMetricStrip
        summary={networkQuery.data}
        loading={networkQuery.isPending}
        error={networkQuery.isError ? errorMessage(networkQuery.error) : null}
      />

      <NetworkHealth
        summary={networkQuery.data}
        loading={networkQuery.isPending}
        error={networkQuery.isError ? errorMessage(networkQuery.error) : null}
        onViewAlerts={() => navigate({ to: "/alerts" })}
      />

      <SelectedStationIntelligence
        station={selectedStation}
        detail={stationDetailQuery.data}
        loading={stationDetailQuery.isPending && detailStationId !== null}
        error={stationDetailQuery.isError ? errorMessage(stationDetailQuery.error) : null}
        liveReading={selectedLive}
        liveSeries={liveSeries}
        liveActive={liveActive}
        stationCount={networkQuery.data?.indian_operational_monitored ?? null}
      />

      <HowSkyGuardDecides />
      <WhatSkyGuardDetects />
      <RealWeatherOrFault
        spatial={spatial}
        stationLabel={selectedStation ? `${selectedStation.id} · ${selectedStation.city}` : null}
      />

      <ReplayStage live={live} stations={replayStations} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Product-facing sections. Every number rendered below comes from the backend
// responses already loaded on this page; missing values render as honest
// unavailable states, never as fabricated completeness.
// ---------------------------------------------------------------------------

function Hero({
  summary,
  loading,
  error,
  onTestObservation,
  onViewAlerts,
  children,
}: {
  summary: NetworkSummary | undefined;
  loading: boolean;
  error: string | null;
  onTestObservation: () => void;
  onViewAlerts: () => void;
  children: ReactNode;
}) {
  return (
    <section
      className="grid shrink-0 grid-cols-1 items-center gap-2 xl:grid-cols-[minmax(0,0.42fr)_minmax(0,0.58fr)] xl:gap-4"
      aria-label="SkyGuard India AWS network"
    >
      <div className="flex min-w-0 flex-col justify-center py-0.5 xl:py-1">
        <p className="text-[12px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
          SkyGuard AI
        </p>
        <h2 className="mt-3 text-[2.75rem] font-bold leading-[1.05] tracking-[-0.035em] text-foreground xl:text-[3rem]">
          Can this weather observation
          <br />
          <span className="text-[#20D7F5]">be trusted?</span>
        </h2>
        <p className="mt-2.5 max-w-[42ch] text-base leading-snug text-muted-foreground">
          SkyGuard evaluates Temperature, Pressure and Relative Humidity using temporal,
          multivariate and spatial context.
        </p>
        <p className="mt-2 max-w-[42ch] text-base leading-snug text-muted-foreground">
          Detect sensor anomalies without confusing them with genuine weather events.
        </p>
        <div className="mt-5 flex flex-wrap items-center text-[13px] font-medium text-muted-foreground">
          <span className="flex items-center gap-2 pr-4">
            <Thermometer className="size-4 text-[#20D7F5]" strokeWidth={1.8} />
            Temperature
          </span>
          <span aria-hidden="true" className="h-[18px] w-px bg-border" />
          <span className="flex items-center gap-2 px-4">
            <Gauge className="size-4 text-sky" strokeWidth={1.8} />
            Pressure
          </span>
          <span aria-hidden="true" className="h-[18px] w-px bg-border" />
          <span className="flex items-center gap-2 pl-4">
            <Droplets className="size-4 text-[#20D7F5]" strokeWidth={1.8} />
            Relative Humidity
          </span>
        </div>
        <div className="mt-7 flex flex-wrap items-center gap-4">
          <Button
            className="h-[54px] w-[248px] rounded-lg bg-[#22CFEA] text-[14px] font-semibold text-[#06131C] hover:bg-[#4FD8F2]"
            onClick={onTestObservation}
          >
            <FlaskConical />
            Test an Observation →
          </Button>
          <Button
            variant="outline"
            className="h-[54px] w-[170px] rounded-lg border-border bg-transparent text-[14px] text-foreground"
            onClick={onViewAlerts}
          >
            <Bell />
            View Alerts
          </Button>
        </div>
        <p className="mt-2 max-w-[48ch] text-[11px] leading-snug text-muted-foreground">
          Real Indian historical observations; detector verdicts are shown only where detector
          coverage exists.
          {error ? ` Network summary unavailable: ${error}` : ""}
        </p>
      </div>
      <div className="relative min-h-[360px] min-w-0 xl:min-h-[430px]">{children}</div>
    </section>
  );
}

function NetworkMetricStrip({
  summary,
  loading,
  error,
}: {
  summary: NetworkSummary | undefined;
  loading: boolean;
  error: string | null;
}) {
  const exact = (count: number | undefined) => {
    if (loading) return "…";
    if (error || count === undefined) return "—";
    return count.toLocaleString();
  };
  const stations = summary?.indian_operational_monitored;
  // Stations a detector actually covers: the frozen full T/P/RH ensemble plus
  // the calibrated station-specific statistical detectors (PARTIAL). Both are
  // measured backend counts. `detector_covered` alone counts only stations whose
  // verdict is available without a replay, which would understate the ten
  // calibrated stations — a PARTIAL station is detector-covered, not uncovered.
  const detectorCoverage =
    summary?.full_tpr_stations !== undefined && summary?.partial_stations !== undefined
      ? summary.full_tpr_stations + summary.partial_stations
      : summary?.detector_covered;
  const cells: Array<{ label: string; value: string; icon: typeof Radio; tone: string }> = [
    { label: "Indian stations", value: exact(stations), icon: Radio, tone: "text-[#20D7F5]" },
    {
      label: "Historical observations",
      value: exact(summary?.observations_indexed),
      icon: Database,
      tone: "text-[#20D7F5]",
    },
    {
      label: "Detector coverage",
      value: `${exact(detectorCoverage)} / ${exact(stations)}`,
      icon: ShieldAlert,
      tone: "text-[#F4B400]",
    },
    {
      label: "Live-capable",
      value: exact(summary?.live_capable_stations),
      icon: Activity,
      tone: "text-[#20D7F5]",
    },
  ];
  return (
    <section
      className="mt-3 grid shrink-0 grid-cols-2 rounded-xl border border-border bg-card px-2 py-4 sm:grid-cols-4"
      aria-label="Network metrics"
    >
      {error && (
        <p className="col-span-full mb-1 px-3 text-[9px] font-semibold text-offline-deep">
          {error}
        </p>
      )}
      {cells.map((cell, index) => (
        <div
          key={cell.label}
          className={
            index === 0
              ? "flex min-w-0 items-center gap-3 px-5"
              : "flex min-w-0 items-center gap-3 border-l border-border px-5"
          }
        >
          <cell.icon className={`size-6 shrink-0 ${cell.tone}`} strokeWidth={1.8} />
          <div className="min-w-0">
            <p className="truncate text-[1.75rem] font-semibold leading-none tabular-nums tracking-tight text-foreground">
              {cell.value}
            </p>
            <p className="mt-1 text-[12px] leading-tight text-muted-foreground">{cell.label}</p>
          </div>
        </div>
      ))}
    </section>
  );
}

/**
 * Network-level status only. Every figure is read from /network/summary — the
 * detailed alert queue lives on the Alerts page, not here.
 */
function NetworkHealth({
  summary,
  loading,
  error,
  onViewAlerts,
}: {
  summary: NetworkSummary | undefined;
  loading: boolean;
  error: string | null;
  onViewAlerts: () => void;
}) {
  const value = (n: number | undefined | null) => {
    if (loading) return "…";
    if (error || n === undefined || n === null) return "—";
    return n.toLocaleString();
  };
  const stations = summary?.indian_operational_monitored ?? summary?.total_stations;
  // A station is detector-covered when a detector can produce a verdict: the
  // frozen ensemble (FULL) plus each calibrated station-specific detector
  // (PARTIAL). Both counts are measured backend values.
  const full = summary?.full_tpr_stations;
  const partial = summary?.partial_stations;
  const covered = full !== undefined && partial !== undefined ? full + partial : undefined;
  const needsAttention =
    summary?.anomaly !== undefined || summary?.needs_review !== undefined
      ? (summary?.anomaly ?? 0) + (summary?.needs_review ?? 0)
      : undefined;
  const cells: Array<{ label: string; value: string; note: string }> = [
    {
      label: "Detector coverage",
      value: `${value(covered)} / ${value(stations)}`,
      note: "stations where a detector can produce a verdict",
    },
    {
      label: "Full T/P/RH",
      value: value(full),
      note: "frozen ensemble — every variable covered",
    },
    {
      label: "Partial coverage",
      value: value(partial),
      note: "calibrated station detector, variable gaps declared",
    },
    {
      label: "Requires investigation",
      value: value(needsAttention),
      note: "anomaly or review status in the current snapshot",
    },
  ];
  const contextOnly = summary?.context_only_stations;
  return (
    <section className="panel mt-3 shrink-0 p-4" aria-label="Network health">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="section-kicker">Network health</p>
          <h2 className="mt-1 text-lg font-extrabold">Can the network be trusted?</h2>
          <p className="mt-1 max-w-[70ch] text-[11px] leading-snug text-muted-foreground">
            Detector verdicts are only reported where a detector covers the station.{" "}
            {contextOnly !== undefined
              ? `${contextOnly} context-only station${contextOnly === 1 ? "" : "s"} carry real observations but never a verdict.`
              : "Context-only stations carry real observations but never a verdict."}
            {error ? ` Network summary unavailable: ${error}` : ""}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-8 rounded-lg border-border bg-transparent px-3 text-[12px]"
          onClick={onViewAlerts}
        >
          View alerts
          <ArrowRight className="size-3.5 text-[#20D7F5]" />
        </Button>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {cells.map((cell) => (
          <div key={cell.label} className="min-w-0 rounded-lg border border-border bg-muted/40 p-3">
            <dt className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
              {cell.label}
            </dt>
            <dd className="mt-1 text-[22px] font-semibold leading-none tabular-nums tracking-tight">
              {cell.value}
            </dd>
            <p className="mt-1 text-[10px] leading-snug text-muted-foreground">{cell.note}</p>
          </div>
        ))}
      </dl>
    </section>
  );
}

function HowSkyGuardDecides() {
  const steps: Array<{ title: string; detail: string; icon: typeof Activity }> = [
    {
      title: "AWS observation",
      detail: "Temperature · Pressure · Relative Humidity",
      icon: Activity,
    },
    {
      title: "Data quality",
      detail: "Staleness, ranges, frozen runs, missingness",
      icon: ShieldCheck,
    },
    {
      title: "Temporal intelligence",
      detail: "Causal deltas, trends and window behaviour",
      icon: GitBranch,
    },
    {
      title: "AI detection",
      detail: "Statistical · Isolation Forest · LSTM Autoencoder · Ensemble",
      icon: Activity,
    },
    {
      title: "Multivariate consistency",
      detail: "Do T, P and RH agree with each other?",
      icon: Waves,
    },
    {
      title: "Spatial context",
      detail: "Do compatible nearby stations behave the same way?",
      icon: Network,
    },
    {
      title: "Explainable decision",
      detail: "Anomaly score, confidence, root cause, SHAP contributions",
      icon: ShieldCheck,
    },
    { title: "Alert / investigation", detail: "Triage queue and evidence workspace", icon: Bell },
  ];
  return (
    <section className="panel shrink-0 p-4" aria-label="How SkyGuard decides">
      <p className="section-kicker">Architecture</p>
      <h2 className="mt-1 text-lg font-extrabold">How SkyGuard Decides</h2>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Every observation follows the same pipeline. Component availability is reported per station
        — a component that cannot run is shown as unavailable, never as a pass.
      </p>
      <ol className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {steps.map((step, index) => (
          <li key={step.title} className="rounded-xl border border-border bg-card p-2.5">
            <div className="flex items-center gap-2">
              <span className="flex size-7 items-center justify-center rounded-lg bg-info-soft text-info">
                <step.icon className="size-3.5" />
              </span>
              <span className="text-[9px] font-extrabold text-muted-foreground">
                STEP {index + 1}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] font-extrabold leading-tight">{step.title}</p>
            <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">{step.detail}</p>
          </li>
        ))}
      </ol>
      <p className="mt-2 text-[10px] text-muted-foreground">
        The full ensemble runs on the server; only the streaming/edge subset is lightweight. No card
        here claims the entire ensemble runs on a microcontroller.
      </p>
    </section>
  );
}

function WhatSkyGuardDetects() {
  const detections: Array<{
    title: string;
    verb: string;
    detail: string;
    icon: typeof Activity;
    tone: string;
  }> = [
    {
      title: "Spike",
      verb: "Detects",
      detail: "Sudden abnormal sensor change beyond the calibrated threshold.",
      icon: Activity,
      tone: "bg-anomaly-soft text-anomaly",
    },
    {
      title: "Frozen sensor",
      verb: "Detects",
      detail: "Repeated / stuck sensor behaviour flagged by run-length quality checks.",
      icon: Snowflake,
      tone: "bg-info-soft text-info",
    },
    {
      title: "Drift",
      verb: "Monitors",
      detail: "Persistent gradual deviation relative to the sensor's own history.",
      icon: TrendingUp,
      tone: "bg-warning-soft text-warning-deep",
    },
    {
      title: "Cross-variable",
      verb: "Detects",
      detail: "Temperature / pressure / humidity relationships that no longer hold together.",
      icon: Waves,
      tone: "bg-info-soft text-info",
    },
    {
      title: "Communication",
      verb: "Detects",
      detail: "Missing, stale or failed source delivery, kept separate from physical faults.",
      icon: Radio,
      tone: "bg-offline-soft text-offline-deep",
    },
  ];
  return (
    <section className="panel shrink-0 p-4" aria-label="What SkyGuard detects">
      <p className="section-kicker">Fault taxonomy</p>
      <h2 className="mt-1 text-lg font-extrabold">What SkyGuard Detects</h2>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Fault classes are grouped by the evidence that supports them. Detection strength varies by
        class; per-class benchmark numbers live on the Evaluation page.
      </p>
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {detections.map((entry) => (
          <article key={entry.title} className="rounded-xl border border-border bg-card p-2.5">
            <span className={cn("flex size-8 items-center justify-center rounded-xl", entry.tone)}>
              <entry.icon className="size-4" />
            </span>
            <p className="mt-1.5 text-[11px] font-extrabold leading-tight">{entry.title}</p>
            <p className="mt-0.5 text-[9px] font-bold uppercase tracking-[0.06em] text-muted-foreground">
              {entry.verb}
            </p>
            <p className="mt-1 text-[10px] leading-snug text-muted-foreground">{entry.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

/** The central PS story: a genuine regional event vs a local sensor fault. */
function RealWeatherOrFault({
  spatial,
  stationLabel,
}: {
  spatial: StationDetailResponse["spatial_context"] | null;
  stationLabel: string | null;
}) {
  const states: Array<{ title: string; interpretation: string; detail: string; tone: string }> = [
    {
      title: "State A",
      interpretation: "POSSIBLE REGIONAL EVENT",
      detail: "Compatible neighbouring stations support a regional meteorological change.",
      tone: "bg-info-soft text-info",
    },
    {
      title: "State B",
      interpretation: "LOCAL SENSOR ANOMALY",
      detail: "The target observation differs from compatible nearby station behaviour.",
      tone: "bg-anomaly-soft text-anomaly",
    },
  ];
  const measured =
    spatial?.available === true &&
    (spatial?.context_level ?? "UNAVAILABLE").toUpperCase() !== "UNAVAILABLE";
  return (
    <section className="panel shrink-0 p-4" aria-label="Real weather or sensor fault">
      <p className="section-kicker">The central question</p>
      <h2 className="mt-1 text-lg font-extrabold">Real Weather or Sensor Fault?</h2>
      <p className="mt-1 text-[11px] text-muted-foreground">
        The Phase-22 spatial decision separates a genuine regional event from an isolated sensor
        fault by comparing the target station against compatible neighbours.
      </p>
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {states.map((state) => (
          <article key={state.title} className="rounded-xl border border-border bg-card p-3">
            <p className="text-[9px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground">
              {state.title}
            </p>
            <p
              className={cn(
                "mt-1 inline-block rounded-lg px-2 py-0.5 text-[11px] font-extrabold",
                state.tone,
              )}
            >
              {state.interpretation}
            </p>
            <p className="mt-1.5 text-[10px] leading-snug text-muted-foreground">{state.detail}</p>
          </article>
        ))}
      </div>
      <div className="mt-2 rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
          Measured spatial context
        </p>
        {measured ? (
          <p className="mt-1 text-[11px] text-muted-foreground">
            {stationLabel ?? "Selected station"} — context level{" "}
            <strong className="text-foreground">{spatial?.context_level}</strong> with{" "}
            {spatial?.neighbor_count ?? 0} compatible neighbour(s). Interpretation follows the
            Phase-22 policy.
          </p>
        ) : (
          <p className="mt-1 text-[11px] text-muted-foreground">
            Spatial context unavailable for the current selection. Open a station or run a probe to
            see the measured interpretation — no neighbour values are invented.
          </p>
        )}
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          These states are conceptual; the system never labels real historical data as a confirmed
          heatwave. Controlled or replay demonstrations are labelled as such.
        </p>
      </div>
    </section>
  );
}

function MapLab({
  stations,
  selectedStation,
  stationsLoading,
  stationsError,
  stationCount,
  onSelectStation,
}: {
  stations: (MergedStation & { live?: LiveReading })[];
  selectedStation: (MergedStation & { live?: LiveReading }) | null;
  stationsLoading: boolean;
  stationsError: string | null;
  stationCount: number | null;
  onSelectStation: (stationId: string) => void;
}) {
  return (
    <section
      className="map-hero relative h-full min-h-[360px] overflow-visible xl:min-h-[430px]"
      aria-label="India weather station network"
    >
      <div className="absolute right-1 top-1 z-20 flex w-[190px] items-center gap-2.5 rounded-[10px] border border-border bg-card/80 px-3 py-2.5 backdrop-blur-sm">
        <Radio className="size-5 shrink-0 text-[#20D7F5]" strokeWidth={1.8} />
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase leading-tight tracking-[0.08em] text-muted-foreground">
            Historical network
          </p>
          <p className="text-[15px] font-semibold leading-tight text-foreground">
            {stationCount === null ? "…" : `${stationCount} stations`}
          </p>
        </div>
      </div>

      {stationsError && (
        <div className="absolute left-1 top-1 z-20 max-w-[280px]" role="alert">
          <p className="text-[10px] font-extrabold text-offline-deep">Station feed unavailable</p>
          <p className="text-[9px] text-muted-foreground">{stationsError}</p>
        </div>
      )}
      {stationsLoading && (
        <div className="absolute left-1 top-1 z-20" role="status">
          <p className="text-[9px] font-semibold text-muted-foreground">Loading station feed…</p>
        </div>
      )}

      <div className="map-stage absolute inset-0 flex items-center justify-center">
        <div className="map-world relative">
          <img
            src={indiaAsset.url}
            alt="Soft 3D map of India with weather stations, terrain, clouds and environmental landmarks"
            className="h-full w-full object-contain"
          />
          {stations.map((station) => (
            <Button
              key={station.id}
              variant="mapPin"
              size="icon"
              aria-label={`Select ${station.city} station`}
              title={`${station.city} · ${station.id}`}
              onClick={() => onSelectStation(station.id)}
              data-status={station.status}
              data-capability={stationMapCapability(station.api)}
              data-selected={selectedStation?.id === station.id ? "true" : "false"}
              className="station-hotspot absolute z-10"
              style={{ left: `${station.x}%`, top: `${station.y}%` }}
            >
              <span className="sr-only">{station.city}</span>
              <span className="station-name">{station.city}</span>
            </Button>
          ))}
        </div>
      </div>
    </section>
  );
}

/** Min/max/count over the non-null points of a sensor series. */
function extent(values: Array<{ index: number; value: number | null }>) {
  const numbers = values
    .map((entry) => entry.value)
    .filter((value): value is number => value !== null);
  return {
    count: numbers.length,
    min: numbers.length > 0 ? Math.min(...numbers) : null,
    max: numbers.length > 0 ? Math.max(...numbers) : null,
  };
}

/**
 * Compact analytical sensor card: current value, 24-hour direction, the real
 * recorded trend as a sparkline (gaps preserved) and the measured 24-hour
 * range. Everything is rendered from the station's own observations; a range
 * that cannot be measured says so instead of being invented.
 */
function SensorCard({
  title,
  icon: Icon,
  iconTone,
  color,
  value,
  delta,
  deltaTone,
  range,
  series,
  sparkId,
  emptyMessage,
}: {
  title: string;
  icon: typeof Thermometer;
  iconTone: string;
  color: string;
  value: string;
  delta: string;
  deltaTone: string;
  range: string;
  series: Array<{ index: number; value: number | null }>;
  /** Slug used for the SVG gradient id — spaces would break the paint ref. */
  sparkId: string;
  emptyMessage: string;
}) {
  return (
    <article className="flex min-w-0 flex-col rounded-lg border border-border bg-muted/40 p-3">
      <div className="flex items-center gap-1.5">
        <Icon className={cn("size-3.5 shrink-0", iconTone)} strokeWidth={1.8} />
        <p className="truncate text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          {title}
        </p>
        <span className={cn("ml-auto shrink-0 text-[11px] font-bold tabular-nums", deltaTone)}>
          {delta}
        </span>
      </div>
      <p className="mt-1.5 text-[20px] font-semibold leading-none tabular-nums tracking-tight">
        {value}
      </p>
      <div className="mt-2 h-[34px] min-h-0">
        {series.length > 0 ? (
          <SensorSpark values={series} color={color} gradientId={`overview-spark-${sparkId}`} />
        ) : (
          <p className="flex h-full items-center text-[10px] text-muted-foreground">
            {emptyMessage}
          </p>
        )}
      </div>
      <p className="mt-1.5 text-[10px] leading-snug text-muted-foreground">{range}</p>
    </article>
  );
}

function SelectedStationIntelligence({
  station,
  detail,
  loading,
  error,
  liveReading,
  liveSeries,
  liveActive,
  stationCount,
}: {
  station: (MergedStation & { live?: LiveReading }) | null;
  detail: StationDetailResponse | undefined;
  loading: boolean;
  error: string | null;
  liveReading: LiveReading | null;
  liveSeries: Record<HistoryVariable, Array<{ index: number; value: number | null }>>;
  liveActive: boolean;
  stationCount: number | null;
}) {
  const api = station?.api;
  const capability = stationMapCapability(api);
  const measurements = detail?.observations;
  const detected = detail?.anomaly?.detected === true;
  const hasVerdict = detail?.data_quality?.ml_eligible === true;
  // Coverage = a detector can produce a verdict (frozen ensemble OR a
  // calibrated station detector). PARTIAL is partial variable coverage, not
  // "no detector".
  const detectorCovered = hasDetectorCoverage(api);
  const dataAvailable = api?.data_available === true;
  const stationId = station?.id ?? null;

  // 24-hour recorded history per variable (real observations, gaps kept).
  const temperature = useSensorSeries(dataAvailable ? stationId : null, "temperature");
  const pressure = useSensorSeries(dataAvailable ? stationId : null, "pressure");
  const humidity = useSensorSeries(dataAvailable ? stationId : null, "humidity");

  const sourceLabel =
    api?.source_dataset === "delhi_clean"
      ? "Historical AWS"
      : api?.source_dataset === "noaa_ghcnh"
        ? "Historical GHCNh"
        : "Historical observations";
  const capabilityLabel =
    capability === "full-tpr"
      ? "Full T/P/RH detection"
      : capability === "partial"
        ? "Partial detection"
        : api?.data_available === false
          ? "Data unavailable"
          : "Context only — no verdict";
  const detectorDot =
    capability === "partial"
      ? "bg-[#F4B400]"
      : capability === "full-tpr"
        ? "bg-sky"
        : "bg-muted-foreground";
  const detectorTone =
    capability === "partial"
      ? "text-[#F4C343]"
      : capability === "full-tpr"
        ? "text-foreground"
        : "text-muted-foreground";

  const live = liveActive && liveReading !== null;
  const sensors: Array<{
    title: string;
    icon: typeof Thermometer;
    iconTone: string;
    color: string;
    unit: string;
    digits: number;
    format: (value: number) => string;
    stats: ReturnType<typeof useSensorSeries>;
    fallback: number | null;
    liveValues: Array<{ index: number; value: number | null }>;
    liveLatest: number | null;
  }> = [
    {
      title: "Temperature",
      icon: Thermometer,
      iconTone: "text-[#20D7F5]",
      color: "var(--chart-context)",
      unit: "°C",
      digits: 1,
      format: (value) => formatTemp(value),
      stats: temperature,
      fallback: measurements?.temperature_c ?? api?.temperature ?? null,
      liveValues: liveSeries.temperature,
      liveLatest: live ? (liveReading?.observations.temperature_c ?? null) : null,
    },
    {
      title: "Pressure",
      icon: Gauge,
      iconTone: "text-sky",
      color: "var(--chart-blue)",
      unit: "hPa",
      digits: 1,
      format: (value) => formatPressure(value),
      stats: pressure,
      fallback: measurements?.pressure_hpa ?? api?.pressure ?? null,
      liveValues: liveSeries.pressure,
      liveLatest: live ? (liveReading?.observations.pressure_hpa ?? null) : null,
    },
    {
      title: "Relative humidity",
      icon: Droplets,
      iconTone: "text-[#20D7F5]",
      color: "var(--chart-green)",
      unit: "%",
      digits: 0,
      format: (value) => formatHumidity(value),
      stats: humidity,
      fallback: measurements?.relative_humidity_pct ?? api?.humidity ?? null,
      liveValues: liveSeries.humidity,
      liveLatest: live ? (liveReading?.observations.relative_humidity_pct ?? null) : null,
    },
  ];

  return (
    <section className="panel mt-3 shrink-0 p-4" aria-label="Selected station">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="section-kicker">{station ? "Selected station" : "Network overview"}</p>
          <h2 className="mt-1 text-lg font-extrabold leading-tight">
            {station ? `${station.id} · ${station.city}` : "Pick a station on the network map"}
          </h2>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {station
              ? `${sourceLabel} · ${formatDisplayTerm(api?.data_mode ?? "historical_replay")}`
              : `${stationCount === null ? "…" : stationCount} Indian stations with real historical observations — select any marker to inspect its current readings and 24-hour trend.`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {station &&
            (loading ? (
              <span className="text-[11px] text-muted-foreground">Loading detector state…</span>
            ) : error || !detail ? (
              <span className="rounded-full border border-border px-3 py-1.5 text-[11px] text-muted-foreground">
                Detector verdict unavailable
              </span>
            ) : detected ? (
              <span className="flex items-center gap-2 rounded-full border border-anomaly/30 bg-anomaly-soft px-3 py-1.5 text-[11px] font-medium text-anomaly-deep">
                <span className="size-[7px] rounded-full bg-anomaly" />
                Anomaly detected
              </span>
            ) : hasVerdict ? (
              <span className="flex items-center gap-2 rounded-full border border-success/20 bg-success-soft px-3 py-1.5 text-[11px] font-medium text-success-deep">
                <span className="size-[7px] rounded-full bg-success" />
                No active anomaly
              </span>
            ) : (
              <span className="rounded-full border border-border px-3 py-1.5 text-[11px] text-muted-foreground">
                Detector verdict unavailable
              </span>
            ))}
          {station && (
            <Button
              asChild
              variant="outline"
              className="h-8 rounded-lg border-border bg-transparent px-3 text-[12px] text-foreground"
            >
              <Link to="/stations/$stationId" params={{ stationId: station.id }}>
                Investigate station
                <ArrowRight className="size-3.5 text-[#20D7F5]" />
              </Link>
            </Button>
          )}
        </div>
      </div>

      {station ? (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {sensors.map((sensor) => {
            const liveValues = sensor.liveValues.length > 0 ? sensor.liveValues : null;
            const values = liveValues ?? sensor.stats.values;
            const measured = extent(values);
            const firstRecorded = values.find((entry) => entry.value !== null)?.value ?? null;
            // While a replay is streaming, the card follows the stream; in
            // historical mode it follows the real 24-hour recorded window.
            const liveDelta =
              sensor.liveLatest !== null && firstRecorded !== null
                ? sensor.liveLatest - firstRecorded
                : null;
            const deltaValue = sensor.liveLatest !== null ? liveDelta : sensor.stats.delta;
            const hasRange = measured.count > 1 && measured.min !== null && measured.max !== null;
            const displayValue = !dataAvailable
              ? "—"
              : sensor.liveLatest !== null
                ? sensor.format(sensor.liveLatest)
                : sensor.stats.loading && sensor.stats.latest === null
                  ? "…"
                  : sensor.stats.latest !== null
                    ? sensor.format(sensor.stats.latest)
                    : sensor.fallback !== null
                      ? sensor.format(sensor.fallback)
                      : "—";
            const displayDelta =
              !dataAvailable || deltaValue === null
                ? "—"
                : `${deltaValue >= 0 ? "↑" : "↓"} ${Math.abs(deltaValue).toFixed(sensor.digits)}${sensor.unit === "hPa" ? " hPa" : sensor.unit}`;
            const rangeLabel = !dataAvailable
              ? "Station data unavailable — no readings are invented."
              : !hasRange
                ? "Historical range unavailable."
                : `${liveValues ? "Replay window" : "Last 24 h"} · ${(measured.min ?? 0).toFixed(sensor.digits)}–${(measured.max ?? 0).toFixed(sensor.digits)} ${sensor.unit}`;
            return (
              <SensorCard
                key={sensor.title}
                title={sensor.title}
                icon={sensor.icon}
                iconTone={sensor.iconTone}
                color={sensor.color}
                value={displayValue}
                delta={displayDelta}
                deltaTone={
                  !dataAvailable || deltaValue === null
                    ? "text-muted-foreground"
                    : Math.abs(deltaValue) < 0.05
                      ? "text-muted-foreground"
                      : Math.abs(deltaValue) >= 2
                        ? "text-anomaly-deep"
                        : "text-warning-deep"
                }
                range={rangeLabel}
                series={values}
                sparkId={sensor.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}
                emptyMessage={
                  !dataAvailable
                    ? "No readings served for this station."
                    : sensor.stats.loading
                      ? "Loading history…"
                      : "No history available."
                }
              />
            );
          })}
          <article className="flex min-w-0 flex-col rounded-lg border border-border bg-muted/40 p-3">
            <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
              Detector
            </p>
            <p
              className={cn(
                "mt-1.5 flex items-center gap-2 text-[14px] font-semibold",
                detectorTone,
              )}
            >
              <span className={cn("size-2 shrink-0 rounded-full", detectorDot)} />
              {capabilityLabel}
            </p>
            <p className="mt-1 text-[10px] leading-snug text-muted-foreground">
              {loading
                ? "Loading detector state…"
                : error
                  ? "Detector status unavailable"
                  : detected
                    ? "Anomaly detected at the latest observation."
                    : !detectorCovered
                      ? "No detector covers this station — observations are context only."
                      : capability === "full-tpr"
                        ? "Frozen ensemble · no active anomaly."
                        : "Calibrated station detector · verdicts are produced during historical replay."}
            </p>
            {station && (
              <p className="mt-auto pt-1 text-[10px] text-muted-foreground">
                Full record, detector events and evidence live on the station page.
              </p>
            )}
          </article>
        </div>
      ) : (
        <p className="mt-3 border-t border-border pt-2 text-[11px] text-muted-foreground">
          Nothing is preselected, so no station is presented as the default. Select a marker to load
          that station's live readings, 24-hour trend and detector state.
        </p>
      )}
    </section>
  );
}

function useSensorSeries(stationId: string | null, variable: HistoryVariable) {
  const query = useStationHistory(stationId, variable, 24);
  return useMemo(() => {
    const points = query.data?.points ?? [];
    const values = points.map((point, index) => ({ index, value: point[variable] ?? null }));
    const nonNull = values.filter(
      (entry): entry is { index: number; value: number } => entry.value !== null,
    );
    const latest = nonNull.length > 0 ? (nonNull[nonNull.length - 1]?.value ?? null) : null;
    const first = nonNull.length > 0 ? (nonNull[0]?.value ?? null) : null;
    const delta = latest !== null && first !== null && nonNull.length > 1 ? latest - first : null;
    return {
      values,
      latest,
      delta,
      loading: query.isPending,
      error: query.isError ? errorMessage(query.error) : null,
    };
  }, [query.data, query.isPending, query.isError, query.error, variable]);
}
