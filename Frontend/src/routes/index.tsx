import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState, type ComponentType } from "react";
import {
  Activity,
  ArrowUpRight,
  AlertTriangle,
  BarChart3,
  Bell,
  CloudSun,
  Droplets,
  FlaskConical,
  Gauge,
  HeartPulse,
  Eye,
  MapPin,
  RadioTower,
  Search,
  ShieldCheck,
  Sun,
  Moon,
  Thermometer,
  WifiOff,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ApiError,
  DATA_MODE_HISTORICAL_REPLAY,
  normalizeStatus,
  type AlertDetailResponse,
  type AlertSummary,
  type DisplayStatus,
  type HistoryVariable,
  type NetworkSummary,
  type StationDetailResponse,
  type StationSummary,
} from "@/lib/api";
import {
  useAlert,
  useAlerts,
  useHealth,
  useNetworkSummary,
  useStation,
  useStationHistory,
  useStations,
} from "@/hooks/useSkyguard";

const indiaAsset = { url: "/assets/india.png" };

export const Route = createFileRoute("/")({
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

// ---------------------------------------------------------------------------
// Visual configuration only. Positions, ids and display names for the India
// map are local UI config — every status/reading comes from the API.
// JENA-01 is backend-only and intentionally has no map entry.
// ---------------------------------------------------------------------------

type StationMapMeta = {
  id: string;
  city: string;
  x: number;
  y: number;
};

const stationMapMeta: StationMapMeta[] = [
  { id: "DEL-01", city: "New Delhi", x: 42.3, y: 18.2 },
  { id: "JAI-02", city: "Jaipur", x: 34.1, y: 30.3 },
  { id: "LUCK-04", city: "Lucknow", x: 61.2, y: 34.4 },
  { id: "AMD-06", city: "Ahmedabad", x: 27.2, y: 43.7 },
  { id: "BHO-08", city: "Bhopal", x: 45.2, y: 45.3 },
  { id: "MUM-03", city: "Mumbai", x: 30.2, y: 56.1 },
  { id: "HYD-07", city: "Hyderabad", x: 44.2, y: 66.2 },
  { id: "BLR-05", city: "Bengaluru", x: 44.8, y: 81.3 },
  { id: "CHE-03", city: "Chennai", x: 62.1, y: 81.2 },
  { id: "KOL-02", city: "Kolkata", x: 77.7, y: 47.4 },
];

type MergedStation = StationMapMeta & {
  status: DisplayStatus;
  temperature: string;
  api: StationSummary | undefined;
};

const statusLabels: Record<DisplayStatus, string> = {
  healthy: "Healthy",
  review: "Needs review",
  anomaly: "Anomaly",
  offline: "Offline",
};

type Theme = "light" | "dark";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Request failed.";
}

/**
 * Backend string fields occasionally serialize a missing value as the literal
 * string "nan" (pandas NaN through str()). Treat those as missing so the UI
 * never renders "nan" text and falls back to honest empty states instead.
 */
function cleanText(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const trimmed = value.trim();
  if (trimmed === "" || trimmed.toLowerCase() === "nan") return null;
  return value;
}

function formatTemp(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(1)}°C`;
}

function formatHumidity(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  return `${value.toFixed(1)}% RH`;
}

function formatPressure(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  return `${value.toFixed(1)} hPa`;
}

function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(3);
}

function formatTime(iso: string | null | undefined): string {
  if (iso === null || iso === undefined || iso === "") return "—";
  const date = new Date(iso);
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }
  const match = iso.match(/(\d{2}):(\d{2})/);
  if (match) return `${match[1]}:${match[2]}`;
  return iso;
}

function formatDateTime(iso: string | null | undefined): string {
  if (iso === null || iso === undefined || iso === "") return "Not available";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function LiveOverview() {
  const [selectedStationId, setSelectedStationId] = useState<string | null>("DEL-01");
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>("light");

  const healthQuery = useHealth();
  const networkQuery = useNetworkSummary();
  const stationsQuery = useStations();
  const alertsQuery = useAlerts(50);

  const stationsById = useMemo(() => {
    const map = new Map<string, StationSummary>();
    for (const station of stationsQuery.data?.stations ?? []) {
      map.set(station.station_id, station);
    }
    return map;
  }, [stationsQuery.data]);

  const mergedStations: MergedStation[] = useMemo(
    () =>
      stationMapMeta.map((meta) => {
        const api = stationsById.get(meta.id);
        return {
          ...meta,
          status: normalizeStatus(api?.status, api?.data_available ?? false),
          temperature: formatTemp(api?.temperature),
          api,
        };
      }),
    [stationsById],
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

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

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

  const dataMode =
    healthQuery.data?.data_mode ??
    stationsQuery.data?.data_mode ??
    networkQuery.data?.data_mode ??
    alertsQuery.data?.data_mode ??
    null;
  const backendFailed =
    healthQuery.isError && stationsQuery.isError && networkQuery.isError && alertsQuery.isError;

  return (
    <main className="flex min-h-screen flex-col bg-background text-foreground lg:h-screen lg:overflow-hidden">
      <div className="dashboard-shell flex min-h-[876px] flex-1 overflow-hidden bg-surface lg:h-full lg:min-h-0">
        <Sidebar alertCount={alertsQuery.data ? String(alerts.length) : null} />

        <section className="flex min-w-0 flex-1 flex-col">
          <Header
            theme={theme}
            onThemeChange={setTheme}
            online={!backendFailed}
            dataMode={dataMode}
          />
          <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 pt-0 lg:overflow-y-auto">
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
                isOnMap={
                  selectedAlert
                    ? stationMapMeta.some((meta) => meta.id === selectedAlert.station_id)
                    : false
                }
                onViewStation={selectStation}
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
              stationLabel={
                selectedStation ? `${selectedStation.id} · ${selectedStation.city}` : null
              }
              dataAvailable={selectedStation?.api?.data_available === true}
            />
          </div>
        </section>
      </div>
    </main>
  );
}

const navItems = [
  { label: "Overview", icon: BarChart3, active: true },
  { label: "Stations", icon: MapPin },
  { label: "Alerts", icon: Bell },
  { label: "Investigations", icon: Search },
  { label: "Network Health", icon: HeartPulse },
  { label: "Judge Probe", icon: FlaskConical },
];

function Sidebar({ alertCount }: { alertCount: string | null }) {
  return (
    <aside className="hidden w-[176px] shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-3 py-5 text-sidebar-foreground lg:flex">
      <div className="flex items-center gap-2 px-2">
        <div className="flex size-10 items-center justify-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground shadow-logo">
          <ShieldCheck className="size-6" strokeWidth={2.4} />
        </div>
        <div>
          <p className="text-base font-extrabold leading-none text-sidebar-foreground">
            SkyGuard <span className="text-sidebar-highlight">AI</span>
          </p>
          <p className="mt-1 text-[8px] font-semibold uppercase tracking-[0.12em] text-sidebar-muted">
            Climate intelligence
          </p>
        </div>
      </div>
      <p className="mt-3 px-2 text-[10px] font-medium text-sidebar-muted">
        Trusted Data. Safer Tomorrow.
      </p>

      <nav className="mt-8 space-y-1.5" aria-label="Primary navigation">
        {navItems.map((item) => (
          <Button
            key={item.label}
            variant={item.active ? "sidebarActive" : "sidebar"}
            className="w-full justify-start"
            title={item.label}
          >
            <item.icon />
            <span>{item.label}</span>
            {item.label === "Alerts" && alertCount !== null && (
              <span className="ml-auto rounded-full bg-anomaly px-1.5 py-0.5 text-[9px] text-anomaly-foreground">
                {alertCount}
              </span>
            )}
          </Button>
        ))}
      </nav>
    </aside>
  );
}

function Header({
  theme,
  onThemeChange,
  online,
  dataMode,
}: {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
  online: boolean;
  dataMode: string | null;
}) {
  const replay = dataMode === DATA_MODE_HISTORICAL_REPLAY;
  return (
    <header className="flex h-[72px] shrink-0 items-center justify-between px-5">
      <div>
        <h1 className="text-[25px] font-extrabold leading-tight text-foreground">Live Overview</h1>
        <p className="text-xs font-medium text-muted-foreground">
          National weather station monitoring and anomaly intelligence
        </p>
      </div>
      <div className="flex items-center gap-2">
        {online ? (
          <span className="status-pill bg-success-soft text-success-deep">
            <span className="status-dot bg-success" />
            System Online
          </span>
        ) : (
          <span className="status-pill bg-offline-soft text-offline-deep">
            <span className="status-dot bg-offline" />
            Backend Unreachable
          </span>
        )}
        {replay ? (
          <span
            className="status-pill bg-info-soft text-info"
            title="API data_mode: historical_replay — observations are replayed history, not a live sensor feed."
          >
            <Activity className="size-3.5" />
            Historical Replay
          </span>
        ) : (
          <span className="status-pill bg-info-soft text-info">
            <Activity className="size-3.5" />
            {dataMode ?? "Connecting…"}
          </span>
        )}
        <div
          role="group"
          aria-label="Color theme"
          className="ml-1 flex items-center rounded-full border border-border bg-card p-1 shadow-soft"
        >
          <button
            type="button"
            onClick={() => onThemeChange("light")}
            aria-pressed={theme === "light"}
            aria-label="Light mode"
            title="Light mode"
            className={cn(
              "flex size-7 cursor-pointer items-center justify-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              theme === "light"
                ? "bg-info-soft text-info"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Sun className="size-4" />
          </button>
          <button
            type="button"
            onClick={() => onThemeChange("dark")}
            aria-pressed={theme === "dark"}
            aria-label="Dark mode"
            title="Dark mode"
            className={cn(
              "flex size-7 cursor-pointer items-center justify-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              theme === "dark"
                ? "bg-info-soft text-info"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Moon className="size-4" />
          </button>
        </div>
      </div>
    </header>
  );
}

function KpiRow({
  summary,
  loading,
  error,
}: {
  summary: NetworkSummary | undefined;
  loading: boolean;
  error: string | null;
}) {
  const value = (n: number | undefined) => {
    if (loading) return "…";
    if (error || n === undefined) return "—";
    return String(n);
  };
  const kpis: Array<{
    label: string;
    value: string;
    icon: ComponentType<{ className?: string }>;
    tone: string;
  }> = [
    {
      label: "Stations Monitored",
      value: value(summary?.stations_monitored),
      icon: RadioTower,
      tone: "bg-sky-soft text-sky",
    },
    {
      label: "Healthy",
      value: value(summary?.healthy),
      icon: ShieldCheck,
      tone: "bg-success-soft text-success",
    },
    {
      label: "Needs Review",
      value: value(summary?.needs_review),
      icon: AlertTriangle,
      tone: "bg-warning-soft text-warning",
    },
    {
      label: "Offline",
      value: value(summary?.offline),
      icon: WifiOff,
      tone: "bg-offline-soft text-offline",
    },
    {
      label: "Network Health",
      value: loading
        ? "…"
        : error || summary === undefined
          ? "—"
          : `${summary.network_health_pct}%`,
      icon: HeartPulse,
      tone: "bg-info-soft text-info",
    },
  ];

  return (
    <section aria-label="Network summary">
      <div className="grid shrink-0 grid-cols-5 gap-2.5">
        {kpis.map((kpi) => (
          <article key={kpi.label} className="metric-card">
            <span className={cn("flex size-9 items-center justify-center rounded-xl", kpi.tone)}>
              <kpi.icon className="size-[18px]" />
            </span>
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground">{kpi.label}</p>
              <p className="text-lg font-extrabold leading-tight">{kpi.value}</p>
            </div>
          </article>
        ))}
      </div>
      {error && (
        <p
          className="mt-1.5 rounded-xl border border-offline/30 bg-offline-soft px-3 py-1.5 text-[10px] font-semibold text-offline-deep"
          role="alert"
        >
          Network summary unavailable: {error}
        </p>
      )}
    </section>
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
              aria-label={`Select ${station.city} station, ${statusLabels[station.status]}`}
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
                    <span>Root cause</span>
                    <strong className="text-foreground">
                      {cleanText(detail.root_cause.class) ?? "Not available"}
                    </strong>
                  </p>
                  <p className="flex justify-between">
                    <span>Updated</span>
                    <strong className="text-foreground">
                      {formatDateTime(detail.station.last_updated)}
                    </strong>
                  </p>
                </div>
              )}
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

function StatusBadge({ status }: { status: DisplayStatus }) {
  return (
    <span className={cn("status-badge", `status-${status}`)}>
      <span className="status-dot" />
      {statusLabels[status]}
    </span>
  );
}

function InvestigationPanel({
  alert,
  alertsLoading,
  alertsError,
  isOnMap,
  onViewStation,
}: {
  alert: AlertSummary | null;
  alertsLoading: boolean;
  alertsError: string | null;
  isOnMap: boolean;
  onViewStation: (stationId: string) => void;
}) {
  const [actionNotice, setActionNotice] = useState("");
  const detailQuery = useAlert(alert?.alert_id ?? null);

  useEffect(() => {
    setActionNotice("");
  }, [alert?.alert_id]);

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
        actionNotice={actionNotice}
        setActionNotice={setActionNotice}
        isOnMap={isOnMap}
        onViewStation={onViewStation}
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
  actionNotice,
  setActionNotice,
  isOnMap,
  onViewStation,
}: {
  alert: AlertSummary;
  detail: AlertDetailResponse | undefined;
  detailLoading: boolean;
  detailError: string | null;
  status: DisplayStatus;
  actionNotice: string;
  setActionNotice: (notice: string) => void;
  isOnMap: boolean;
  onViewStation: (stationId: string) => void;
}) {
  const observations = detail?.observations;
  const historyVariable = detail?.history.variable ?? "temperature";
  const historyHours = detail?.history.hours ?? 24;
  const historySeries = (detail?.history.series ?? []).map((point, index) => {
    const raw = point[historyVariable];
    return {
      time: formatTime(point.timestamp),
      recorded: typeof raw === "number" ? raw : null,
      index,
    };
  });
  const outcome = cleanText(detail?.root_cause.class) ?? cleanText(alert.root_cause) ?? alert.event;
  const outcomeMessage =
    cleanText(detail?.explanation.text) ?? cleanText(alert.summary) ?? "No explanation available.";
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
      <div className="mt-2.5 rounded-xl border border-border p-2.5">
        <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
          Why this needs review
        </p>
        <div className="mt-1.5 space-y-1.5">
          {detail && detail.evidence.length > 0 ? (
            detail.evidence.map((item, index) => (
              <div key={`${item.source}-${index}`} className="flex gap-2">
                <span
                  className={cn(
                    "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full text-[8px] font-extrabold",
                    index === 0 ? "bg-warning-soft text-warning-deep" : "bg-info-soft text-info",
                  )}
                >
                  {index + 1}
                </span>
                <p className="text-[9px] leading-snug">
                  <strong className="block text-foreground">{item.title}</strong>
                  <span className="text-muted-foreground">{item.detail}</span>
                </p>
              </div>
            ))
          ) : (
            <p className="text-[9px] text-muted-foreground">
              {detailLoading ? "Loading evidence…" : "No evidence items available for this alert."}
            </p>
          )}
        </div>
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
        <div className="mt-1 h-[72px]">
          {historySeries.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={historySeries} margin={{ top: 4, right: 3, bottom: 0, left: 3 }}>
                <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 7, fill: "var(--muted-foreground)" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
                <Line
                  type="monotone"
                  dataKey="recorded"
                  stroke="var(--chart-alert)"
                  dot={false}
                  strokeWidth={2.5}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="flex h-full items-center justify-center text-[9px] text-muted-foreground">
              {detailLoading ? "Loading history…" : "No history available."}
            </p>
          )}
        </div>
      </div>
      <div
        className={cn(
          "mt-2.5 flex items-start gap-2 rounded-xl border p-2.5",
          status === "offline"
            ? "border-offline/30 bg-offline-soft text-offline"
            : status === "anomaly"
              ? "border-anomaly/30 bg-anomaly-soft text-anomaly"
              : "border-warning/30 bg-warning-soft text-warning",
        )}
      >
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
        <p className="text-[9px] leading-snug">
          <strong
            className={cn(
              "block",
              status === "offline"
                ? "text-offline-deep"
                : status === "anomaly"
                  ? "text-anomaly-deep"
                  : "text-warning-deep",
            )}
          >
            {outcome}
          </strong>
          <span className="text-muted-foreground">{outcomeMessage}</span>
          {detail && (
            <span className="mt-1 block text-muted-foreground">
              Root-cause confidence:{" "}
              {detail.root_cause.confidence !== null && detail.root_cause.confidence !== undefined
                ? `${(detail.root_cause.confidence * 100).toFixed(0)}%`
                : "Not available"}{" "}
              · Ensemble: {detail.ensemble_method}
            </span>
          )}
          {!detail && alert.anomaly_score !== null && alert.anomaly_score !== undefined && (
            <span className="mt-1 block text-muted-foreground">
              Anomaly score: {formatScore(alert.anomaly_score)}
            </span>
          )}
        </p>
      </div>
      <div className="mt-2.5 grid grid-cols-2 gap-2">
        <Button
          size="sm"
          onClick={() => setActionNotice("Investigation detail loaded from historical replay.")}
        >
          <ArrowUpRight />
          Open investigation
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            onViewStation(alert.station_id);
            setActionNotice(
              isOnMap
                ? `${alert.station_id} is highlighted on the map.`
                : `${alert.station_id} is backend-only and not on the India map.`,
            );
          }}
        >
          <Eye />
          View station
        </Button>
      </div>
      {actionNotice && (
        <p className="mt-2 text-center text-[8px] font-semibold text-info" role="status">
          {actionNotice}
        </p>
      )}
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
                <button
                  key={alert.alert_id}
                  type="button"
                  onClick={() => onSelectAlert(alert)}
                  aria-pressed={selected}
                  title={alert.summary}
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
                </button>
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

function DetailStat({
  label,
  value,
  emphasis = false,
  tone,
  valueTone,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
  tone?: string;
  valueTone?: string;
}) {
  return (
    <div
      className={cn("min-w-0 rounded-xl p-2", tone ?? (emphasis ? "bg-anomaly-soft" : "bg-muted"))}
    >
      <p className="text-[7px] font-semibold leading-tight text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mt-1 break-words text-[11px] font-extrabold leading-tight",
          valueTone ?? (emphasis && "text-anomaly"),
        )}
      >
        {value}
      </p>
    </div>
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
                    <AreaChart data={sensor.series.values}>
                      <defs>
                        <linearGradient id={`fill-${sensor.title}`} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={sensor.color} stopOpacity={0.28} />
                          <stop offset="100%" stopColor={sensor.color} stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <Area
                        type="monotone"
                        dataKey="value"
                        stroke={sensor.color}
                        strokeWidth={2.2}
                        fill={`url(#fill-${sensor.title})`}
                        dot={false}
                        connectNulls={false}
                        isAnimationActive={false}
                      />
                    </AreaChart>
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
