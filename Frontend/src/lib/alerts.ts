import { normalizeStatus } from "@/lib/api";

export type AlertFilter = "all" | "anomaly" | "review" | "offline";

/** Client-side filtering over loaded API alert data (no backend search endpoint). */
export function filterAlerts<
  T extends { station_id: string; event: string; status: string; root_cause?: string | null },
>(alerts: T[], search: string, filter: AlertFilter): T[] {
  const needle = search.trim().toLowerCase();
  return alerts.filter((alert) => {
    if (filter !== "all" && normalizeStatus(alert.status, true) !== filter) return false;
    if (needle === "") return true;
    return (
      alert.station_id.toLowerCase().includes(needle) ||
      alert.event.toLowerCase().includes(needle) ||
      (alert.root_cause ?? "").toLowerCase().includes(needle)
    );
  });
}
