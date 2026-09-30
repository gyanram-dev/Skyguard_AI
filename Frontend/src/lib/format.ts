import { ApiError } from "@/lib/api";

/** Human-readable message for any query failure. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Request failed.";
}

/**
 * Backend string fields occasionally serialize a missing value as the literal
 * string "nan" (pandas NaN through str()). Treat those as missing so the UI
 * never renders "nan" text and falls back to honest empty states instead.
 */
export function cleanText(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const trimmed = value.trim();
  if (trimmed === "" || trimmed.toLowerCase() === "nan") return null;
  return value;
}

export function formatTemp(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(1)}°C`;
}

export function formatHumidity(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  return `${value.toFixed(1)}% RH`;
}

export function formatPressure(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  return `${value.toFixed(1)} hPa`;
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(3);
}

export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  return `${(value * 100).toFixed(0)}%`;
}

export function formatTime(iso: string | null | undefined): string {
  if (iso === null || iso === undefined || iso === "") return "—";
  const date = new Date(iso);
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }
  const match = iso.match(/(\d{2}):(\d{2})/);
  if (match) return `${match[1]}:${match[2]}`;
  return iso;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (iso === null || iso === undefined || iso === "") return "Not available";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/**
 * Presentation-only labels for backend enums, data_mode and provenance
 * values. The underlying backend value is never altered — only its display
 * form. Unknown values fall through unchanged.
 */
const DISPLAY_TERMS: Record<string, string> = {
  historical_replay: "Historical Replay",
  historical: "Historical data",
  full_tpr: "Full T/P/RH Detection",
  partial: "Partial T/P/RH coverage",
  context_only: "Context Only (no detector verdict)",
  unavailable: "Data Unavailable",
  // Pressure basis (never silently conflated across stations).
  altimeter_qnh_hpa: "QNH altimeter (sea-level reduced — not station pressure)",
  station_level_hpa: "Station-level pressure",
  // Provider provenance for relative humidity.
  "reported (provider file; measured-vs-calculated not verifiable)":
    "Reported in the provider file — measured vs calculated is not verifiable",
};

export function formatDisplayTerm(value: string | null | undefined, fallback = "—"): string {
  if (value === null || value === undefined || value.trim() === "") return fallback;
  const key = value.trim();
  return DISPLAY_TERMS[key] ?? DISPLAY_TERMS[key.toLowerCase()] ?? key;
}

/** Compact count for supporting metrics (793872 → "793K+"). */
export function formatCompactCount(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  if (value >= 1000) return `${Math.floor(value / 1000).toLocaleString()}K+`;
  return value.toLocaleString();
}
