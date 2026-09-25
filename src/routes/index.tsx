import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState, type ComponentType } from "react";
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
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

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
        content: "A live view of trusted weather observations across India's station network.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: LiveOverview,
});

type Status = "healthy" | "review" | "anomaly" | "offline";

type Station = {
  id: string;
  city: string;
  status: Status;
  x: number;
  y: number;
  temperature: string;
};

type AlertItem = {
  stationId: string;
  event: string;
  time: string;
  status: Exclude<Status, "healthy">;
  reviewLabel: string;
  recorded: { label: string; value: string };
  comparison: { label: string; value: string };
  difference: { label: string; value: string };
  evidence: Array<{ title: string; detail: string }>;
  historyTitle: string;
  historyLabels: { recorded: string; context: string };
  history: Array<{ time: string; recorded: number | null; context: number }>;
  outcome: string;
  statusMessage: string;
};

const stations: Station[] = [
  { id: "DEL-01", city: "New Delhi", status: "anomaly", x: 42.3, y: 18.2, temperature: "55.0°C" },
  { id: "JAI-02", city: "Jaipur", status: "review", x: 34.1, y: 30.3, temperature: "7.2°C" },
  { id: "LUCK-04", city: "Lucknow", status: "offline", x: 61.2, y: 34.4, temperature: "—" },
  { id: "AMD-06", city: "Ahmedabad", status: "healthy", x: 27.2, y: 43.7, temperature: "27.1°C" },
  { id: "BHO-08", city: "Bhopal", status: "healthy", x: 45.2, y: 45.3, temperature: "26.4°C" },
  { id: "MUM-03", city: "Mumbai", status: "review", x: 30.2, y: 56.1, temperature: "29.8°C" },
  { id: "HYD-07", city: "Hyderabad", status: "healthy", x: 44.2, y: 66.2, temperature: "28.2°C" },
  { id: "BLR-05", city: "Bengaluru", status: "healthy", x: 44.8, y: 81.3, temperature: "23.6°C" },
  { id: "CHE-03", city: "Chennai", status: "review", x: 62.1, y: 81.2, temperature: "31.0°C" },
  { id: "KOL-02", city: "Kolkata", status: "healthy", x: 77.7, y: 47.4, temperature: "30.4°C" },
];

