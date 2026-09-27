import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { errorMessage } from "@/lib/format";
import { useAlerts } from "@/hooks/useSkyguard";
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

export const Route = createFileRoute("/_app/alerts")({
  head: () => ({
    meta: [{ title: "Alerts | SkyGuard AI" }],
  }),
  component: AlertsPage,
});

const FILTER_OPTIONS: Array<{ value: AlertFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "anomaly", label: "Anomaly" },
  { value: "review", label: "Needs review" },
  { value: "offline", label: "Offline / availability" },
];

function AlertsPage() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<AlertFilter>("all");
  const alertsQuery = useAlerts();

  const alerts = useMemo(() => alertsQuery.data?.alerts ?? [], [alertsQuery.data]);
  const filtered = useMemo(() => filterAlerts(alerts, search, filter), [alerts, search, filter]);
  const hasFilters = search.trim() !== "" || filter !== "all";

  return (
    <>
      <SectionCard
        title={`Alert Center · ${alertsQuery.data ? alerts.length : "…"}`}
        subtitle="Detected anomalies and data availability events from the backend queue."
      >
        <div className="flex flex-col gap-2">
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder="Search by station, event, or root cause…"
            label="Search alerts"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <FilterPills options={FILTER_OPTIONS} value={filter} onChange={setFilter} />
            {hasFilters && (
              <button
                type="button"
                onClick={() => {
                  setSearch("");
                  setFilter("all");
                }}
                className="cursor-pointer text-[10px] font-bold text-info hover:underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Queue" subtitle="Select an alert to open its evidence view.">
        {alertsQuery.isPending && <LoadingBlock label="Loading alerts…" />}
        {alertsQuery.isError && (
          <ErrorBlock
            message={errorMessage(alertsQuery.error)}
            onRetry={() => alertsQuery.refetch()}
          />
        )}
        {!alertsQuery.isPending && !alertsQuery.isError && filtered.length === 0 && (
          <EmptyBlock
            title="No alerts match"
            message={
              hasFilters
                ? "No alerts match the current search or filter. Clear the filters to see the full queue."
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
                  to="/alerts/$alertId"
                />
              ))}
            </div>
          </>
        )}
      </SectionCard>
    </>
  );
}
