import { AlertTriangle, HeartPulse, RadioTower, ShieldCheck, WifiOff } from "lucide-react";
import type { ComponentType } from "react";

import { cn } from "@/lib/utils";
import type { NetworkSummary } from "@/lib/api";

/** Network KPI cards; values always come from /network/summary. */
export function KpiRow({
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
      <div className="grid shrink-0 grid-cols-2 gap-2.5 sm:grid-cols-3 xl:grid-cols-5">
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
