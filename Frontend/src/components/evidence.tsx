import { AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";
import { cleanText, formatConfidence, formatScore } from "@/lib/format";
import type { DisplayStatus, EvidenceItem, Explanation } from "@/lib/api";

/** Numbered backend evidence items; honest empty state when absent. */
export function EvidenceList({
  evidence,
  loading,
}: {
  evidence: EvidenceItem[];
  loading: boolean;
}) {
  return (
    <div className="rounded-xl border border-border p-2.5">
      <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">
        Why this needs review
      </p>
      <div className="mt-1.5 space-y-1.5">
        {evidence.length > 0 ? (
          evidence.map((item, index) => (
            <div key={`${item.source}-${index}`} className="flex gap-2">
              <span
                className={cn(
                  "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full text-[8px] font-extrabold",
                  index === 0 ? "bg-warning-soft text-warning-deep" : "bg-info-soft text-info",
                )}
              >
                {index + 1}
              </span>
              <p className="text-[11px] leading-snug">
                <strong className="block text-foreground">{item.title}</strong>
                <span className="text-muted-foreground">{item.detail}</span>
              </p>
            </div>
          ))
        ) : (
          <p className="text-[11px] text-muted-foreground">
            {loading ? "Loading evidence…" : "No evidence items available for this alert."}
          </p>
        )}
      </div>
    </div>
  );
}

/** Colored outcome banner: root cause + explanation + ensemble method. */
export function OutcomeBanner({
  status,
  outcome,
  message,
  rootCauseConfidence,
  ensembleMethod,
  anomalyScore,
}: {
  status: DisplayStatus;
  outcome: string;
  message: string;
  rootCauseConfidence?: number | null;
  ensembleMethod?: string | null;
  anomalyScore?: number | null;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-xl border p-2.5",
        status === "offline"
          ? "border-offline/30 bg-offline-soft text-offline"
          : status === "anomaly"
            ? "border-anomaly/30 bg-anomaly-soft text-anomaly"
            : "border-warning/30 bg-warning-soft text-warning",
      )}
    >
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
      <p className="text-[11px] leading-snug">
        <strong
          className={cn(
            "block",
            status === "offline"
              ? "text-offline-deep"
              : status === "anomaly"
                ? "text-anomaly-deep"
                : "text-warning-deep",
          )}
        >
          {outcome}
        </strong>
        <span className="text-muted-foreground">{message}</span>
        {(rootCauseConfidence !== undefined || ensembleMethod || anomalyScore !== undefined) && (
          <span className="mt-1 block text-muted-foreground">
            {rootCauseConfidence !== undefined &&
              `Root-cause confidence: ${formatConfidence(rootCauseConfidence)}`}
            {ensembleMethod ? ` · Ensemble: ${ensembleMethod}` : ""}
            {anomalyScore !== undefined && rootCauseConfidence === undefined
              ? `Anomaly score: ${formatScore(anomalyScore)}`
              : ""}
          </span>
        )}
      </p>
    </div>
  );
}

/** Explainability block: text plus per-feature contributions when present. */
export function ExplanationBlock({
  explanation,
  loading,
}: {
  explanation: Explanation | undefined;
  loading: boolean;
}) {
  const text = cleanText(explanation?.text);
  const features = explanation?.features ?? [];
  return (
    <div className="rounded-xl border border-border p-2.5">
      <p className="text-[10px] font-extrabold uppercase tracking-[0.06em]">Explainability</p>
      {loading ? (
        <p className="mt-1.5 text-[11px] text-muted-foreground">Loading explanation…</p>
      ) : text ? (
        <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">{text}</p>
      ) : (
        <p className="mt-1.5 text-[11px] text-muted-foreground">Explanation not available.</p>
      )}
      {!loading && features.length > 0 && (
        <ul className="mt-2 space-y-1">
          {features.map((feature) => (
            <li key={feature.name} className="flex items-center justify-between gap-2 text-[11px]">
              <span className="font-semibold text-foreground">{feature.name}</span>
              <span className="text-muted-foreground">
                {feature.contribution !== null && feature.contribution !== undefined
                  ? `${feature.contribution >= 0 ? "+" : ""}${feature.contribution.toFixed(3)} · ${feature.direction}`
                  : feature.direction}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
