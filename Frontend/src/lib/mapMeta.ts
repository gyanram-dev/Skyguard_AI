import { normalizeStatus, type DisplayStatus, type StationSummary } from "@/lib/api";
import { formatTemp } from "@/lib/format";

// ---------------------------------------------------------------------------
// Visual configuration only. Positions, ids and display names for the India
// map are local UI config — every status/reading comes from the API.
// Only data-backed Indian network stations are represented here.
// ---------------------------------------------------------------------------

export type StationMapMeta = {
  id: string;
  city: string;
  x: number;
  y: number;
};

export const stationMapMeta: StationMapMeta[] = [
  { id: "DEL-01", city: "New Delhi", x: 42.3, y: 18.2 },
  { id: "JAI-02", city: "Jaipur", x: 34.1, y: 30.3 },
  { id: "LUCK-04", city: "Lucknow", x: 61.2, y: 34.4 },
  { id: "BHO-08", city: "Bhopal", x: 45.2, y: 45.3 },
  { id: "MUM-03", city: "Mumbai", x: 30.2, y: 56.1 },
  { id: "HYD-07", city: "Hyderabad", x: 44.2, y: 66.2 },
  { id: "PUN-10", city: "Pune", x: 34.0, y: 63.0 },
  { id: "BLR-05", city: "Bengaluru", x: 44.8, y: 81.3 },
  { id: "CHE-03", city: "Chennai", x: 62.1, y: 81.2 },
  { id: "KOL-02", city: "Kolkata", x: 77.7, y: 47.4 },
  { id: "CHD-09", city: "Chandigarh", x: 50.0, y: 22.0 },
  { id: "SAF-11", city: "Delhi (Safdarjung)", x: 44.0, y: 20.0 },
  { id: "GAU-12", city: "Guwahati", x: 83.5, y: 37.5 },
  { id: "TRV-13", city: "Thiruvananthapuram", x: 49.5, y: 94.0 },
];

export type MergedStation = StationMapMeta & {
  status: DisplayStatus;
  temperature: string;
  api: StationSummary | undefined;
};

/** Merge backend station rows into the visual map metadata (positions kept). */
export function mergeStations(stations: StationSummary[]): MergedStation[] {
  const byId = new Map(stations.map((station) => [station.station_id, station]));
  return stationMapMeta.map((meta) => {
    const api = byId.get(meta.id);
    return {
      ...meta,
      status: normalizeStatus(api?.status, api?.data_available ?? false),
      temperature: formatTemp(api?.temperature),
      api,
    };
  });
}

export type MapCapability = "full-tpr" | "partial" | "context-only";

/**
 * Detector coverage for map marker styling. Prefers the backend's explicit
 * Phase-25 `capability.detector_capability`; falls back to deriving from
 * probe_available + available_variables on older responses. Both agree:
 * only FULL_TPR stations get a detector verdict, CONTEXT_ONLY never does.
 */
export function stationMapCapability(api: StationSummary | undefined): MapCapability {
  const declared = api?.capability?.detector_capability;
  if (declared === "FULL_TPR") return "full-tpr";
  if (declared === "PARTIAL") return "partial";
  if (declared === "CONTEXT_ONLY" || declared === "UNAVAILABLE") return "context-only";
  if (!api?.probe_available) return "context-only";
  const variables = new Set(api.available_variables ?? []);
  return ["temperature", "pressure", "relative_humidity"].every((key) => variables.has(key))
    ? "full-tpr"
    : "partial";
}

/** Visible data-source provenance label (Phase 12) — never 'real-time'. */
export function stationSourceLabel(api: StationSummary | undefined): string {
  const declared = api?.capability?.data_source;
  if (declared) return declared;
  if (api?.source_dataset === "delhi_clean") return "Historical AWS dataset";
  if (api?.source_dataset === "noaa_ghcnh") return "NOAA GHCNh";
  return "Historical observations";
}

/** Display city for any backend station id (map meta first, API row next). */
export function cityForStationId(stationId: string, stations: StationSummary[]): string | null {
  const meta = stationMapMeta.find((entry) => entry.id === stationId);
  if (meta) return meta.city;
  return stations.find((station) => station.station_id === stationId)?.city ?? null;
}
