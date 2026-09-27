import { normalizeStatus, type DisplayStatus } from "@/lib/api";
import { cleanText } from "@/lib/format";

export type AlertFilter = "all" | DisplayStatus;

export const alertFilters: Array<{ value: AlertFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "anomaly", label: "Anomaly" },
  { value: "review", label: "Needs review" },
  { value: "offline", label: "Offline / availability" },
];

export type AlertLike = {
  station_id: string;
  event: string;
  root_cause: string | null;
  status: string;
};

/** Client-side filtering over loaded alert data (no backend search endpoint). */
export function filterAlerts<T extends AlertLike>(
  alerts: T[],
  search: string,
  statusFilter: AlertFilter,
  stationFilter = "all",
): T[] {
  const term = search.trim().toLowerCase();
  return alerts.filter((alert) => {
    const status = normalizeStatus(alert.status, true);
    if (statusFilter !== "all" && status !== statusFilter) return false;
    if (stationFilter !== "all" && alert.station_id !== stationFilter) return false;
    if (term === "") return true;
    return (
      alert.station_id.toLowerCase().includes(term) ||
      alert.event.toLowerCase().includes(term) ||
      (cleanText(alert.root_cause) ?? "").toLowerCase().includes(term)
    );
  });
}