const alerts: AlertItem[] = [
  {
    stationId: "DEL-01", event: "High Temperature", time: "10:30", status: "anomaly", reviewLabel: "Review needed",
    recorded: { label: "Recorded temperature", value: "55.0°C" }, comparison: { label: "Nearby expectation", value: "32.0°C" }, difference: { label: "Difference", value: "+23.0°C" },
    evidence: [
      { title: "Sudden jump", detail: "Temperature increased rapidly from 31.2°C to 55.0°C." },
      { title: "Nearby stations stay near 32°C", detail: "Surrounding stations report approximately 30–34°C." },
    ],
    historyTitle: "Temperature history · 24 hours", historyLabels: { recorded: "Recorded (DEL-01)", context: "Nearby average" },
    history: [
      { time: "00", recorded: 29, context: 29 }, { time: "04", recorded: 28, context: 28.5 }, { time: "08", recorded: 31.2, context: 30.5 },
      { time: "12", recorded: 55, context: 32 }, { time: "16", recorded: 52, context: 33 }, { time: "20", recorded: 48, context: 31.5 }, { time: "24", recorded: 45, context: 30 },
    ],
    outcome: "Possible spike · Needs operator review", statusMessage: "This reading is significantly higher than nearby stations.",
  },
  {
    stationId: "MUM-03", event: "Pressure Drop", time: "10:28", status: "review", reviewLabel: "Review needed",
    recorded: { label: "Recorded pressure", value: "982.1 hPa" }, comparison: { label: "Local expectation", value: "1001.4 hPa" }, difference: { label: "Difference", value: "−19.3 hPa" },
    evidence: [
      { title: "Sharp baseline departure", detail: "Pressure dropped sharply compared with the station's recent baseline." },
      { title: "Local pressure remains stable", detail: "Nearby stations remain within the expected pressure range." },
    ],
    historyTitle: "Pressure history · 24 hours", historyLabels: { recorded: "Recorded (MUM-03)", context: "Nearby average" },
    history: [
      { time: "00", recorded: 1004, context: 1003 }, { time: "04", recorded: 1003, context: 1003 }, { time: "08", recorded: 1002, context: 1002 },
      { time: "12", recorded: 998, context: 1002 }, { time: "16", recorded: 990, context: 1001 }, { time: "20", recorded: 982.1, context: 1001.4 }, { time: "24", recorded: 984, context: 1001 },
    ],
    outcome: "Pressure departure · Needs operator review", statusMessage: "The local pressure pattern does not match nearby stations.",
  },
  {
    stationId: "JAI-02", event: "Possible Sensor Freeze", time: "10:22", status: "review", reviewLabel: "Review needed",
    recorded: { label: "Current value", value: "68% RH" }, comparison: { label: "Repeated value", value: "68% RH" }, difference: { label: "Duration", value: "6h 05m" },
    evidence: [
      { title: "Unchanged humidity", detail: "Relative humidity remained unchanged for an unusually long period." },
      { title: "Other signals continued moving", detail: "Temperature and pressure continued to vary during the same period." },
    ],
    historyTitle: "Humidity history · 24 hours", historyLabels: { recorded: "Recorded (JAI-02)", context: "Expected movement" },
    history: [
      { time: "00", recorded: 61, context: 60 }, { time: "04", recorded: 65, context: 64 }, { time: "08", recorded: 68, context: 67 },
      { time: "12", recorded: 68, context: 64 }, { time: "16", recorded: 68, context: 59 }, { time: "20", recorded: 68, context: 55 }, { time: "24", recorded: 68, context: 58 },
    ],
    outcome: "Possible frozen signal · Needs operator review", statusMessage: "Humidity is static while related weather signals continue to change.",
  },
  {
    stationId: "CHE-03", event: "Humidity Spike", time: "10:16", status: "review", reviewLabel: "Review needed",
    recorded: { label: "Recorded humidity", value: "91% RH" }, comparison: { label: "Nearby expectation", value: "73% RH" }, difference: { label: "Difference", value: "+18% RH" },
    evidence: [
      { title: "Rapid rise", detail: "Humidity rose 18 percentage points inside one reporting interval." },
      { title: "No matching rain context", detail: "Nearby stations and precipitation signals do not show a similar increase." },
    ],
    historyTitle: "Humidity history · 24 hours", historyLabels: { recorded: "Recorded (CHE-03)", context: "Nearby average" },
    history: [
      { time: "00", recorded: 72, context: 71 }, { time: "04", recorded: 74, context: 72 }, { time: "08", recorded: 73, context: 72 },
      { time: "12", recorded: 76, context: 73 }, { time: "16", recorded: 91, context: 73 }, { time: "20", recorded: 89, context: 74 }, { time: "24", recorded: 84, context: 75 },
    ],
    outcome: "Possible humidity spike · Needs operator review", statusMessage: "The increase is not supported by nearby weather context.",
  },
  {
    stationId: "LUCK-04", event: "Communication Gap", time: "10:11", status: "offline", reviewLabel: "Data availability event",
    recorded: { label: "Last reading", value: "10:24" }, comparison: { label: "Expected next reading", value: "10:29" }, difference: { label: "Missing duration", value: "25 min" },
    evidence: [
      { title: "Expected report missing", detail: "No observation arrived during the expected reporting interval." },
      { title: "Availability interruption", detail: "The last valid packet was received at 10:24." },
    ],
    historyTitle: "Data availability · 24 hours", historyLabels: { recorded: "Received reports", context: "Expected reports" },
    history: [
      { time: "00", recorded: 1, context: 1 }, { time: "04", recorded: 1, context: 1 }, { time: "08", recorded: 1, context: 1 },
      { time: "12", recorded: 1, context: 1 }, { time: "16", recorded: null, context: 1 }, { time: "20", recorded: null, context: 1 }, { time: "24", recorded: null, context: 1 },
    ],
    outcome: "Data availability event", statusMessage: "The station has missed its expected reporting interval.",
  },
];

