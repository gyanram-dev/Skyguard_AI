import { cleanText } from "@/lib/format";
import type { LiveAlert, LiveReading } from "@/lib/live";

/**
 * Read-only view over a streamed replay event.
 *
 * The replay WebSocket serves two detector shapes:
 *
 * - `ensemble`             Delhi's frozen statistical + Isolation Forest +
 *                          LSTM ensemble (component evidence, threshold).
 * - `station-statistical`  the ten calibrated Indian GHCNh stations: a
 *                          statistical verdict with severity, confidence,
 *                          primary reason and contributing factors.
 *
 * Both are real backend payloads. This module is the ONE place that knows the
 * difference, so components render whichever evidence actually arrived and
 * show "unavailable" for anything the backend did not send. Nothing here
 * computes a detection, a score or a severity.
 */

export type ReplayDetectorShape = "ensemble" | "station-statistical";

export function readingShape(reading: LiveReading): ReplayDetectorShape {
  return reading.detection ? "station-statistical" : "ensemble";
}

/** Documented backend method identifiers, in plain language. */
const METHOD_LABELS: Record<string, string> = {
  ens_median: "Frozen ensemble",
  "ens_median+freeze_detector": "Frozen ensemble + freeze detector",
  freeze_detector: "Freeze detector",
  statistical: "Statistical baseline",
};

/** Human detector label for the panel that produced the verdict. */
export function readingDetectorLabel(reading: LiveReading): string {
  const method = cleanText(reading.anomaly.method);
  return (
    cleanText(reading.detection?.detector) ??
    (method !== null ? (METHOD_LABELS[method] ?? method) : null) ??
    "Detection pipeline"
  );
}

export function readingSeverity(reading: LiveReading): string | null {
  return (
    cleanText(reading.severity) ??
    cleanText(reading.detection?.severity) ??
    cleanText(reading.anomaly.severity) ??
    null
  );
}

export function alertSeverity(alert: LiveAlert): string | null {
  return cleanText(alert.severity) ?? cleanText(alert.event) ?? null;
}

/** Primary reason / diagnosis as the backend reported it (never inferred). */
export function readingReason(reading: LiveReading): string | null {
  return (
    cleanText(reading.detection?.primary_reason) ??
    cleanText(reading.reason) ??
    cleanText(reading.root_cause.class) ??
    cleanText(reading.explanation.text) ??
    null
  );
}

export function alertReason(alert: LiveAlert): string | null {
  return (
    cleanText(alert.reason) ??
    cleanText(alert.detection?.primary_reason) ??
    cleanText(alert.root_cause) ??
    null
  );
}

/** Contributing factors exactly as sent; empty means the backend sent none. */
export function readingContributingFactors(reading: LiveReading): string[] {
  const factors = reading.detection?.contributing_factors ?? reading.evidence.contributing_factors;
  return Array.isArray(factors) ? factors.filter((item) => cleanText(item) !== null) : [];
}

export function readingConfidence(reading: LiveReading): number | null {
  if (typeof reading.confidence === "number") return reading.confidence;
  if (typeof reading.detection?.confidence === "number") return reading.detection.confidence;
  if (typeof reading.anomaly.confidence === "number") return reading.anomaly.confidence;
  return null;
}

export function readingThreshold(reading: LiveReading): number | null {
  return typeof reading.anomaly.threshold === "number" ? reading.anomaly.threshold : null;
}

export type SpatialLevel = "SUPPORTED" | "CONTRADICTED" | "INSUFFICIENT" | "UNAVAILABLE";

const SPATIAL_LEVELS: Record<string, SpatialLevel> = {
  SPATIAL_SUPPORTED: "SUPPORTED",
  SPATIAL_CONTRADICTED: "CONTRADICTED",
  SPATIAL_INSUFFICIENT: "INSUFFICIENT",
  SPATIAL_UNAVAILABLE: "UNAVAILABLE",
  SUPPORTED: "SUPPORTED",
  CONTRADICTED: "CONTRADICTED",
  INSUFFICIENT: "INSUFFICIENT",
  UNAVAILABLE: "UNAVAILABLE",
};

function toSpatialLevel(raw: unknown): SpatialLevel {
  if (typeof raw !== "string") return "UNAVAILABLE";
  return SPATIAL_LEVELS[raw.toUpperCase()] ?? "UNAVAILABLE";
}

export interface SpatialView {
  available: boolean;
  level: SpatialLevel;
  /** One honest sentence: never claims neighbours are normal. */
  label: string;
  neighborCount: number | null;
  referenceMedian: number | null;
  detail: string | null;
  /** Phase-22 contextual interpretation when the backend supplies one. */
  contextualDecision: string | null;
}

const SPATIAL_LABELS: Record<SpatialLevel, string> = {
  SUPPORTED: "Compatible neighbours behave similarly — possible regional event.",
  CONTRADICTED: "Target differs from compatible neighbours — local sensor anomaly.",
  INSUFFICIENT: "Insufficient compatible neighbour evidence to interpret.",
  UNAVAILABLE: "Spatial context unavailable for this station.",
};

/**
 * Spatial evidence from either shape. The calibrated stations send
 * `spatial_context` next to their verdict; the ensemble path carries its
 * spatial block inside `evidence.spatial`.
 */
export function readingSpatial(reading: LiveReading): SpatialView {
  const spatial = reading.evidence.spatial ?? {};
  const decision = (reading.spatial_decision ?? null) as Record<string, unknown> | null;
  const rawLevel =
    (typeof decision?.["spatial_status"] === "string" && decision["spatial_status"]) ||
    (typeof spatial["context"] === "string" && spatial["context"]) ||
    (typeof spatial["status"] === "string" && spatial["status"]) ||
    "";
  const level = toSpatialLevel(rawLevel);
  const available = spatial["available"] === true && level !== "UNAVAILABLE";
  const neighborCount =
    typeof spatial["neighbor_count"] === "number"
      ? spatial["neighbor_count"]
      : typeof spatial["usable_neighbor_count"] === "number"
        ? spatial["usable_neighbor_count"]
        : null;
  const referenceMedian =
    typeof spatial["reference_median"] === "number" ? spatial["reference_median"] : null;
  const note = typeof spatial["note"] === "string" ? spatial["note"] : null;
  const reason = typeof spatial["reason"] === "string" ? spatial["reason"] : null;
  return {
    available,
    level: available ? level : "UNAVAILABLE",
    label: SPATIAL_LABELS[available ? level : "UNAVAILABLE"],
    neighborCount,
    referenceMedian,
    detail: note ?? reason,
    contextualDecision:
      (typeof decision?.["contextual_decision"] === "string" && decision["contextual_decision"]) ||
      null,
  };
}

/** Human labels for the documented severity vocabulary. */
const SEVERITY_LABELS: Record<string, string> = {
  NORMAL: "Normal",
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
  CRITICAL: "Critical",
};

export function severityLabel(value: string | null): string | null {
  if (value === null) return null;
  return SEVERITY_LABELS[value.toUpperCase()] ?? value;
}
