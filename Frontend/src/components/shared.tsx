import type { ReactNode } from "react";
import { AlertTriangle, Search } from "lucide-react";

import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { DisplayStatus } from "@/lib/api";

export const statusLabels: Record<DisplayStatus, string> = {
  healthy: "Healthy",
  review: "Needs review",
  anomaly: "Anomaly",
  offline: "Offline",
};

export function StatusBadge({ status }: { status: DisplayStatus }) {
  return (
    <span className={cn("status-badge", `status-${status}`)}>
      <span className="status-dot" />
      {statusLabels[status]}
    </span>
  );
}

export function LoadingBlock({ label }: { label: string }) {
  return (
    <p className="text-[11px] text-muted-foreground" role="status">
      {label}
    </p>
  );
}

export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-offline/30 bg-offline-soft px-3 py-2.5" role="alert">
      <p className="text-[11px] font-bold text-offline-deep">Data unavailable</p>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyBlock({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-3 py-4 text-center" role="status">
      <p className="text-[11px] font-extrabold text-foreground">{title}</p>
      <p className="mt-1 text-[10px] text-muted-foreground">{message}</p>
    </div>
  );
}

export function SearchField({
  value,
  onChange,
  placeholder,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  label: string;
}) {
  return (
    <label className="relative block min-w-0 flex-1">
      <span className="sr-only">{label}</span>
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-8 bg-card pl-8 text-xs"
      />
    </label>
  );
}

export function FilterPills<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Status filter">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          aria-pressed={value === option.value}
          className={cn(
            "cursor-pointer rounded-full border px-2.5 py-1 text-[10px] font-bold transition-colors",
            value === option.value
              ? "border-primary/50 bg-info-soft text-info"
              : "border-border bg-card text-muted-foreground hover:text-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function SectionCard({
  title,
  subtitle,
  action,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("panel p-4", className)} aria-label={title}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-extrabold text-foreground">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[10px] text-muted-foreground">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <p className="flex items-baseline justify-between gap-3 py-1 text-[11px]">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words text-right font-bold text-foreground">{value}</span>
    </p>
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
  emphasis?: boolean;
  tone?: string;
  valueTone?: string;
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

export function OutcomeBanner({
  tone,
  title,
  titleTone,
  children,
}: {
  tone: "review" | "anomaly" | "offline";
  title: string;
  titleTone: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-xl border p-2.5",
        tone === "offline" && "border-offline/30 bg-offline-soft text-offline",
        tone === "anomaly" && "border-anomaly/30 bg-anomaly-soft text-anomaly",
        tone === "review" && "border-warning/30 bg-warning-soft text-warning",
      )}
    >
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
      <p className="text-[9px] leading-snug">
        <strong className={cn("block", titleTone)}>{title}</strong>
        <span className="text-muted-foreground">{children}</span>
      </p>
    </div>
  );
}