const activityData = [
  { time: "06", reports: 78, verified: 70 }, { time: "09", reports: 91, verified: 84 },
  { time: "12", reports: 86, verified: 78 }, { time: "15", reports: 104, verified: 95 },
  { time: "18", reports: 97, verified: 91 }, { time: "21", reports: 112, verified: 103 },
  { time: "24", reports: 106, verified: 98 },
];

const sparkData = {
  temperature: [22.8, 23.4, 23.1, 24.2, 23.8, 24.5, 24.8],
  pressure: [1014, 1012, 1013, 1011, 1010, 1009, 1008.3],
  humidity: [47, 49, 48, 53, 51, 54, 56],
};

const statusLabels: Record<Status, string> = {
  healthy: "Healthy",
  review: "Needs review",
  anomaly: "Anomaly",
  offline: "Offline",
};

type Theme = "light" | "dark";

function LiveOverview() {
  const [selectedStationId, setSelectedStationId] = useState<string | null>("DEL-01");
  const [selectedAlert, setSelectedAlert] = useState<AlertItem>(alerts[0] as AlertItem);
  const [theme, setTheme] = useState<Theme>("light");
  const selectedStation = stations.find((station) => station.id === selectedStationId) ?? null;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  const selectStation = (station: Station) => {
    setSelectedStationId(station.id);
    const match = alerts.find((alert) => alert.stationId === station.id);
    if (match) setSelectedAlert(match);
  };

  const selectAlert = (alert: AlertItem) => {
    setSelectedAlert(alert);
    setSelectedStationId(alert.stationId);
  };

  return (
    <main className="flex min-h-screen flex-col bg-background text-foreground lg:h-screen lg:overflow-hidden">
      <div className="dashboard-shell flex min-h-[876px] flex-1 overflow-hidden bg-surface lg:h-full lg:min-h-0">
        <Sidebar />

        <section className="flex min-w-0 flex-1 flex-col">
          <Header theme={theme} onThemeChange={setTheme} />
          <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 pt-0 lg:overflow-y-auto">
            <KpiRow />
            <div className="grid min-h-[500px] shrink-0 grid-cols-1 gap-3 xl:h-[520px] xl:min-h-0 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] 2xl:h-[600px]">
              <MapLab
                selectedStation={selectedStation}
                onSelectStation={selectStation}
              />
              <InvestigationPanel selectedAlert={selectedAlert} />
            </div>
            <RecentAlerts selectedAlert={selectedAlert} onSelectAlert={selectAlert} />
            <BottomInsights />
          </div>
        </section>
      </div>
    </main>
  );
}

const navItems = [
  { label: "Overview", icon: BarChart3, active: true },
  { label: "Stations", icon: MapPin },
  { label: "Alerts", icon: Bell, badge: "5" },
  { label: "Investigations", icon: Search },
  { label: "Network Health", icon: HeartPulse },
  { label: "Judge Probe", icon: FlaskConical },
];

function Sidebar() {
  return (
    <aside className="hidden w-[176px] shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-3 py-5 text-sidebar-foreground lg:flex">
      <div className="flex items-center gap-2 px-2">
        <div className="flex size-10 items-center justify-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground shadow-logo">
          <ShieldCheck className="size-6" strokeWidth={2.4} />
        </div>
        <div>
          <p className="text-base font-extrabold leading-none text-sidebar-foreground">SkyGuard <span className="text-sidebar-highlight">AI</span></p>
          <p className="mt-1 text-[8px] font-semibold uppercase tracking-[0.12em] text-sidebar-muted">Climate intelligence</p>
        </div>
      </div>
      <p className="mt-3 px-2 text-[10px] font-medium text-sidebar-muted">Trusted Data. Safer Tomorrow.</p>

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
            {item.badge && <span className="ml-auto rounded-full bg-anomaly px-1.5 py-0.5 text-[9px] text-anomaly-foreground">{item.badge}</span>}
          </Button>
        ))}
      </nav>
    </aside>
  );
}

