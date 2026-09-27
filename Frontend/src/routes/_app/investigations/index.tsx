import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState, ErrorState, LoadingState } from "@/components/common";
import { AlertTable } from "@/components/tables";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/lib/format";
import { alertFilters, filterAlerts, type AlertFilter } from "@/lib/alerts";
import { useAlerts } from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/investigations/")({
  head: () => ({
    meta: [{ title: "Investigations | SkyGuard AI" }],
  }),
  component: InvestigationsPage,
});

function InvestigationsPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<AlertFilter>("all");
  const [stationFilter, setStationFilter] = useState("all");
  const alertsQuery = useAlerts(1000);

  const alerts = useMemo(() => alertsQuery.data?.alerts ?? [], [alertsQuery.data]);

  const stationOptions = useMemo(() => {
    const ids = new Set(alerts.map((alert) => alert.station_id));
    return ["all", ...Array.from(ids).sort()];
  }, [alerts]);

  const filtered = useMemo(
    () => filterAlerts(alerts, search, statusFilter, stationFilter),
    [alerts, search, statusFilter, stationFilter],
  );

  const filtersActive = search.trim() !== "" || statusFilter !== "all" || stationFilter !== "all";

  return (
    <>
      <section
        className="panel flex flex-wrap items-center gap-2 p-3"
        aria-label="Investigation summary"
      >
        <p className="text-xs font-extrabold">
          {alertsQuery.isPending ? "…" : alerts.length} investigation candidates
        </p>
        <span className="ml-auto text-[10px] text-muted-foreground">
          Historical replay · each row opens a full explanation workspace
        </span>
      </section>

      <section
        className="panel flex flex-wrap items-center gap-2 p-3"
        aria-label="Investigation filters"
      >
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by station, event or root cause…"
            aria-label="Search investigations"
            className="pl-8"
          />
        </div>
        <Select value={stationFilter} onValueChange={setStationFilter}>
          <SelectTrigger className="w-[160px]" aria-label="Station filter">
            <SelectValue placeholder="Station" />
          </SelectTrigger>
          <SelectContent>
            {stationOptions.map((option) => (
              <SelectItem key={option} value={option}>
                {option === "all" ? "All stations" : option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Status filter">
          {alertFilters.map((filter) => (
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
              setStationFilter("all");
            }}
          >
            <X />
            Clear
          </Button>
        )}
      </section>

      {alertsQuery.isPending && <LoadingState message="Loading investigation candidates…" />}
      {alertsQuery.isError && (
        <ErrorState
          message={errorMessage(alertsQuery.error)}
          onRetry={() => alertsQuery.refetch()}
        />
      )}
      {!alertsQuery.isPending && !alertsQuery.isError && filtered.length === 0 && (
        <EmptyState
          title="No investigations match"
          message={
            alerts.length === 0
              ? "The API returned no alerts to investigate."
              : "No investigation candidates match the current search and filters."
          }
        />
      )}
      {!alertsQuery.isPending && !alertsQuery.isError && filtered.length > 0 && (
        <AlertTable alerts={filtered} basePath="/investigations/$alertId" />
      )}
    </>
  );
}
