import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { type ReactNode, useEffect, useMemo, useState } from "react";
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
import { StatusBadge, FactRow } from "@/components/common";
import { SensorSpark } from "@/components/charts";
import { ReplayStage } from "@/components/replay/ReplayStage";
import { useReplaySession } from "@/components/replay/ReplaySessionContext";
import type { LiveReading } from "@/lib/live";
import {
  hasDetectorCoverage,
  normalizeStatus,
  type AlertSummary,
  type StationDetailResponse,
} from "@/lib/api";
import {
  errorMessage,
  formatCompactCount,
  formatDisplayTerm,
  formatHumidity,
  formatPressure,
  formatScore,
  formatTemp,
  formatTime,
} from "@/lib/format";
import {
  mergeStations,
  stationMapCapability,
  stationMapMeta,
  type MergedStation,
} from "@/lib/mapMeta";
import {
  useAlerts,
  useNetworkSummary,
  useStation,
  useStationHistory,
  useStations,
} from "@/hooks/useSkyguard";
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
  const [selectedStationId, setSelectedStationId] = useState<string | null>("DEL-01");
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);

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
  const alertsQuery = useAlerts(1000);

  const mergedStations = useMemo(
    () => mergeStations(stationsQuery.data?.stations ?? []),
    [stationsQuery.data],
  );

  const alerts = useMemo(() => alertsQuery.data?.alerts ?? [], [alertsQuery.data]);
  const recentAlerts = useMemo(() => alerts.slice(0, 50), [alerts]);

  const liveSummaries = useMemo<AlertSummary[]>(
    () =>
      live.liveAlerts.map((alert) => ({
        alert_id: alert.alert_id,
        station_id: alert.station_id,
        timestamp: alert.timestamp,
        status: alert.status,
        event: alert.event,
        anomaly_score: alert.score,
        root_cause: alert.root_cause,
        root_cause_confidence: alert.confidence,
        summary: alert.summary,
      })),
    [live.liveAlerts],
  );
  const liveIds = useMemo(
    () => new Set(liveSummaries.map((alert) => alert.alert_id)),
    [liveSummaries],
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

  useEffect(() => {
    if (selectedAlertId === null && alerts.length > 0) {
      const first = alerts[0];
      if (first) setSelectedAlertId(first.alert_id);
    }
  }, [alerts, selectedAlertId]);

  // Station detail is only requested for stations that actually have backend
  // data; offline/unmapped stations (AMD-06, HYD-07) render an unavailable
  // state instead of erroring against a 404.
  const detailStationId = selectedStation?.api?.data_available === true ? selectedStation.id : null;
  const stationDetailQuery = useStation(detailStationId);

  const selectStation = (stationId: string) => {
    setSelectedStationId(stationId);
    const match = alerts.find((alert) => alert.station_id === stationId);
    if (match) setSelectedAlertId(match.alert_id);
  };

  const selectAlert = (alert: AlertSummary, isLive: boolean) => {
    if (isLive) {
      // Dedicated replay investigation route backed by the exact stored
      // streamed payload — never the persistent REST store.
      navigate({
        to: "/investigations/replay/$anomalyId",
        params: { anomalyId: alert.alert_id },
      });
      return;
    }
    setSelectedAlertId(alert.alert_id);
    if (stationMapMeta.some((meta) => meta.id === alert.station_id)) {
      setSelectedStationId(alert.station_id);
    }
  };

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

      <SelectedStationIntelligence
        station={selectedStation}
        detail={stationDetailQuery.data}
        loading={stationDetailQuery.isPending && detailStationId !== null}
        error={stationDetailQuery.isError ? errorMessage(stationDetailQuery.error) : null}
      />

      <BottomInsights
        stationId={detailStationId}
        stationLabel={selectedStation ? `${selectedStation.id} · ${selectedStation.city}` : null}
        dataAvailable={selectedStation?.api?.data_available === true}
        liveReading={selectedLive}
        liveSeries={liveSeries}
        liveActive={liveActive}
      />

      <HowSkyGuardDecides />
      <WhatSkyGuardDetects />
      <RealWeatherOrFault
        spatial={spatial}
        stationLabel={selectedStation ? `${selectedStation.id} · ${selectedStation.city}` : null}
      />

      <ReplayStage live={live} stations={replayStations} />

      <RecentAlerts
        alerts={recentAlerts}
        liveAlerts={liveSummaries}
        liveIds={liveIds}
        selectedAlertId={selectedAlertId}
        onSelectAlert={selectAlert}
        loading={alertsQuery.isPending}
        error={alertsQuery.isError ? errorMessage(alertsQuery.error) : null}
      />
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

function SpatialContextCard({
  station,
  spatial,
}: {
  station: (MergedStation & { live?: LiveReading }) | null;
  spatial: StationDetailResponse["spatial_context"] | null;
}) {
  const level = (spatial?.context_level ?? "UNAVAILABLE").toUpperCase();
  // The backend can report available=true with an UNAVAILABLE level when the
  // station has no compatible neighbours; that must not read as evidence.
  const available = spatial?.available === true && level !== "UNAVAILABLE";
  const interpretation = !available
    ? "SPATIAL CONTEXT UNAVAILABLE"
    : (spatial?.context_level ?? "UNAVAILABLE");
  const label = !available
    ? "Spatial context unavailable for this station — no neighbour values are invented."
    : interpretation.toUpperCase().includes("REGIONAL")
      ? "Compatible neighbouring stations behave similarly → possible regional event."
      : "Target differs from compatible nearby stations → local sensor anomaly.";
  return (
    <aside className="panel min-h-0 p-3.5" aria-label="Spatial context">
      <div className="flex items-center justify-between gap-2">
        <p className="section-kicker">Spatial context</p>
        <Network className="size-4 text-sky" />
      </div>
      <h2 className="mt-0.5 text-sm font-extrabold">
        {station ? `${station.id} · ${station.city}` : "No station selected"}
      </h2>
      <p
        className={cn(
          "mt-1.5 rounded-lg px-2 py-1 text-[10px] font-extrabold",
          available ? "bg-info-soft text-info" : "bg-warning-soft text-warning-deep",
        )}
        role="status"
      >
        {interpretation}
      </p>
      <p className="mt-1.5 text-[10px] leading-snug text-muted-foreground">{label}</p>
      {available && (
        <div className="mt-1.5 divide-y divide-border border-t border-border pt-1">
          <FactRow label="Compatible neighbours" value={String(spatial?.neighbor_count ?? 0)} />
          <FactRow label="Phase-22 context level" value={interpretation} />
        </div>
      )}
      <p className="mt-1.5 text-[9px] leading-snug text-muted-foreground">
        Uses the existing Phase-22 spatial decision. Thresholds and policy are unchanged.
      </p>
    </aside>
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

function SelectedStationIntelligence({
  station,
  detail,
  loading,
  error,
}: {
  station: (MergedStation & { live?: LiveReading }) | null;
  detail: StationDetailResponse | undefined;
  loading: boolean;
  error: string | null;
}) {
  const api = station?.api;
  const capability = stationMapCapability(api);
  const measurements = detail?.observations;
  const detected = detail?.anomaly?.detected === true;
  const sourceLabel =
    api?.source_dataset === "delhi_clean"
      ? "Historical AWS"
      : api?.source_dataset === "noaa_ghcnh"
        ? "Historical GHCNh"
        : "Historical observations";
  const capabilityLabel =
    capability === "full-tpr"
      ? "Full T/P/RH Detection"
      : capability === "partial"
        ? "Partial detection"
        : api?.data_available === false
          ? "Data Unavailable"
          : "Context Only";
  // Coverage = a detector can produce a verdict (frozen ensemble OR a
  // calibrated station detector). PARTIAL is partial variable coverage, not
  // "no detector".
  const detectorCovered = hasDetectorCoverage(api);
  const noVerdict = !detectorCovered;

  const hasVerdict = detail?.data_quality?.ml_eligible === true;
  const variables = [
    measurements?.temperature_c ?? api?.temperature,
    measurements?.pressure_hpa ?? api?.pressure,
    measurements?.relative_humidity_pct ?? api?.humidity,
  ];
  const variableLabels = ["T", "P", "RH"].filter((_, index) => variables[index] != null);
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
  return (
    <section
      className="mt-4 rounded-xl border border-border bg-card p-6"
      aria-label="Selected station intelligence"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            Selected station
          </p>
          <h2 className="mt-1 text-[24px] font-semibold leading-tight tracking-tight text-foreground">
            {station ? `${station.id} · ${station.city}` : "Select a station on the map"}
          </h2>
          {station && (
            <p className="mt-1 text-[12px] text-muted-foreground">
              {sourceLabel} · {formatDisplayTerm(api?.data_mode ?? "historical_replay")}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {station &&
            (loading ? (
              <span className="text-[12px] text-muted-foreground">Loading detector state…</span>
            ) : error || !detail ? (
              <span className="rounded-full border border-border px-3 py-1.5 text-[12px] text-muted-foreground">
                Detector verdict unavailable
              </span>
            ) : detected ? (
              <span className="flex items-center gap-2 rounded-full border border-anomaly/30 bg-anomaly-soft px-3 py-1.5 text-[12px] font-medium text-anomaly-deep">
                <span className="size-[7px] rounded-full bg-anomaly" />
                Anomaly Detected
              </span>
            ) : hasVerdict ? (
              <span className="flex items-center gap-2 rounded-full border border-success/20 bg-success-soft px-3 py-1.5 text-[12px] font-medium text-success-deep">
                <span className="size-[7px] rounded-full bg-success" />
                No Active Anomaly
              </span>
            ) : (
              <span className="rounded-full border border-border px-3 py-1.5 text-[12px] text-muted-foreground">
                Detector verdict unavailable
              </span>
            ))}
          {station && (
            <Button
              asChild
              variant="outline"
              className="h-[38px] rounded-lg border-border bg-transparent px-4 text-[13px] text-foreground"
            >
              <Link to="/stations/$stationId" params={{ stationId: station.id }}>
                Investigate
                <ArrowRight className="size-4 text-[#20D7F5]" />
              </Link>
            </Button>
          )}
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_200px]">
        <div className="grid min-w-0 grid-cols-2 gap-4 lg:grid-cols-4">
          <div className="min-h-[116px] rounded-[9px] border border-border bg-muted/40 p-[18px]">
            <div className="flex items-center gap-2">
              <Thermometer className="size-4 text-[#20D7F5]" strokeWidth={1.8} />
              <p className="text-[12px] text-muted-foreground">Temperature</p>
            </div>
            <p className="mt-2 text-[22px] font-semibold tabular-nums text-foreground">
              {formatTemp(measurements?.temperature_c ?? api?.temperature)}
            </p>
            {detected && (
              <p className="mt-1 text-[10px] font-bold uppercase tracking-[0.08em] text-anomaly">
                Anomalous
              </p>
            )}
          </div>
          <div className="min-h-[116px] rounded-[9px] border border-border bg-muted/40 p-[18px]">
            <div className="flex items-center gap-2">
              <Gauge className="size-4 text-sky" strokeWidth={1.8} />
              <p className="text-[12px] text-muted-foreground">Pressure</p>
            </div>
            <p className="mt-2 text-[22px] font-semibold tabular-nums text-foreground">
              {formatPressure(measurements?.pressure_hpa ?? api?.pressure)}
            </p>
          </div>
          <div className="min-h-[116px] rounded-[9px] border border-border bg-muted/40 p-[18px]">
            <div className="flex items-center gap-2">
              <Droplets className="size-4 text-[#20D7F5]" strokeWidth={1.8} />
              <p className="text-[12px] text-muted-foreground">Humidity</p>
            </div>
            <p className="mt-2 text-[22px] font-semibold tabular-nums text-foreground">
              {formatHumidity(measurements?.relative_humidity_pct ?? api?.humidity)}
            </p>
          </div>
          <div className="min-h-[116px] rounded-[9px] border border-border bg-muted/40 p-[18px]">
            <p className="text-[12px] text-muted-foreground">Detector</p>
            <p className={cn("mt-2 flex items-center gap-2 text-[14px] font-medium", detectorTone)}>
              <span className={cn("size-2 shrink-0 rounded-full", detectorDot)} />
              {capabilityLabel}
            </p>
            <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
              {loading
                ? "Loading detector state…"
                : error
                  ? "Detector status unavailable"
                  : detected
                    ? "Anomalous"
                    : noVerdict
                      ? "No detector verdict available for this station."
                      : capability === "full-tpr"
                        ? "No active anomaly."
                        : "Calibrated station detector · verdicts are produced during historical replay."}
            </p>
          </div>
        </div>
        <dl className="grid min-w-0 grid-cols-2 gap-x-4 gap-y-2 content-start xl:grid-cols-1 xl:gap-y-1.5">
          {[
            ["State", station?.city ?? "—"],
            ["Data source", "Historical"],
            ["Variables", variableLabels.length > 0 ? variableLabels.join(" · ") : "Unavailable"],
            ["Observations", api?.data_available === true ? "Available" : "Unavailable"],
            ["Coverage", "Historical period"],
            ["Mode", formatDisplayTerm(api?.data_mode ?? "historical_replay")],
          ].map(([term, value]) => (
            <div key={term}>
              <dt className="text-[11px] text-muted-foreground">{term}</dt>
              <dd className="text-[12px] text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function RecentAlerts({
  alerts,
  liveAlerts,
  liveIds,
  selectedAlertId,
  onSelectAlert,
  loading,
  error,
}: {
  alerts: AlertSummary[];
  liveAlerts: AlertSummary[];
  liveIds: Set<string>;
  selectedAlertId: string | null;
  onSelectAlert: (alert: AlertSummary, isLive: boolean) => void;
  loading: boolean;
  error: string | null;
}) {
  const navigate = useNavigate();
  const openAlert = (alert: AlertSummary) => {
    const isLive = liveIds.has(alert.alert_id);
    onSelectAlert(alert, isLive);
    if (!isLive) {
      navigate({ to: "/alerts/$alertId", params: { alertId: alert.alert_id } });
    }
  };
  const rows = [...liveAlerts, ...alerts];
  return (
    <section className="panel shrink-0 p-4" aria-label="Recent alerts">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="section-kicker">Recent activity · Historical and replay alerts</p>
          <h2 className="mt-1 text-lg font-extrabold">Recent Alerts</h2>
        </div>
        <span className="flex size-8 items-center justify-center rounded-xl bg-anomaly-soft text-anomaly">
          <Bell className="size-4" />
        </span>
      </div>
      {loading && (
        <p className="mt-3 text-[10px] text-muted-foreground" role="status">
          Loading alerts…
        </p>
      )}
      {error && (
        <p
          className="mt-3 rounded-xl border border-offline/30 bg-offline-soft px-3 py-2 text-[10px] font-semibold text-offline-deep"
          role="alert"
        >
          Alerts unavailable: {error}
        </p>
      )}
      {!loading && !error && rows.length === 0 && (
        <p className="mt-3 text-[10px] text-muted-foreground" role="status">
          No alerts in the current window.
        </p>
      )}
      {!loading && !error && rows.length > 0 && (
        <>
          <div
            className="mt-3 grid grid-cols-[88px_minmax(0,1fr)_104px_128px_60px] gap-2 px-2.5 text-[9px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground"
            aria-hidden="true"
          >
            <span>Station</span>
            <span>Event</span>
            <span>Reading</span>
            <span>Status</span>
            <span className="text-right">Time</span>
          </div>
          <div className="mt-1.5 space-y-1.5">
            {rows.map((alert) => {
              const selected = selectedAlertId === alert.alert_id;
              const status = normalizeStatus(alert.status, true);
              const isLive = liveIds.has(alert.alert_id);
              return (
                <div
                  key={alert.alert_id}
                  role="link"
                  tabIndex={0}
                  aria-label={`Open alert ${alert.event} at ${alert.station_id}`}
                  onClick={() => openAlert(alert)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openAlert(alert);
                    }
                  }}
                  className={cn(
                    "grid w-full cursor-pointer grid-cols-[88px_minmax(0,1fr)_104px_128px_60px] items-center gap-2 rounded-xl border px-2.5 py-2 text-left transition-colors",
                    selected
                      ? "border-primary/50 bg-info-soft"
                      : "border-border bg-card hover:border-primary/30 hover:bg-info-soft/50",
                  )}
                >
                  <strong className="text-[11px] font-extrabold">
                    {alert.station_id}
                    {isLive && (
                      <span className="ml-1 rounded bg-success-soft px-1 text-[8px] font-extrabold text-success-deep">
                        REPLAY
                      </span>
                    )}
                  </strong>
                  <span className="truncate text-[11px] font-semibold text-muted-foreground">
                    {alert.event}
                  </span>
                  <strong
                    className="text-xs font-extrabold"
                    title="Anomaly score — open the investigation for observed readings"
                  >
                    {formatScore(alert.anomaly_score)}
                  </strong>
                  <span>
                    <StatusBadge status={status} />
                  </span>
                  <time className="text-right text-[10px] font-medium text-muted-foreground">
                    {formatTime(alert.timestamp)}
                  </time>
                </div>
              );
            })}
          </div>
        </>
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

function BottomInsights({
  stationId,
  stationLabel,
  dataAvailable,
  liveReading,
  liveSeries,
  liveActive,
}: {
  stationId: string | null;
  stationLabel: string | null;
  dataAvailable: boolean;
  liveReading: LiveReading | null;
  liveSeries: Record<HistoryVariable, Array<{ index: number; value: number | null }>>;
  liveActive: boolean;
}) {
  const temperature = useSensorSeries(dataAvailable ? stationId : null, "temperature");
  const pressure = useSensorSeries(dataAvailable ? stationId : null, "pressure");
  const humidity = useSensorSeries(dataAvailable ? stationId : null, "humidity");

  const liveByKey: Record<
    string,
    { latest: number | null; values: Array<{ index: number; value: number | null }> }
  > = {
    Temperature: {
      latest: liveReading?.observations.temperature_c ?? null,
      values: liveSeries.temperature,
    },
    Pressure: {
      latest: liveReading?.observations.pressure_hpa ?? null,
      values: liveSeries.pressure,
    },
    Humidity: {
      latest: liveReading?.observations.relative_humidity_pct ?? null,
      values: liveSeries.humidity,
    },
  };

  const sensorCards = [
    {
      title: "Temperature",
      series: temperature,
      formatValue: (v: number) => `${v.toFixed(1)}°C`,
      formatDelta: (d: number) => `${d >= 0 ? "↑" : "↓"} ${Math.abs(d).toFixed(1)}°C`,
      icon: Thermometer,
      color: "var(--chart-context)",
      tone: "bg-muted text-muted-foreground",
    },
    {
      title: "Pressure",
      series: pressure,
      formatValue: (v: number) => `${v.toFixed(1)} hPa`,
      formatDelta: (d: number) => `${d >= 0 ? "↑" : "↓"} ${Math.abs(d).toFixed(1)} hPa`,
      icon: Gauge,
      color: "var(--chart-blue)",
      tone: "bg-info-soft text-info",
    },
    {
      title: "Humidity",
      series: humidity,
      formatValue: (v: number) => `${v.toFixed(0)}%`,
      formatDelta: (d: number) => `${d >= 0 ? "↑" : "↓"} ${Math.abs(d).toFixed(1)}%`,
      icon: Droplets,
      color: "var(--chart-green)",
      tone: "bg-success-soft text-success",
    },
  ];

  return (
    <section
      className="grid h-[154px] shrink-0 grid-cols-[minmax(0,1.2fr)_minmax(330px,.8fr)] gap-3"
      aria-label="Sensor and activity insights"
    >
      <div className="grid grid-cols-3 gap-2.5">
        {sensorCards.map((sensor) => {
          const unavailable = !dataAvailable || stationId === null;
          const live = liveActive && liveReading ? liveByKey[sensor.title] : null;
          const liveValues = live && live.values.length > 0 ? live.values : null;
          const values = liveValues ?? sensor.series.values;
          const nonNull = values.filter(
            (entry): entry is { index: number; value: number } => entry.value !== null,
          );
          const liveLatest = live?.latest ?? null;
          const first = nonNull.length > 0 ? (nonNull[0]?.value ?? null) : null;
          const last = nonNull.length > 0 ? (nonNull[nonNull.length - 1]?.value ?? null) : null;
          const liveDelta =
            liveLatest !== null && first !== null && nonNull.length > 1 ? liveLatest - first : null;
          const displayValue = unavailable
            ? "—"
            : liveLatest !== null
              ? sensor.formatValue(liveLatest)
              : sensor.series.loading
                ? "…"
                : sensor.series.latest !== null
                  ? sensor.formatValue(sensor.series.latest)
                  : "—";
          const displayDelta =
            unavailable || (liveLatest !== null ? liveDelta === null : sensor.series.delta === null)
              ? "—"
              : sensor.formatDelta((liveLatest !== null ? liveDelta : sensor.series.delta) ?? 0);
          return (
            <article
              key={sensor.title}
              className="panel flex min-w-0 flex-col p-3"
              title={stationLabel ? `24-hour history for ${stationLabel}` : undefined}
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn("flex size-8 items-center justify-center rounded-xl", sensor.tone)}
                >
                  <sensor.icon className="size-4" />
                </span>
                <div>
                  <p className="text-[9px] font-semibold text-muted-foreground">{sensor.title}</p>
                  <p className="text-sm font-extrabold">{displayValue}</p>
                </div>
                <span className="ml-auto text-[9px] font-bold text-success-deep">
                  {displayDelta}
                </span>
              </div>
              <div className="mt-1 min-h-0 flex-1">
                {!unavailable && values.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <SensorSpark
                      values={values}
                      color={sensor.color}
                      gradientId={`fill-${sensor.title}`}
                    />
                  </ResponsiveContainer>
                ) : (
                  <p className="flex h-full items-center justify-center text-[9px] text-muted-foreground">
                    {unavailable
                      ? "Station unavailable."
                      : sensor.series.loading && liveLatest === null
                        ? "Loading history…"
                        : "No history available."}
                  </p>
                )}
              </div>
            </article>
          );
        })}
      </div>
      <article className="panel flex min-w-0 flex-col p-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-extrabold">Network Activity</p>
            <p className="text-[9px] text-muted-foreground">Reports processed over 24 hours</p>
          </div>
        </div>
        <div className="mt-1 flex min-h-0 flex-1 items-center justify-center">
          <p className="px-4 text-center text-[9px] leading-snug text-muted-foreground">
            Activity feed is not provided by the API in historical replay — no data fabricated.
          </p>
        </div>
      </article>
    </section>
  );
}