function Header({ theme, onThemeChange }: { theme: Theme; onThemeChange: (theme: Theme) => void }) {
  return (
    <header className="flex h-[72px] shrink-0 items-center justify-between px-5">
      <div>
        <h1 className="text-[25px] font-extrabold leading-tight text-foreground">Live Overview</h1>
        <p className="text-xs font-medium text-muted-foreground">National weather station monitoring and anomaly intelligence</p>
      </div>
      <div className="flex items-center gap-2">
        <span className="status-pill bg-success-soft text-success-deep"><span className="status-dot bg-success" />System Online</span>
        <span className="status-pill bg-info-soft text-info"><Activity className="size-3.5" />Simulation Data</span>
        <div role="group" aria-label="Color theme" className="ml-1 flex items-center rounded-full border border-border bg-card p-1 shadow-soft">
          <button
            type="button"
            onClick={() => onThemeChange("light")}
            aria-pressed={theme === "light"}
            aria-label="Light mode"
            title="Light mode"
            className={cn(
              "flex size-7 cursor-pointer items-center justify-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              theme === "light" ? "bg-info-soft text-info" : "text-muted-foreground hover:text-foreground",
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
              theme === "dark" ? "bg-info-soft text-info" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Moon className="size-4" />
          </button>
        </div>
      </div>
    </header>
  );
}

const kpis: Array<{ label: string; value: string; icon: ComponentType<{ className?: string }>; tone: string }> = [
  { label: "Stations Monitored", value: "124", icon: RadioTower, tone: "bg-sky-soft text-sky" },
  { label: "Healthy", value: "118", icon: ShieldCheck, tone: "bg-success-soft text-success" },
  { label: "Needs Review", value: "5", icon: AlertTriangle, tone: "bg-warning-soft text-warning" },
  { label: "Offline", value: "1", icon: WifiOff, tone: "bg-offline-soft text-offline" },
  { label: "Network Health", value: "96%", icon: HeartPulse, tone: "bg-info-soft text-info" },
];

function KpiRow() {
  return (
    <section className="grid shrink-0 grid-cols-5 gap-2.5" aria-label="Network summary">
      {kpis.map((kpi) => (
        <article key={kpi.label} className="metric-card">
          <span className={cn("flex size-9 items-center justify-center rounded-xl", kpi.tone)}><kpi.icon className="size-[18px]" /></span>
          <div><p className="text-[10px] font-semibold text-muted-foreground">{kpi.label}</p><p className="text-lg font-extrabold leading-tight">{kpi.value}</p></div>
        </article>
      ))}
    </section>
  );
}

function MapLab({ selectedStation, onSelectStation }: { selectedStation: Station | null; onSelectStation: (station: Station) => void }) {
  return (
    <section className="map-card relative min-h-[440px] overflow-hidden xl:min-h-0" aria-label="India weather station network">
      <div className="absolute left-4 top-4 z-20 flex items-center gap-2 rounded-xl border border-border bg-card/95 px-3 py-2 shadow-soft backdrop-blur-sm">
        <CloudSun className="size-4 text-sky" />
        <div><p className="text-[10px] font-extrabold uppercase tracking-[0.08em]">India Climate Network</p><p className="text-[9px] text-muted-foreground">Live station confidence layer</p></div>
      </div>

      <div className="map-stage absolute inset-0 flex items-center justify-center">
        <div className="map-world relative">
          <img src={indiaAsset.url} alt="Soft 3D map of India with weather stations, terrain, clouds and environmental landmarks" className="h-full w-full object-contain" />
          {stations.map((station) => (
            <Button
              key={station.id}
              variant="mapPin"
              size="icon"
              aria-label={`Select ${station.city} station, ${statusLabels[station.status]}`}
              title={`${station.city} · ${station.id}`}
              onClick={() => onSelectStation(station)}
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
          <div className="flex items-center justify-between"><p className="text-xs font-extrabold">{selectedStation.id}</p><StatusBadge status={selectedStation.status} /></div>
          <p className="mt-1 text-[10px] text-muted-foreground">{selectedStation.city} station</p>
          <div className="mt-2 flex items-end justify-between"><span className="text-[10px] text-muted-foreground">Current reading</span><strong className="text-base">{selectedStation.temperature}</strong></div>
        </div>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: Status }) {
  return <span className={cn("status-badge", `status-${status}`)}><span className="status-dot" />{statusLabels[status]}</span>;
}

function InvestigationPanel({ selectedAlert }: { selectedAlert: AlertItem }) {
  const [actionNotice, setActionNotice] = useState("");

  useEffect(() => {
    setActionNotice("");
  }, [selectedAlert?.stationId]);

    return (
      <aside className="panel min-h-0 overflow-y-auto p-3.5" aria-label="Investigation panel">
        <div className="flex items-start justify-between gap-2">
          <div><p className="section-kicker">{selectedAlert.stationId} / Investigation</p><h2 className="mt-0.5 text-sm font-extrabold">{selectedAlert.event}</h2></div>
          <span className={cn("status-badge shrink-0", selectedAlert.status === "offline" ? "status-offline" : "status-review")}><span className="status-dot" />{selectedAlert.reviewLabel}</span>
        </div>
        <div className="mt-2.5 grid grid-cols-3 gap-1.5">
          <DetailStat label={selectedAlert.recorded.label} value={selectedAlert.recorded.value} emphasis tone="bg-anomaly-soft" />
          <DetailStat label={selectedAlert.comparison.label} value={selectedAlert.comparison.value} tone="bg-surface-blue-tint" />
          <DetailStat label={selectedAlert.difference.label} value={selectedAlert.difference.value} tone="bg-surface-blue-tint" valueTone="text-info" />
        </div>
        <div className="mt-2.5 rounded-xl border border-border p-2.5">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">Why this needs review</p>
          <div className="mt-1.5 space-y-1.5">
            {selectedAlert.evidence.map((item, index) => (
              <div key={item.title} className="flex gap-2">
                <span className={cn("mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full text-[8px] font-extrabold", index === 0 ? "bg-warning-soft text-warning-deep" : "bg-info-soft text-info")}>{index + 1}</span>
                <p className="text-[9px] leading-snug"><strong className="block text-foreground">{item.title}</strong><span className="text-muted-foreground">{item.detail}</span></p>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-2.5 rounded-xl border border-border p-2.5">
          <div className="flex items-start justify-between gap-2"><p className="text-[9px] font-extrabold uppercase tracking-[0.04em]">{selectedAlert.historyTitle}</p><div className="flex flex-wrap justify-end gap-x-2 gap-y-1 text-[7px] font-semibold text-muted-foreground"><span className="flex items-center gap-1"><i className="size-1.5 rounded-full bg-anomaly" />{selectedAlert.historyLabels.recorded}</span><span className="flex items-center gap-1"><i className="size-1.5 rounded-full bg-info" />{selectedAlert.historyLabels.context}</span></div></div>
          <div className="mt-1 h-[72px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={selectedAlert.history} margin={{ top: 4, right: 3, bottom: 0, left: 3 }}>
                <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                <XAxis dataKey="time" tick={{ fontSize: 7, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
                <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
                <Line type="monotone" dataKey="context" stroke="var(--chart-context)" strokeDasharray="4 3" dot={false} strokeWidth={1.5} isAnimationActive={false} />
                <Line type="monotone" dataKey="recorded" stroke="var(--chart-alert)" dot={false} strokeWidth={2.5} connectNulls={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className={cn("mt-2.5 flex items-start gap-2 rounded-xl border p-2.5", selectedAlert.status === "offline" ? "border-offline/30 bg-offline-soft text-offline" : "border-warning/30 bg-warning-soft text-warning")}>
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <p className="text-[9px] leading-snug"><strong className={cn("block", selectedAlert.status === "offline" ? "text-offline-deep" : "text-warning-deep")}>{selectedAlert.outcome}</strong><span className="text-muted-foreground">{selectedAlert.statusMessage}</span></p>
        </div>
        <div className="mt-2.5 grid grid-cols-2 gap-2">
          <Button size="sm" onClick={() => setActionNotice("Investigation opened in simulation mode.")}><ArrowUpRight />Open investigation</Button>
          <Button variant="outline" size="sm" onClick={() => setActionNotice(`${selectedAlert.stationId} is highlighted on the map.`)}><Eye />View station</Button>
        </div>
        {actionNotice && <p className="mt-2 text-center text-[8px] font-semibold text-info" role="status">{actionNotice}</p>}
      </aside>
    );
}

function RecentAlerts({ selectedAlert, onSelectAlert }: { selectedAlert: AlertItem; onSelectAlert: (alert: AlertItem) => void }) {
  return (
    <section className="panel shrink-0 p-4" aria-label="Recent alerts">
      <div className="flex items-center justify-between gap-2">
        <div><p className="section-kicker">Attention queue</p><h2 className="mt-1 text-lg font-extrabold">Recent Alerts</h2></div>
        <span className="flex size-8 items-center justify-center rounded-xl bg-anomaly-soft text-anomaly"><Bell className="size-4" /></span>
      </div>
      <div className="mt-3 grid grid-cols-[88px_minmax(0,1fr)_104px_128px_60px] gap-2 px-2.5 text-[9px] font-extrabold uppercase tracking-[0.08em] text-muted-foreground" aria-hidden="true">
        <span>Station</span><span>Event</span><span>Reading</span><span>Status</span><span className="text-right">Time</span>
      </div>
      <div className="mt-1.5 space-y-1.5">
        {alerts.map((alert) => {
          const selected = selectedAlert.stationId === alert.stationId;
          return (
            <button
              key={alert.stationId}
              type="button"
              onClick={() => onSelectAlert(alert)}
              aria-pressed={selected}
              className={cn(
                "grid w-full cursor-pointer grid-cols-[88px_minmax(0,1fr)_104px_128px_60px] items-center gap-2 rounded-xl border px-2.5 py-2 text-left transition-colors",
                selected ? "border-primary/50 bg-info-soft" : "border-border bg-card hover:border-primary/30 hover:bg-info-soft/50",
              )}
            >
              <strong className="text-[11px] font-extrabold">{alert.stationId}</strong>
              <span className="truncate text-[11px] font-semibold text-muted-foreground">{alert.event}</span>
              <strong className="text-xs font-extrabold">{alert.status === "offline" ? "—" : alert.recorded.value}</strong>
              <span><StatusBadge status={alert.status} /></span>
              <time className="text-right text-[10px] font-medium text-muted-foreground">{alert.time}</time>
            </button>
          );
        })}
      </div>
      <div className="mt-3 rounded-xl bg-success-soft px-3 py-2.5"><p className="text-[10px] font-bold text-success-deep">118 stations are reporting normally</p><p className="mt-0.5 text-[9px] text-muted-foreground">Last network check completed 28 seconds ago.</p></div>
    </section>
  );
}

function DetailStat({ label, value, emphasis = false, tone, valueTone }: { label: string; value: string; emphasis?: boolean; tone?: string; valueTone?: string }) {
  return <div className={cn("min-w-0 rounded-xl p-2", tone ?? (emphasis ? "bg-anomaly-soft" : "bg-muted"))}><p className="text-[7px] font-semibold leading-tight text-muted-foreground">{label}</p><p className={cn("mt-1 break-words text-[11px] font-extrabold leading-tight", valueTone ?? (emphasis && "text-anomaly"))}>{value}</p></div>;
}

const sensorCards = [
  { title: "Temperature", value: "24.8°C", change: "↑ 0.6°C", icon: Thermometer, key: "temperature" as const, color: "var(--chart-alert)", tone: "bg-anomaly-soft text-anomaly" },
  { title: "Pressure", value: "1008.3 hPa", change: "↓ 1.2%", icon: Gauge, key: "pressure" as const, color: "var(--chart-blue)", tone: "bg-info-soft text-info" },
  { title: "Humidity", value: "56%", change: "↑ 2%", icon: Droplets, key: "humidity" as const, color: "var(--chart-green)", tone: "bg-success-soft text-success" },
];

function BottomInsights() {
  return (
    <section className="grid h-[154px] shrink-0 grid-cols-[minmax(0,1.2fr)_minmax(330px,.8fr)] gap-3" aria-label="Sensor and activity insights">
      <div className="grid grid-cols-3 gap-2.5">
        {sensorCards.map((sensor) => (
          <article key={sensor.title} className="panel flex min-w-0 flex-col p-3">
            <div className="flex items-center gap-2"><span className={cn("flex size-8 items-center justify-center rounded-xl", sensor.tone)}><sensor.icon className="size-4" /></span><div><p className="text-[9px] font-semibold text-muted-foreground">{sensor.title}</p><p className="text-sm font-extrabold">{sensor.value}</p></div><span className="ml-auto text-[9px] font-bold text-success-deep">{sensor.change}</span></div>
            <div className="mt-1 min-h-0 flex-1">
              <ResponsiveContainer width="100%" height="100%"><AreaChart data={sparkData[sensor.key].map((value, index) => ({ index, value }))}><defs><linearGradient id={`fill-${sensor.key}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={sensor.color} stopOpacity={0.28} /><stop offset="100%" stopColor={sensor.color} stopOpacity={0.02} /></linearGradient></defs><Area type="monotone" dataKey="value" stroke={sensor.color} strokeWidth={2.2} fill={`url(#fill-${sensor.key})`} dot={false} isAnimationActive={false} /></AreaChart></ResponsiveContainer>
            </div>
          </article>
        ))}
      </div>
      <article className="panel flex min-w-0 flex-col p-3">
        <div className="flex items-center justify-between"><div><p className="text-xs font-extrabold">Network Activity</p><p className="text-[9px] text-muted-foreground">Reports processed over 24 hours</p></div><div className="flex items-center gap-3 text-[9px] font-semibold text-muted-foreground"><span className="flex items-center gap-1"><i className="size-2 rounded-sm bg-sky" />Received</span><span className="flex items-center gap-1"><i className="size-2 rounded-sm bg-success" />Trusted</span></div></div>
        <div className="mt-1 min-h-0 flex-1"><ResponsiveContainer width="100%" height="100%"><BarChart data={activityData} barGap={2}><CartesianGrid stroke="var(--chart-grid)" vertical={false} /><XAxis dataKey="time" tick={{ fontSize: 8, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} /><YAxis hide /><Tooltip cursor={{ fill: "var(--chart-hover)" }} contentStyle={{ borderRadius: 10, borderColor: "var(--border)", fontSize: 10, backgroundColor: "var(--card)", color: "var(--card-foreground)" }} /><Bar dataKey="reports" fill="var(--chart-blue)" radius={[3,3,0,0]} isAnimationActive={false} /><Bar dataKey="verified" fill="var(--chart-green)" radius={[3,3,0,0]} isAnimationActive={false} /></BarChart></ResponsiveContainer></div>
      </article>
    </section>
  );
}