import { ApiError } from "@/lib/api";

/** Shared display formatters for API-backed values (Phase 13/14). */

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
