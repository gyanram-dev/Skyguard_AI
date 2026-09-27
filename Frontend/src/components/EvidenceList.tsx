import { cn } from "@/lib/utils";
import type { EvidenceItem } from "@/lib/api";

/** Numbered evidence rows in the SkyGuard investigation style. */
export function EvidenceList({ evidence }: { evidence: EvidenceItem[] }) {
  if (evidence.length === 0) {
    return (
      <p className="text-[10px] text-muted-foreground">
        No evidence items available for this alert.
      </p>
    );
  }
  return (
    <div className="space-y-1.5">
      {evidence.map((item, index) => (
        <div key={`${item.source}-${index}`} className="flex gap-2">
          <span
            className={cn(
              "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full text-[8px] font-extrabold",
              index === 0 ? "bg-warning-soft text-warning-deep" : "bg-info-soft text-info",
            )}
          >
            {index + 1}
          </span>
          <p className="text-[9px] leading-snug">
            <strong className="block text-foreground">{item.title}</strong>
            <span className="text-muted-foreground">{item.detail}</span>
          </p>
        </div>
      ))}
    </div>
  );
}
