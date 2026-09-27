import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { normalizeStatus, type DisplayStatus } from "@/lib/api";
import { errorMessage } from "@/lib/format";
import { useStations } from "@/hooks/useSkyguard";
import {
  EmptyBlock,
  ErrorBlock,
  FilterPills,
  LoadingBlock,
  SearchField,
  SectionCard,
  StatusBadge,
} from "@/components/shared";
import { StationTable } from "@/components/StationTable";

export const Route = createFileRoute("/_app/stations")({
  head: () => ({
    meta: [{ title: "Stations | SkyGuard AI" }],
  }),
  component: StationsPage,
});

type StatusFilter = "all" | DisplayStatus;

const STATUS_OPTIONS: Array<{ value: StatusFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "healthy", label: "Healthy" },
  { value: "review", label: "Needs review" },
  { value: "anomaly", label: "Anomaly" },
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
    };
    for (const station of stations) {
      result[normalizeStatus(station.status, station.data_available)] += 1;
    }
    return result;
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

  const hasFilters = search.trim() !== "" || statusFilter !== "all";

  return (
    <>
      <SectionCard
        title={`Station Network · ${stationsQuery.data ? stations.length : "…"}`}
        subtitle="Every reading below comes from the FastAPI backend in historical replay."
        action={
          !stationsQuery.isPending &&
          !stationsQuery.isError && (
            <div className="flex flex-wrap justify-end gap-1.5">
              {(Object.keys(counts) as DisplayStatus[]).map((status) => (
                <span key={status} className="flex items-center gap-1.5">
                  <StatusBadge status={status} />
                  <strong className="text-[11px] text-foreground">{counts[status]}</strong>
                </span>
              ))}
            </div>
          )
        }
      >
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <SearchField
              value={search}
              onChange={setSearch}
              placeholder="Search by station ID or city…"
              label="Search stations"
            />
          </div>
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
      </SectionCard>

      <SectionCard title="Stations" subtitle="Select a station to open its detail view.">
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
            message={
              hasFilters
                ? "No stations match the current search or filter. Clear the filters to see the full network."
                : "The backend returned an empty station list."
            }
          />
        )}
        {filtered.length > 0 && <StationTable stations={filtered} variant="full" />}
      </SectionCard>
    </>
  );
}
