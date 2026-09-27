import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Bell, CloudSun, Droplets, Eye, Gauge, Thermometer } from "lucide-react";
import { ResponsiveContainer } from "recharts";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { StatusBadge, DetailStat } from "@/components/common";
import { HistoryChart, SensorSpark, toChartPoints } from "@/components/charts";
import { EvidenceList, OutcomeBanner } from "@/components/evidence";
import { KpiRow } from "@/components/kpi";
import {
  normalizeStatus,
  type AlertDetailResponse,
  type AlertSummary,
  type StationDetailResponse,
} from "@/lib/api";
import type { DisplayStatus } from "@/lib/api";
import {
  errorMessage,
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

  const networkQuery = useNetworkSummary();
  const stationsQuery = useStations();
  const alertsQuery = useAlerts(50);

  const mergedStations = useMemo(
    () => mergeStations(stationsQuery.data?.stations ?? []),
    [stationsQuery.data],
  );

  const selectedStation = useMemo(
    () => mergedStations.find((station) => station.id === selectedStationId) ?? null,
    [mergedStations, selectedStationId],
  );

  const alerts = useMemo(() => alertsQuery.data?.alerts ?? [], [alertsQuery.data]);

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
    const match = alerts.find((alert) => alert.station_id === stationId);
    if (match) setSelectedAlertId(match.alert_id);
  };

  const selectAlert = (alert: AlertSummary) => {
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
      <div className="grid min-h-[500px] shrink-0 grid-cols-1 gap-3 xl:h-[520px] xl:min-h-0 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] 2xl:h-[600px]">
        <MapLab
          stations={mergedStations}
          selectedStation={selectedStation}
          detail={stationDetailQuery.data}
          detailLoading={stationDetailQuery.isPending && detailStationId !== null}
          detailError={stationDetailQuery.isError}
          stationsLoading={stationsQuery.isPending}
          stationsError={stationsQuery.isError ? errorMessage(stationsQuery.error) : null}
          onSelectStation={selectStation}
        />
        <InvestigationPanel
          alert={selectedAlert}
          alertsLoading={alertsQuery.isPending}
          alertsError={alertsQuery.isError ? errorMessage(alertsQuery.error) : null}
        />
      </div>
      <RecentAlerts
        alerts={alerts}
        selectedAlertId={selectedAlertId}
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
      />
    </>
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
  onSelectStation,
}: {
  stations: MergedStation[];
  selectedStation: MergedStation | null;
  detail: StationDetailResponse | undefined;
  detailLoading: boolean;
  detailError: boolean;
  stationsLoading: boolean;
  stationsError: string | null;
  onSelectStation: (stationId: string) => void;
}) {
  const available = selectedStation?.api?.data_available === true;
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
}: {
  alert: AlertSummary | null;
  alertsLoading: boolean;
  alertsError: string | null;
}) {
  const detailQuery = useAlert(alert?.alert_id ?? null);

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
  selectedAlertId,
  onSelectAlert,
  loading,
  error,
  healthyCount,
  networkUpdated,
  networkLoading,
}: {
  alerts: AlertSummary[];
  selectedAlertId: string | null;
  onSelectAlert: (alert: AlertSummary) => void;
  loading: boolean;
  error: string | null;
  healthyCount: number | null;
  networkUpdated: string | null;
  networkLoading: boolean;
}) {
  const navigate = useNavigate();
  const openAlert = (alert: AlertSummary) => {
    onSelectAlert(alert);
    navigate({ to: "/alerts/$alertId", params: { alertId: alert.alert_id } });
  };
  return (
    <section className="panel shrink-0 p-4" aria-label="Recent alerts">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="section-kicker">Attention queue</p>
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
      {!loading && !error && alerts.length === 0 && (
        <p className="mt-3 text-[10px] text-muted-foreground" role="status">
          No alerts in the current window.
        </p>
      )}
      {!loading && !error && alerts.length > 0 && (
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
            {alerts.map((alert) => {
              const selected = selectedAlertId === alert.alert_id;
              const status = normalizeStatus(alert.status, true);
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
                  <strong className="text-[11px] font-extrabold">{alert.station_id}</strong>
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
              Last network check: {formatDateTime(networkUpdated)}.
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
}: {
  stationId: string | null;
  stationLabel: string | null;
  dataAvailable: boolean;
}) {
  const temperature = useSensorSeries(dataAvailable ? stationId : null, "temperature");
  const pressure = useSensorSeries(dataAvailable ? stationId : null, "pressure");
  const humidity = useSensorSeries(dataAvailable ? stationId : null, "humidity");

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
          const displayValue = unavailable
            ? "—"
            : sensor.series.loading
              ? "…"
              : sensor.series.latest !== null
                ? sensor.formatValue(sensor.series.latest)
                : "—";
          const displayDelta =
            unavailable || sensor.series.delta === null
              ? "—"
              : sensor.formatDelta(sensor.series.delta);
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
                {!unavailable && sensor.series.values.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <SensorSpark
                      values={sensor.series.values}
                      color={sensor.color}
                      gradientId={`fill-${sensor.title}`}
                    />
                  </ResponsiveContainer>
                ) : (
                  <p className="flex h-full items-center justify-center text-[9px] text-muted-foreground">
                    {unavailable
                      ? "Station unavailable."
                      : sensor.series.loading
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
