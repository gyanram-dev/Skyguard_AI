import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/common";
import { AlertTable } from "@/components/tables";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/lib/format";
import { alertFilters, filterAlerts, type AlertFilter } from "@/lib/alerts";
import { useAlerts } from "@/hooks/useSkyguard";

export const Route = createFileRoute("/_app/alerts/")({
  head: () => ({
    meta: [{ title: "Alerts | SkyGuard AI" }],
  }),
  component: AlertsPage,
});

function AlertsPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<AlertFilter>("all");
  const alertsQuery = useAlerts(1000);

  const alerts = useMemo(() => alertsQuery.data?.alerts ?? [], [alertsQuery.data]);
  const filtered = useMemo(
    () => filterAlerts(alerts, search, statusFilter),
    [alerts, search, statusFilter],
  );

  const filtersActive = search.trim() !== "" || statusFilter !== "all";

  return (
    <>
      <section className="panel flex flex-wrap items-center gap-2 p-3" aria-label="Alert summary">
        <p className="text-xs font-extrabold">
          {alertsQuery.isPending ? "…" : alerts.length} alerts
        </p>
        <span className="ml-auto text-[10px] text-muted-foreground">
          Historical replay · click a row for alert detail
        </span>
      </section>

      <section className="panel flex flex-wrap items-center gap-2 p-3" aria-label="Alert filters">
        <div className="relative min-w-[200px] flex-1">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by station, event or root cause…"
            aria-label="Search alerts"
            className="pl-8"
          />
        </div>
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
            }}
          >
            <X />
            Clear
          </Button>
        )}
      </section>

      {alertsQuery.isPending && <LoadingState message="Loading alerts from the API…" />}
      {alertsQuery.isError && (
        <ErrorState
          message={errorMessage(alertsQuery.error)}
          onRetry={() => alertsQuery.refetch()}
        />
      )}
      {!alertsQuery.isPending && !alertsQuery.isError && filtered.length === 0 && (
        <EmptyState
          title="No alerts match"
          message={
            alerts.length === 0
              ? "The API returned no alerts."
              : "No alerts match the current search and filters."
          }
        />
      )}
      {!alertsQuery.isPending && !alertsQuery.isError && filtered.length > 0 && (
        <AlertTable alerts={filtered} basePath="/alerts/$alertId" />
      )}
    </>
  );
}
