import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Bell, CloudSun, Droplets, Eye, Gauge, Thermometer } from "lucide-react";
import { ResponsiveContainer } from "recharts";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { StatusBadge, DetailStat, FactRow } from "@/components/common";
import { HistoryChart, SensorSpark, toChartPoints } from "@/components/charts";
import { EvidenceList, ExplanationBlock, OutcomeBanner } from "@/components/evidence";
import { KpiRow } from "@/components/kpi";
import { ReplayControls } from "@/components/replay/ReplayControls";
import { LiveEventFeed } from "@/components/replay/LiveEventFeed";
import { useLiveReplay } from "@/hooks/useLiveReplay";
import type { LiveAlert, LiveReading } from "@/lib/live";
import {
  normalizeStatus,
  type AlertDetailResponse,
  type AlertSummary,
  type StationDetailResponse,
} from "@/lib/api";
import type { DisplayStatus } from "@/lib/api";
import {
  errorMessage,
  cleanText,
  formatConfidence,
  formatDateTime,
  formatHumidity,
  formatPressure,
  formatScore,
  formatTemp,
  formatTime,
} from "@/lib/format";
import { mergeStations, stationMapMeta, type MergedStation } from "@/lib/mapMeta";
import {
  useAlert,
  useAlerts,
  useNetworkSummary,
  useStation,
  useStationHistory,
  useStations,
} from "@/hooks/useSkyguard";
import type { HistoryVariable } from "@/lib/api";

const indiaAsset = { url: "/assets/india.png" };

