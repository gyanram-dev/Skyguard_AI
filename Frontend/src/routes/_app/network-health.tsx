import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { DATA_MODE_HISTORICAL_REPLAY, normalizeStatus, type DisplayStatus } from "@/lib/api";
import { errorMessage, formatDateTime } from "@/lib/format";
import { useNetworkSummary, useStations } from "@/hooks/useSkyguard";
import {
  EmptyBlock,
  ErrorBlock,
  FilterPills,
  LoadingBlock,
  SearchField,
  SectionCard,
  StatusBadge,
} from "@/components/shared";
import { NetworkKpis } from "@/components/NetworkKpis";
import { StationTable } from "@/components/StationTable";

export const Route = createFileRoute("/_app/network-health")({
  head: () => ({
    meta: [{ title: "Network Health | SkyGuard AI" }],
  }),
  component: NetworkHealthPage,
});

type StatusFilter = "all" | DisplayStatus;

const STATUS_OPTIONS: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "healthy", label: "Healthy" },
  { value: "review", label: "Needs review" },
  { value: "anomaly", label: "Anomaly" },
  { value: "offline", label: "Offline" },
];

function NetworkHealthPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const networkQuery = useNetworkSummary();
  const stationsQuery = useStations();

  const stations = useMemo(() => stationsQuery.data?.stations ?? [], [stationsQuery.data]);

  const distribution = useMemo(() => {
    const counts: Record<DisplayStatus, number> = { healthy: 0, review: 0, anomaly: 0, offline: 0 };
    for (const station of stations) {
      counts[normalizeStatus(station.status, station.data_available)] += 1;
    }
    return counts;
  }, [stations]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return stations.filter((station) => {
      const status = normalizeStatus(station.status, station.data_available);
      if (statusFilter !== "all" && status !== statusFilter) return false;
      if (needle === "") return true;
      return (
        station.station_id.toLowerCase().includes(needle) ||
        station.city.toLowerCase().includes(needle)
      );
    });
  }, [stations, search, statusFilter]);

  const summary = networkQuery.data;
  const total = summary?.stations_monitored ?? stations.length;
  const barSegments: Array<{ status: DisplayStatus; count: number; bar: string }> = [
    { status: "healthy", count: summary?.healthy ?? distribution.healthy, bar: "bg-success" },
    { status: "review", count: summary?.needs_review ?? distribution.review, bar: "bg-warning" },
    { status: "anomaly", count: summary?.anomaly ?? distribution.anomaly, bar: "bg-anomaly" },
    { status: "offline", count: summary?.offline ?? distribution.offline, bar: "bg-offline" },
  ];
  const hasFilters = search.trim() !== "" || statusFilter !== "all";

  return (
    <>
      <NetworkKpis
        summary={summary}
        loading={networkQuery.isPending}
        error={networkQuery.isError ? errorMessage(networkQuery.error) : null}
      />

      <SectionCard
        title="Health distribution"
        subtitle={`Last updated ${formatDateTime(summary?.last_updated ?? null)} · ${
          summary?.data_mode === DATA_MODE_HISTORICAL_REPLAY
            ? "Historical replay"
            : (summary?.data_mode ?? "Connecting…")
        }`}
      >
        {networkQuery.isPending && <LoadingBlock label="Loading distribution…" />}
        {networkQuery.isError && <ErrorBlock message={errorMessage(networkQuery.error)} />}
        {!networkQuery.isPending && !networkQuery.isError && (
          <>
            <div
              className="flex h-3 w-full overflow-hidden rounded-full bg-muted"
              role="img"
              aria-label={`Station health: ${barSegments.map((s) => `${s.count} ${s.status}`).join(", ")}`}
            >
              {barSegments.map((segment) => {
                const width = total > 0 ? (segment.count / total) * 100 : 0;
                return (
                  <div
                    key={segment.status}
                    className={segment.bar}
                    style={{ width: `${width}%` }}
                    title={`${segment.status}: ${segment.count}`}
                  />
                );
              })}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
              {barSegments.map((segment) => (
                <span key={segment.status} className="flex items-center gap-1.5 text-[10px]">
                  <StatusBadge status={segment.status} />
                  <strong className="text-foreground">{segment.count}</strong>
                </span>
              ))}
            </div>
          </>
        )}
      </SectionCard>

      <SectionCard title="Station status" subtitle="Availability and trust per station.">
        <div className="flex flex-col gap-2">
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder="Search by station ID or city…"
            label="Search stations"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <FilterPills options={STATUS_OPTIONS} value={statusFilter} onChange={setStatusFilter} />
            {hasFilters && (
              <button
                type="button"
                onClick={() => {
                  setSearch("");
                  setStatusFilter("all");
                }}
                className="cursor-pointer text-[10px] font-bold text-info hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>
        <div className="mt-3">
          {stationsQuery.isPending && <LoadingBlock label="Loading stations…" />}
          {stationsQuery.isError && (
            <ErrorBlock
              message={errorMessage(stationsQuery.error)}
              onRetry={() => stationsQuery.refetch()}
            />
          )}
          {!stationsQuery.isPending && !stationsQuery.isError && filtered.length === 0 && (
            <EmptyBlock
              title="No stations match"
              message="No stations match the current search or filter."
            />
          )}
          {filtered.length > 0 && <StationTable stations={filtered} variant="compact" />}
        </div>
      </SectionCard>

      <SectionCard title="Network activity" subtitle="Reports processed over time">
        <p className="text-[11px] leading-snug text-muted-foreground">
          Network activity history is not provided by the current API — no data fabricated.
        </p>
      </SectionCard>
    </>
  );
}
