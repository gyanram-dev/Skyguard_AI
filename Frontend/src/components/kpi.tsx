import {
  AlertTriangle,
  Database,
  HeartPulse,
  History,
  RadioTower,
} from "lucide-react";
import type { ComponentType } from "react";

import { formatCompactCount } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { NetworkSummary } from "@/lib/api";

/**
 * Network KPI cards; values always come from /network/summary.
 *
 * Phase 9 headline numbers: stations, observations and capability counts.
 * There is deliberately NO "100% healthy" figure: health is scoped to the
 * detector-covered stations and shown as a detector-verdict count instead.
 */
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
  const observations = summary?.total_observations ?? summary?.observations_indexed;
  const kpis: Array<{
    label: string;
    value: string;
    note: string;
    icon: ComponentType<{ className?: string }>;
    tone: string;
  }> = [
    {
      label: "Indian Stations",
      value: value(summary?.total_stations ?? summary?.stations_monitored),
      note: "Historical observation network",
      icon: RadioTower,
      tone: "bg-sky-soft text-sky",
    },
    {
      label: "Historical Observations",
      value:
        loading || error
          ? "…"
          : (formatCompactCount(observations) ?? "—"),
      note: observations === undefined ? "Rows loaded" : `${observations.toLocaleString()} rows loaded`,
      icon: Database,
      tone: "bg-info-soft text-info",
    },
    {
      label: "Detector-ready (Full T/P/RH)",
      value: value(summary?.full_tpr_stations ?? summary?.detector_covered),
      note: "Delhi AWS — full T/P/RH detector coverage",
      icon: HeartPulse,
      tone: "bg-success-soft text-success",
    },
    {
      label: "Partial-data",
      value: value(summary?.partial_stations),
      note: "Detector-covered with missing variables",
      icon: AlertTriangle,
      tone: "bg-warning-soft text-warning",
    },
    {
      label: "Context-only",
      value: value(summary?.context_only_stations ?? summary?.context_only),
      note: "Real observations, no detector — no verdict",
      icon: History,
      tone: "bg-muted text-muted-foreground",
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
            <div className="min-w-0">
              <p className="text-[10px] font-semibold text-muted-foreground">{kpi.label}</p>
              <p className="text-lg font-extrabold leading-tight">{kpi.value}</p>
              <p
                className="truncate text-[8px] leading-tight text-muted-foreground"
                title={kpi.note}
              >
                {kpi.note}
              </p>
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
