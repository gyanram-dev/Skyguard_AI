import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/common";
import { StationTable } from "@/components/tables";
import { KpiRow } from "@/components/kpi";
import { cn } from "@/lib/utils";
import { normalizeStatus, type DisplayStatus } from "@/lib/api";
import { errorMessage, formatDateTime } from "@/lib/format";
import { useNetworkSummary, useStations } from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/network-health")({
  head: () => ({
    meta: [{ title: "Network Health | SkyGuard AI" }],
  }),
  component: NetworkHealthPage,
});

type StatusFilter = "all" | DisplayStatus;

const statusFilters: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "healthy", label: "Healthy" },
  { value: "review", label: "Needs review" },
  { value: "anomaly", label: "Anomaly" },
  { value: "historical", label: "Historical only" },
  { value: "offline", label: "Offline" },
];

const distributionTone: Record<DisplayStatus, string> = {
  healthy: "bg-success",
  review: "bg-warning",
  anomaly: "bg-anomaly",
  offline: "bg-offline",
  historical: "bg-muted-foreground/40",
};

const distributionLabel: Record<DisplayStatus, string> = {
  healthy: "Healthy",
  review: "Needs review",
  anomaly: "Anomaly",
  offline: "Offline",
  historical: "Historical only",
};

function NetworkHealthPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const networkQuery = useNetworkSummary();
  const stationsQuery = useStations();

  const stations = useMemo(() => stationsQuery.data?.stations ?? [], [stationsQuery.data]);

  const distribution = useMemo(() => {
    const counts: Record<DisplayStatus, number> = {
      healthy: 0,
      review: 0,
      anomaly: 0,
      offline: 0,
      historical: 0,
    };
    for (const station of stations) {
      counts[normalizeStatus(station.status, station.data_available)] += 1;
    }
    const total = stations.length;
    return (Object.keys(counts) as DisplayStatus[]).map((status) => ({
      status,
      count: counts[status],
      pct: total > 0 ? (counts[status] / total) * 100 : 0,
    }));
  }, [stations]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return stations.filter((station) => {
      const status = normalizeStatus(station.status, station.data_available);
      if (statusFilter !== "all" && status !== statusFilter) return false;
      if (term === "") return true;
      return (
        station.station_id.toLowerCase().includes(term) || station.city.toLowerCase().includes(term)
      );
    });
  }, [stations, search, statusFilter]);

  const filtersActive = search.trim() !== "" || statusFilter !== "all";

  return (
    <>
      <KpiRow
        summary={networkQuery.data}
        loading={networkQuery.isPending}
        error={networkQuery.isError ? errorMessage(networkQuery.error) : null}
      />

      <section className="panel p-4" aria-label="Health distribution">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="section-kicker">Station health distribution</p>
            <h2 className="mt-1 text-lg font-extrabold">Network Composition</h2>
          </div>
          <p className="text-[10px] text-muted-foreground">
            Last updated:{" "}
            {networkQuery.data ? formatDateTime(networkQuery.data.last_updated) : "Not available"}
          </p>
          {networkQuery.data ? (
            <p className="text-[10px] text-muted-foreground">
              Indian operational network: {networkQuery.data.detector_covered} station(s) with
              detector coverage ({networkQuery.data.indian_operational_healthy} healthy);{" "}
              {networkQuery.data.indian_operational_context_only} historical-only station(s) carry
              observations but have no detector. Benchmark stations excluded.
            </p>
          ) : null}
        </div>
        {stationsQuery.isPending ? (
          <p className="mt-3 text-[11px] text-muted-foreground" role="status">
            Loading station statuses…
          </p>
        ) : stationsQuery.isError ? (
          <div className="mt-3">
            <ErrorState
              message={errorMessage(stationsQuery.error)}
              onRetry={() => stationsQuery.refetch()}
            />
          </div>
        ) : (
          <div className="mt-3 space-y-2">
            {distribution.map((entry) => (
              <div key={entry.status} className="flex items-center gap-2">
                <span className="w-[92px] shrink-0 text-[11px] font-bold">
                  {distributionLabel[entry.status]}
                </span>
                <div className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn("h-full rounded-full", distributionTone[entry.status])}
                    style={{ width: `${entry.pct}%` }}
                  />
                </div>
                <span className="w-[64px] shrink-0 text-right text-[11px] font-extrabold">
                  {entry.count} · {entry.pct.toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel flex flex-wrap items-center gap-2 p-3" aria-label="Station filters">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by station ID or city…"
            aria-label="Search stations"
            className="pl-8"
          />
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Status filter">
          {statusFilters.map((filter) => (
            <Button
              key={filter.value}
              size="sm"
              variant={statusFilter === filter.value ? "default" : "outline"}
              onClick={() => setStatusFilter(filter.value)}
              aria-pressed={statusFilter === filter.value}
              className={cn(statusFilter !== filter.value && "bg-card")}
            >
              {filter.label}
            </Button>
          ))}
        </div>
        {filtersActive && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setSearch("");
              setStatusFilter("all");
            }}
          >
            <X />
            Clear
          </Button>
        )}
      </section>

      {stationsQuery.isPending && <LoadingState message="Loading station health…" />}
      {stationsQuery.isError && (
        <ErrorState
          message={errorMessage(stationsQuery.error)}
          onRetry={() => stationsQuery.refetch()}
        />
      )}
      {!stationsQuery.isPending && !stationsQuery.isError && filtered.length === 0 && (
        <EmptyState
          title="No stations match"
          message={
            stations.length === 0
              ? "The API returned no stations."
              : "No stations match the current search and filters."
          }
        />
      )}
      {!stationsQuery.isPending && !stationsQuery.isError && filtered.length > 0 && (
        <StationTable stations={filtered} />
      )}

      <section className="panel p-4" aria-label="Network activity note">
        <p className="text-[11px] font-bold">Network activity history</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          Network activity history is not provided by the current API in historical replay.
        </p>
      </section>
    </>
  );
}
