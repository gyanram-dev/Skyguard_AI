import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { DisplayStatus } from "@/lib/api";

export const statusLabels: Record<DisplayStatus, string> = {
  healthy: "Healthy",
  review: "Needs review",
  anomaly: "Anomaly",
  offline: "Offline",
  historical: "Historical only",
};

export function StatusBadge({ status }: { status: DisplayStatus }) {
  return (
    <span className={cn("status-badge", `status-${status}`)}>
      <span className="status-dot" />
      {statusLabels[status]}
    </span>
  );
}

export function LoadingState({ message }: { message: string }) {
  return (
    <div className="panel p-4" role="status" aria-label="Loading">
      <div className="space-y-2">
        <Skeleton className="h-4 w-2/5" />
        <Skeleton className="h-4 w-3/5" />
        <Skeleton className="h-4 w-1/2" />
      </div>
      <p className="mt-3 text-[10px] font-semibold text-muted-foreground">{message}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-offline/30 bg-offline-soft px-3 py-2.5" role="alert">
      <p className="text-[10px] font-bold text-offline-deep">Unavailable</p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="panel p-4" role="status">
      <p className="text-xs font-extrabold">{title}</p>
      <p className="mt-1 text-[10px] text-muted-foreground">{message}</p>
    </div>
  );
}

export function DetailStat({
  label,
  value,
  emphasis = false,
  tone,
  valueTone,
}: {
  label: string;
  value: string;
  emphasis?: boolean | undefined;
  tone?: string | undefined;
  valueTone?: string | undefined;
}) {
  return (
    <div
      className={cn("min-w-0 rounded-xl p-2", tone ?? (emphasis ? "bg-anomaly-soft" : "bg-muted"))}
    >
      <p className="text-[7px] font-semibold leading-tight text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mt-1 break-words text-[11px] font-extrabold leading-tight",
          valueTone ?? (emphasis && "text-anomaly"),
        )}
      >
        {value}
      </p>
    </div>
  );
}

/** Small label/value row used on detail pages. */
export function FactRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <p className="flex items-center justify-between gap-2 py-1 text-[11px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-extrabold text-foreground">{value}</span>
    </p>
  );
}
