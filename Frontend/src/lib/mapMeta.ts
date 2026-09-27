import { normalizeStatus, type DisplayStatus, type StationSummary } from "@/lib/api";
import { formatTemp } from "@/lib/format";

// ---------------------------------------------------------------------------
// Visual configuration only. Positions, ids and display names for the India
// map are local UI config — every status/reading comes from the API.
// JENA-01 is backend-only and intentionally has no map entry.
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
  { id: "AMD-06", city: "Ahmedabad", x: 27.2, y: 43.7 },
  { id: "BHO-08", city: "Bhopal", x: 45.2, y: 45.3 },
  { id: "MUM-03", city: "Mumbai", x: 30.2, y: 56.1 },
  { id: "HYD-07", city: "Hyderabad", x: 44.2, y: 66.2 },
  { id: "BLR-05", city: "Bengaluru", x: 44.8, y: 81.3 },
  { id: "CHE-03", city: "Chennai", x: 62.1, y: 81.2 },
  { id: "KOL-02", city: "Kolkata", x: 77.7, y: 47.4 },
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

/** Display city for any backend station id (map meta first, API row next). */
export function cityForStationId(stationId: string, stations: StationSummary[]): string | null {
  const meta = stationMapMeta.find((entry) => entry.id === stationId);
  if (meta) return meta.city;
  return stations.find((station) => station.station_id === stationId)?.city ?? null;
}