export const Route = createFileRoute("/_app/")({
  head: () => ({
    meta: [
      { title: "Live Overview | SkyGuard AI" },
      {
        name: "description",
        content: "National weather station monitoring and anomaly intelligence from SkyGuard AI.",
      },
      { property: "og:title", content: "SkyGuard AI — Live Overview" },
      {
        property: "og:description",
        content:
          "Historical replay of trusted weather observations across India's station network.",
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
  const [livePreview, setLivePreview] = useState<{
    summary: AlertSummary;
    reading: LiveReading;
  } | null>(null);

  const live = useLiveReplay();
  const liveActive =
    live.replay.status === "running" ||
    live.replay.status === "paused" ||
    live.replay.status === "preparing";

  // A new replay run owns a fresh session: drop the previous streamed preview.
  useEffect(() => {
    setLivePreview(null);
  }, [live.runId]);

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

  // Replay covers the detector-backed pipeline datasets only (DEL-01, JENA-01);
  // the server rejects anything else with a structured error shown in the UI.
  const replayStations = useMemo(() => {
    const delhi = mergedStations.find((station) => station.id === "DEL-01");
    return [
      { id: "DEL-01", city: delhi?.city ?? "New Delhi" },
      { id: "JENA-01", city: "Jena (backend)" },
    ];
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
              : ("offline" as const),
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

  const selectedAlert = useMemo(
    () => alerts.find((alert) => alert.alert_id === selectedAlertId) ?? null,
    [alerts, selectedAlertId],
  );

  // Station detail is only requested for stations that actually have backend
  // data; offline/unmapped stations (AMD-06, HYD-07) render an unavailable
  // state instead of erroring against a 404.
  const detailStationId = selectedStation?.api?.data_available === true ? selectedStation.id : null;
  const stationDetailQuery = useStation(detailStationId);

  const selectStation = (stationId: string) => {
    setSelectedStationId(stationId);
    setLivePreview(null);
    const match = alerts.find((alert) => alert.station_id === stationId);
    if (match) setSelectedAlertId(match.alert_id);
  };

  const selectAlert = (alert: AlertSummary, isLive: boolean) => {
    if (isLive) {
      // Authoritative stored payload from this replay session — never the
      // persistent REST store and never a reconstruction.
      const reading = live.anomalyMap[alert.alert_id];
      if (reading) {
        setLivePreview({ summary: alert, reading });
        return;
      }
      return;
    }
    setLivePreview(null);
    setSelectedAlertId(alert.alert_id);
    if (stationMapMeta.some((meta) => meta.id === alert.station_id)) {
      setSelectedStationId(alert.station_id);
    }
  };

  return (
    <>
      <KpiRow
        summary={networkQuery.data}
        loading={networkQuery.isPending}
        error={networkQuery.isError ? errorMessage(networkQuery.error) : null}
      />
      <section className="panel shrink-0 p-3" aria-label="Live historical replay">
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <ReplayControls live={live} stations={replayStations} />
          <LiveEventFeed readings={live.recentReadings} limit={6} />
        </div>
        <div className="mt-2 border-t border-border pt-2">
          <ReplaySummary
            status={live.replay.status}
            observations={live.summary.observations}
            normal={live.summary.normal}
            anomalies={live.summary.anomalies}
          />
          <ReplayAnomalies
            status={live.replay.status}
            alerts={liveSummaries}
            selectedAlertId={livePreview ? livePreview.summary.alert_id : null}
            onReview={(alert) => selectAlert(alert, true)}
          />
        </div>
      </section>
      <div className="grid min-h-[500px] shrink-0 grid-cols-1 gap-3 xl:h-[520px] xl:min-h-0 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] 2xl:h-[600px]">
        <MapLab
          stations={liveStations}
          selectedStation={selectedStation}
          detail={stationDetailQuery.data}
          detailLoading={stationDetailQuery.isPending && detailStationId !== null}
          detailError={stationDetailQuery.isError}
          stationsLoading={stationsQuery.isPending}
          stationsError={stationsQuery.isError ? errorMessage(stationsQuery.error) : null}
          liveActive={liveActive}
          onSelectStation={selectStation}
        />
        <InvestigationPanel
          alert={livePreview ? null : selectedAlert}
          alertsLoading={alertsQuery.isPending}
          alertsError={alertsQuery.isError ? errorMessage(alertsQuery.error) : null}
          livePreview={livePreview}
          split={live.replay.split}
        />
      </div>
      <RecentAlerts
        alerts={recentAlerts}
        liveAlerts={liveSummaries}
        liveIds={liveIds}
        selectedAlertId={livePreview ? livePreview.summary.alert_id : selectedAlertId}
        onSelectAlert={selectAlert}
        loading={alertsQuery.isPending}
        error={alertsQuery.isError ? errorMessage(alertsQuery.error) : null}
        healthyCount={networkQuery.data?.healthy ?? null}
        networkUpdated={networkQuery.data?.last_updated ?? null}
        networkLoading={networkQuery.isPending}
      />
      <BottomInsights
        stationId={detailStationId}
        stationLabel={selectedStation ? `${selectedStation.id} · ${selectedStation.city}` : null}
        dataAvailable={selectedStation?.api?.data_available === true}
        liveReading={selectedLive}
        liveSeries={liveSeries}
        liveActive={liveActive}
      />
    </>
  );
}

function ReplaySummary({
  status,
  observations,
  normal,
  anomalies,
}: {
  status: string;
  observations: number;
  normal: number;
  anomalies: number;
}) {
  if (status === "idle") return null;
  const cells = [
    { label: "Observations", value: String(observations) },
    { label: "Normal", value: String(normal) },
    { label: "Anomalies", value: String(anomalies) },
  ];
  return (
    <div aria-label="Replay summary">
      <p className="section-kicker">Replay Summary</p>
      <div className="mt-1 grid grid-cols-3 gap-2">
        {cells.map((cell) => (
          <div key={cell.label} className="rounded-xl bg-muted p-2">
            <p className="text-[9px] font-semibold text-muted-foreground">{cell.label}</p>
            <p className="text-base font-extrabold leading-tight tabular-nums">{cell.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReplayAnomalies({
  status,
  alerts,
  selectedAlertId,
  onReview,
}: {
  status: string;
  alerts: AlertSummary[];
  selectedAlertId: string | null;
  onReview: (alert: AlertSummary) => void;
}) {
  return (
    <div className="mt-2" aria-label="Current replay anomalies">
      <p className="section-kicker">Current Replay Anomalies</p>
      {alerts.length === 0 ? (
        <p className="mt-1 text-[10px] text-muted-foreground" role="status">
          {status === "idle"
            ? "No replay anomalies yet. Start a historical replay to generate observations."
            : "No anomalies detected in the observations processed so far."}
        </p>
      ) : (
        <div className="mt-1.5 max-h-[220px] space-y-1.5 overflow-y-auto pr-0.5">
          {alerts.map((alert) => {
            const selected = selectedAlertId === alert.alert_id;
            const liveStatus = normalizeStatus(alert.status, true);
            return (
              <div
                key={alert.alert_id}
                role="link"
                tabIndex={0}
                aria-label={`Review replay anomaly ${alert.event} at ${alert.station_id}`}
                onClick={() => onReview(alert)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onReview(alert);
                  }
                }}
                className={cn(
                  "grid w-full cursor-pointer grid-cols-[52px_minmax(0,1fr)_auto] items-center gap-2 rounded-xl border px-2.5 py-2 text-left transition-colors",
                  selected
                    ? "border-primary/50 bg-info-soft"
                    : "border-border bg-card hover:border-primary/30 hover:bg-info-soft/50",
                )}
              >
                <time className="text-[10px] font-semibold text-muted-foreground">
                  {formatTime(alert.timestamp)}
                </time>
                <div className="min-w-0">
                  <p className="truncate text-[11px] font-extrabold">
                    {alert.station_id} · {alert.event}{" "}
                    <span className="ml-1 rounded bg-warning-soft px-1 text-[8px] font-extrabold text-warning-deep">
                      Replay
                    </span>
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    Score {formatScore(alert.anomaly_score)} · Confidence{" "}
                    {alert.root_cause_confidence !== null &&
                    alert.root_cause_confidence !== undefined
                      ? formatConfidence(alert.root_cause_confidence)
                      : "Not available"}
                  </p>
                </div>
                <span className="flex items-center gap-1.5">
                  <StatusBadge status={liveStatus} />
                  <span className="text-[10px] font-extrabold text-info">Review →</span>
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MapLab({
  stations,
  selectedStation,
  detail,
  detailLoading,
  detailError,
  stationsLoading,
  stationsError,
  liveActive,
  onSelectStation,
}: {
  stations: (MergedStation & { live?: LiveReading })[];
  selectedStation: (MergedStation & { live?: LiveReading }) | null;
  detail: StationDetailResponse | undefined;
  detailLoading: boolean;
  detailError: boolean;
  stationsLoading: boolean;
  stationsError: string | null;
  liveActive: boolean;
  onSelectStation: (stationId: string) => void;
}) {
  const available = selectedStation?.api?.data_available === true;
  const liveReading = liveActive ? (selectedStation?.live ?? null) : null;
  return (
    <section
      className="map-card relative min-h-[440px] overflow-hidden xl:min-h-0"
      aria-label="India weather station network"
    >
      <div className="absolute left-4 top-4 z-20 flex items-center gap-2 rounded-xl border border-border bg-card/95 px-3 py-2 shadow-soft backdrop-blur-sm">
        <CloudSun className="size-4 text-sky" />
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.08em]">
            India Climate Network
          </p>
          <p className="text-[9px] text-muted-foreground">Live station confidence layer</p>
        </div>
      </div>

      {stationsError && (
        <div
          className="absolute left-4 top-[68px] z-20 max-w-[280px] rounded-xl border border-offline/30 bg-card/95 px-3 py-2 shadow-soft backdrop-blur-sm"
          role="alert"
        >
          <p className="text-[10px] font-extrabold text-offline-deep">Station feed unavailable</p>
          <p className="text-[9px] text-muted-foreground">{stationsError}</p>
        </div>
      )}
      {stationsLoading && (
        <div
          className="absolute left-4 top-[68px] z-20 rounded-xl border border-border bg-card/95 px-3 py-2 shadow-soft backdrop-blur-sm"
          role="status"
        >
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
              data-selected={selectedStation?.id === station.id ? "true" : "false"}
              className="station-hotspot absolute z-10"
              style={{ left: `${station.x}%`, top: `${station.y}%` }}
            >
              <span className="sr-only">{station.city}</span>
            </Button>
          ))}
        </div>
      </div>

      {selectedStation && (
        <div className="absolute bottom-3 right-4 z-20 w-[205px] rounded-xl border border-border bg-card/95 p-3 shadow-soft backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <p className="text-xs font-extrabold">{selectedStation.id}</p>
            <StatusBadge status={selectedStation.status} />
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">{selectedStation.city} station</p>
          {liveReading && (
            <p className="mt-1 text-[9px] font-bold text-success-deep" role="status">
              Streamed {formatTime(liveReading.timestamp)} · score{" "}
              {formatScore(liveReading.anomaly.score)}
            </p>
          )}
          {available ? (
            <>
              <div className="mt-2 flex items-end justify-between">
                <span className="text-[10px] text-muted-foreground">Current reading</span>
                <strong className="text-base">{selectedStation.temperature}</strong>
              </div>
              {detailLoading && (
                <p className="mt-1 text-[9px] text-muted-foreground" role="status">
                  Loading station detail…
                </p>
              )}
              {detailError && (
                <p className="mt-1 text-[9px] font-semibold text-offline-deep">
                  Station detail unavailable.
                </p>
              )}
              {detail && (
                <div className="mt-1.5 space-y-0.5 border-t border-border pt-1.5 text-[9px] text-muted-foreground">
                  <p className="flex justify-between">
                    <span>Anomaly score</span>
                    <strong className="text-foreground">{formatScore(detail.anomaly.score)}</strong>
                  </p>
                  <p className="flex justify-between">
                    <span>Data quality</span>
                    <strong className="text-foreground">{detail.data_quality.status}</strong>
                  </p>
                  <p className="flex justify-between">
                    <span>Updated</span>
                    <strong className="text-foreground">
                      {formatDateTime(detail.station.last_updated)}
                    </strong>
                  </p>
                </div>
              )}
              <Link
                to="/stations/$stationId"
                params={{ stationId: selectedStation.id }}
                className="mt-2 block text-center text-[10px] font-extrabold text-info hover:underline"
              >
                Open station detail →
              </Link>
            </>
          ) : (
            <div className="mt-2">
              <p className="text-[10px] font-bold text-offline-deep">Station unavailable</p>
              <p className="text-[9px] text-muted-foreground">
                No backend data for this station in historical replay.
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function InvestigationPanel({
  alert,
  alertsLoading,
  alertsError,
  livePreview,
  split,
}: {
  alert: AlertSummary | null;
  alertsLoading: boolean;
  alertsError: string | null;
  livePreview: { summary: AlertSummary; reading: LiveReading } | null;
  split: string | null;
}) {
  const detailQuery = useAlert(alert?.alert_id ?? null);

  if (livePreview) {
    return (
      <aside className="panel min-h-0 overflow-y-auto p-3.5" aria-label="Investigation panel">
        <LiveInvestigationBody
          key={livePreview.summary.alert_id}
          summary={livePreview.summary}
          reading={livePreview.reading}
          split={split}
        />
      </aside>
    );
  }

  if (alertsError) {
    return (
      <aside className="panel min-h-0 overflow-y-auto p-3.5" aria-label="Investigation panel">
        <p className="section-kicker">Investigation</p>
        <h2 className="mt-0.5 text-sm font-extrabold">Alerts unavailable</h2>
        <p className="mt-2 text-[10px] text-muted-foreground" role="alert">
          {alertsError}
        </p>
      </aside>
    );
  }

  if (alertsLoading || alert === null) {
    return (
      <aside className="panel min-h-0 overflow-y-auto p-3.5" aria-label="Investigation panel">
        <p className="section-kicker">Investigation</p>
        <h2 className="mt-0.5 text-sm font-extrabold">
          {alertsLoading ? "Loading alerts…" : "No alerts"}
        </h2>
        <p className="mt-2 text-[10px] text-muted-foreground" role="status">
          {alertsLoading
            ? "Fetching the attention queue from the API."
            : "No alerts in the current window."}
        </p>
      </aside>
    );
  }

  const detail = detailQuery.data;
  const status = normalizeStatus(alert.status, true);

  return (
    <aside className="panel min-h-0 overflow-y-auto p-3.5" aria-label="Investigation panel">
      <InvestigationBody
        key={alert.alert_id}
        alert={alert}
        detail={detail}
        detailLoading={detailQuery.isPending}
        detailError={detailQuery.isError ? errorMessage(detailQuery.error) : null}
        status={status}
      />
    </aside>
  );
}

function LiveInvestigationBody({
  summary,
  reading,
  split,
}: {
  summary: AlertSummary;
  reading: LiveReading;
  split: string | null;
}) {
  const navigate = useNavigate();
  const status = normalizeStatus(summary.status, true);
  const historyQuery = useStationHistory(summary.station_id, "temperature", 24);
  const historySeries = useMemo(
    () => toChartPoints(historyQuery.data?.points ?? [], "temperature"),
    [historyQuery.data],
  );
  const spatial = reading.evidence.spatial;
  const spatialAvailable = spatial["available"] === true;
  const multi = reading.evidence.multivariate;
  const explanationFeatures = useMemo(
    () =>
      reading.explanation.features.map((feature) => ({
        name: String(feature["name"] ?? "feature"),
        value: typeof feature["value"] === "number" ? (feature["value"] as number) : null,
        contribution:
          typeof feature["contribution"] === "number" ? (feature["contribution"] as number) : null,
        direction: String(feature["direction"] ?? "unknown"),
      })),
    [reading],
  );
  const evidence = [
    {
      title: "Statistical evidence",
      detail: `max|z|=${reading.evidence.statistical.raw?.toFixed(2) ?? "—"} (calibrated ${reading.evidence.statistical.calibrated?.toFixed(3) ?? "—"}).`,
      source: "statistical",
    },
    {
      title: "Isolation Forest evidence",
      detail: `raw score=${reading.evidence.isolation_forest.raw?.toFixed(3) ?? "—"} (calibrated ${reading.evidence.isolation_forest.calibrated?.toFixed(3) ?? "—"}).`,
      source: "isolation_forest",
    },
    {
      title: "LSTM reconstruction evidence",
      detail: `target MSE=${reading.evidence.lstm.raw?.toFixed(3) ?? "—"} (calibrated ${reading.evidence.lstm.calibrated?.toFixed(3) ?? "—"}).`,
      source: "lstm",
    },
    {
      title: "Ensemble decision",
      detail: `score=${reading.anomaly.score?.toFixed(3) ?? "—"} vs threshold ${reading.anomaly.threshold?.toFixed(3) ?? "—"}; availability=${reading.anomaly.availability}.`,
      source: "ensemble",
    },
    {
      title: "Multivariate evidence",
      detail:
        typeof multi["multivariate_max_abs_robust_deviation_2h"] === "number"
          ? `max robust deviation=${(multi["multivariate_max_abs_robust_deviation_2h"] as number).toFixed(2)}.`
          : "Multivariate context not available for this event.",
      source: "multivariate",
    },
    {
      title: "Spatial evidence",
      detail: spatialAvailable
        ? `Reference median ${typeof spatial["reference_median"] === "number" ? `${(spatial["reference_median"] as number).toFixed(1)}°C` : "—"} (${String(spatial["neighbor_count"] ?? "—")} neighbors, ${String(spatial["context"] ?? "—")}).`
        : "Spatial context unavailable — no neighbor values invented.",
      source: "spatial",
    },
    {
      title: "Data-quality evidence",
      detail: `${reading.data_quality.status}; ML ${reading.data_quality.ml_eligible ? "eligible" : "ineligible"}.`,
      source: "quality",
    },
  ];
  return (
    <>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="section-kicker">Replay Anomaly</p>
          <h2 className="mt-0.5 text-sm font-extrabold">
            {summary.station_id} · {reading.city}
          </h2>
          <p className="text-[10px] text-muted-foreground">
            Historical Replay · {split ?? "—"} · {formatTime(reading.timestamp)}
          </p>
        </div>
        <StatusBadge status={status} />
      </div>
      <div className="mt-2.5 grid grid-cols-3 gap-1.5">
        <DetailStat
          label="Streamed temperature"
          value={formatTemp(reading.observations.temperature_c)}
          emphasis
          tone="bg-anomaly-soft"
        />
        <DetailStat
          label="Streamed humidity"
          value={formatHumidity(reading.observations.relative_humidity_pct)}
          tone="bg-surface-blue-tint"
        />
        <DetailStat
          label="Streamed pressure"
          value={formatPressure(reading.observations.pressure_hpa)}
          tone="bg-surface-blue-tint"
          valueTone="text-info"
        />
      </div>
      <div className="mt-2.5 divide-y divide-border rounded-xl border border-border px-2.5">
        <FactRow
          label="Anomaly score"
          value={`${formatScore(reading.anomaly.score)} / threshold ${formatScore(reading.anomaly.threshold)}`}
        />
        <FactRow
          label="Confidence"
          value={formatConfidence(summary.root_cause_confidence ?? reading.anomaly.confidence)}
        />
        <FactRow label="Data quality" value={reading.data_quality.status} />
      </div>
      <div className="mt-2.5">
        <EvidenceList evidence={evidence} loading={false} />
      </div>
      <div className="mt-2.5">
        <OutcomeBanner
          status={status}
          outcome={cleanText(summary.root_cause) ?? summary.event}
          message={
            cleanText(reading.explanation.text) ??
            "Streamed replay event assessed by the frozen pipeline."
          }
          rootCauseConfidence={summary.root_cause_confidence ?? reading.root_cause.confidence}
          ensembleMethod={reading.anomaly.method}
        />
        {cleanText(reading.root_cause.runner_up) && (
          <p className="mt-1 text-[10px] text-muted-foreground">
            Runner-up: {reading.root_cause.runner_up} — uncertainty preserved, no diagnosis
            invented.
          </p>
        )}
      </div>
      <div className="mt-2.5">
        <ExplanationBlock
          explanation={{ text: reading.explanation.text, features: explanationFeatures }}
          loading={false}
        />
      </div>
      <div className="mt-2.5 rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
          Temporal context · station history
        </p>
        <div className="mt-1">
          {historyQuery.isPending ? (
            <p
              className="flex h-[72px] items-center justify-center text-[9px] text-muted-foreground"
              role="status"
            >
              Loading station history…
            </p>
          ) : historyQuery.isError ? (
            <p
              className="flex h-[72px] items-center justify-center text-[9px] text-muted-foreground"
              role="alert"
            >
              Station history unavailable.
            </p>
          ) : (
            <HistoryChart
              data={historySeries}
              height={72}
              ariaLabel={`Temperature history for ${summary.station_id}`}
            />
          )}
        </div>
      </div>
      <div className="mt-2.5 grid grid-cols-1 gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            navigate({ to: "/stations/$stationId", params: { stationId: summary.station_id } })
          }
        >
          <Eye />
          View station
        </Button>
      </div>
      <p className="mt-2 text-center text-[8px] text-muted-foreground">
        Replay investigation — exact streamed payload from this session. Stored alert pages cover
        persistent historical alerts.
      </p>
    </>
  );
}

function InvestigationBody({
  alert,
  detail,
  detailLoading,
  detailError,
  status,
}: {
  alert: AlertSummary;
  detail: AlertDetailResponse | undefined;
  detailLoading: boolean;
  detailError: string | null;
  status: DisplayStatus;
}) {
  const navigate = useNavigate();
  const observations = detail?.observations;
  const historyVariable = detail?.history.variable ?? "temperature";
  const historyHours = detail?.history.hours ?? 24;
  const historySeries = useMemo(
    () => toChartPoints(detail?.history.series ?? [], historyVariable),
    [detail, historyVariable],
  );
  const reviewLabel =
    status === "offline"
      ? "Data availability event"
      : status === "anomaly"
        ? "Anomaly"
        : "Review needed";

  return (
    <>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="section-kicker">{alert.station_id} / Investigation</p>
          <h2 className="mt-0.5 text-sm font-extrabold">{alert.event}</h2>
        </div>
        <span
          className={cn(
            "status-badge shrink-0",
            status === "offline"
              ? "status-offline"
              : status === "anomaly"
                ? "status-anomaly"
                : "status-review",
          )}
        >
          <span className="status-dot" />
          {reviewLabel}
        </span>
      </div>
      {detailLoading && (
        <p className="mt-2 text-[10px] text-muted-foreground" role="status">
          Loading investigation detail…
        </p>
      )}
      {detailError && (
        <p
          className="mt-2 rounded-xl border border-offline/30 bg-offline-soft px-2.5 py-2 text-[9px] font-semibold text-offline-deep"
          role="alert"
        >
          Could not load full investigation detail: {detailError}
        </p>
      )}
      <div className="mt-2.5 grid grid-cols-3 gap-1.5">
        <DetailStat
          label="Observed temperature"
          value={
            observations
              ? formatTemp(observations.temperature_c)
              : detailLoading
                ? "…"
                : "Not available"
          }
          emphasis
          tone="bg-anomaly-soft"
        />
        <DetailStat
          label="Observed humidity"
          value={
            observations
              ? formatHumidity(observations.relative_humidity_pct)
              : detailLoading
                ? "…"
                : "Not available"
          }
          tone="bg-surface-blue-tint"
        />
        <DetailStat
          label="Observed pressure"
          value={
            observations
              ? formatPressure(observations.pressure_hpa)
              : detailLoading
                ? "…"
                : "Not available"
          }
          tone="bg-surface-blue-tint"
          valueTone="text-info"
        />
      </div>
      <div className="mt-2.5">
        <EvidenceList evidence={detail?.evidence ?? []} loading={detailLoading} />
      </div>
      <div className="mt-2.5 rounded-xl border border-border p-2.5">
        <div className="flex items-start justify-between gap-2">
          <p className="text-[9px] font-extrabold uppercase tracking-[0.04em]">
            {historyVariable} history · {historyHours} hours
          </p>
          <div className="flex flex-wrap justify-end gap-x-2 gap-y-1 text-[7px] font-semibold text-muted-foreground">
            <span className="flex items-center gap-1">
              <i className="size-1.5 rounded-full bg-anomaly" />
              Recorded ({alert.station_id})
            </span>
          </div>
        </div>
        <div className="mt-1">
          {detailLoading && historySeries.length === 0 ? (
            <p
              className="flex h-[72px] items-center justify-center text-[9px] text-muted-foreground"
              role="status"
            >
              Loading history…
            </p>
          ) : (
            <HistoryChart
              data={historySeries}
              height={72}
              ariaLabel={`${historyVariable} history for ${alert.station_id}`}
            />
          )}
        </div>
      </div>
      <div className="mt-2.5">
        <OutcomeBanner
          status={status}
          outcome={alert.event}
          message="Open the full investigation for evidence, root cause and explanation."
        />
      </div>
      <div className="mt-2.5 grid grid-cols-2 gap-2">
        <Button
          size="sm"
          onClick={() =>
            navigate({ to: "/investigations/$alertId", params: { alertId: alert.alert_id } })
          }
        >
          <ArrowUpRight />
          Open investigation
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            navigate({ to: "/stations/$stationId", params: { stationId: alert.station_id } })
          }
        >
          <Eye />
          View station
        </Button>
      </div>
    </>
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
  healthyCount,
  networkUpdated,
  networkLoading,
}: {
  alerts: AlertSummary[];
  liveAlerts: AlertSummary[];
  liveIds: Set<string>;
  selectedAlertId: string | null;
  onSelectAlert: (alert: AlertSummary, isLive: boolean) => void;
  loading: boolean;
  error: string | null;
  healthyCount: number | null;
  networkUpdated: string | null;
  networkLoading: boolean;
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
          <p className="section-kicker">Attention queue · Historical alerts</p>
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
                        LIVE
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
      <div className="mt-3 rounded-xl bg-success-soft px-3 py-2.5">
        {networkLoading ? (
          <p className="text-[10px] font-bold text-success-deep">Loading network status…</p>
        ) : healthyCount !== null ? (
          <>
            <p className="text-[10px] font-bold text-success-deep">
              {healthyCount} stations are reporting normally
            </p>
            <p className="mt-0.5 text-[9px] text-muted-foreground">
              Last network check: {formatDateTime(networkUpdated)}.{" "}
              <Link to="/evaluation" className="font-bold text-info hover:underline">
                View evaluation evidence →
              </Link>
            </p>
          </>
        ) : (
          <p className="text-[10px] font-bold text-success-deep">Network status unavailable</p>
        )}
      </div>
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
      color: "var(--chart-alert)",
      tone: "bg-anomaly-soft text-anomaly",
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
