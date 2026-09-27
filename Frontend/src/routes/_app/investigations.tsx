import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { useAlerts } from "@/hooks/useSkyguard";
import { errorMessage } from "@/lib/format";
import { filterAlerts, type AlertFilter } from "@/lib/alerts";
import {
  EmptyBlock,
  ErrorBlock,
  FilterPills,
  LoadingBlock,
  SearchField,
  SectionCard,
} from "@/components/shared";
import { AlertListHeader, AlertRow } from "@/components/AlertRow";

export const Route = createFileRoute("/_app/investigations")({
  head: () => ({
    meta: [{ title: "Investigations | SkyGuard AI" }],
  }),
  component: InvestigationsPage,
});

const FILTER_OPTIONS: Array<{ value: AlertFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "anomaly", label: "Anomaly" },
  { value: "review", label: "Needs review" },
  { value: "offline", label: "Offline / availability" },
];

function InvestigationsPage() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<AlertFilter>("all");
  const [stationFilter, setStationFilter] = useState("all");
  const alertsQuery = useAlerts();

  const alerts = useMemo(() => alertsQuery.data?.alerts ?? [], [alertsQuery.data]);

  const stationOptions = useMemo(() => {
    const stations = [...new Set(alerts.map((alert) => alert.station_id))].sort();
    return [
      { value: "all", label: "All stations" },
      ...stations.map((id) => ({ value: id, label: id })),
    ];
  }, [alerts]);

  const filtered = useMemo(() => {
    const base = filterAlerts(alerts, search, filter);
    if (stationFilter === "all") return base;
    return base.filter((alert) => alert.station_id === stationFilter);
  }, [alerts, search, filter, stationFilter]);

  const hasFilters = search.trim() !== "" || filter !== "all" || stationFilter !== "all";

  return (
    <>
      <SectionCard
        title={`Investigation Queue · ${alertsQuery.data ? alerts.length : "…"}`}
        subtitle="Alerts presented as investigation candidates. Select one to open its workspace."
      >
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <SearchField
              value={search}
              onChange={setSearch}
              placeholder="Search by station, event, or root cause…"
              label="Search investigations"
            />
            <label className="flex shrink-0 items-center gap-2 text-[10px] font-bold text-muted-foreground">
              Station
              <select
                value={stationFilter}
                onChange={(event) => setStationFilter(event.target.value)}
                className="h-8 cursor-pointer rounded-md border border-input bg-card px-2 text-xs font-semibold text-foreground"
              >
                {stationOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <FilterPills options={FILTER_OPTIONS} value={filter} onChange={setFilter} />
            {hasFilters && (
              <button
                type="button"
                onClick={() => {
                  setSearch("");
                  setFilter("all");
                  setStationFilter("all");
                }}
                className="cursor-pointer text-[10px] font-bold text-info hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Candidates" subtitle="Each candidate opens a full diagnosis workspace.">
        {alertsQuery.isPending && <LoadingBlock label="Loading investigation candidates…" />}
        {alertsQuery.isError && (
          <ErrorBlock
            message={errorMessage(alertsQuery.error)}
            onRetry={() => alertsQuery.refetch()}
          />
        )}
        {!alertsQuery.isPending && !alertsQuery.isError && filtered.length === 0 && (
          <EmptyBlock
            title="No investigations match"
            message={
              hasFilters
                ? "No candidates match the current search or filters. Clear the filters to see the full queue."
                : "The backend returned an empty alert queue."
            }
          />
        )}
        {filtered.length > 0 && (
          <>
            <AlertListHeader />
            <div className="mt-1.5 space-y-1.5">
              {filtered.map((alert) => (
                <AlertRow
                  key={alert.alert_id}
                  alert={alert}
                  selected={false}
                  to="/investigations/$alertId"
                />
              ))}
            </div>
          </>
        )}
      </SectionCard>
    </>
  );
}
