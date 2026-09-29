import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState, StatusBadge } from "@/components/common";
import { StationTable } from "@/components/tables";
import { cn } from "@/lib/utils";
import { normalizeStatus, type DisplayStatus } from "@/lib/api";
import { errorMessage } from "@/lib/format";
import { useStations } from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/stations/")({
  head: () => ({
    meta: [{ title: "Stations | SkyGuard AI" }],
  }),
  component: StationsPage,
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

function StationsPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const stationsQuery = useStations();

  const stations = useMemo(() => stationsQuery.data?.stations ?? [], [stationsQuery.data]);

  const counts = useMemo(() => {
    const result: Record<DisplayStatus, number> = {
      healthy: 0,
      review: 0,
      anomaly: 0,
      offline: 0,
      historical: 0,
    };
    for (const station of stations) {
      result[normalizeStatus(station.status, station.data_available)] += 1;
    }
    return result;
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
      <section className="panel flex flex-wrap items-center gap-2 p-3" aria-label="Station summary">
        <p className="text-xs font-extrabold">
          {stationsQuery.isPending ? "…" : stations.length} stations
        </p>
        {(Object.keys(counts) as DisplayStatus[]).map((status) => (
          <span key={status} className="flex items-center gap-1.5">
            <StatusBadge status={status} />
            <span className="text-[11px] font-extrabold">{counts[status]}</span>
          </span>
        ))}
        <span className="ml-auto text-[10px] text-muted-foreground">
          Historical replay · click a row for station detail
        </span>
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

      {stationsQuery.isPending && <LoadingState message="Loading stations from the API…" />}
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
    </>
  );
}
