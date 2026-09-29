import { useRouterState } from "@tanstack/react-router";
import { Activity, Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";
import { DATA_MODE_HISTORICAL_REPLAY } from "@/lib/api";
import { formatDisplayTerm } from "@/lib/format";

export type Theme = "light" | "dark";

type PageMeta = { title: string; subtitle: string };

function pageMetaFor(pathname: string): PageMeta {
  const segments = pathname.split("/").filter(Boolean);
  const root = segments[0] ?? "";
  const detail = segments[1] ?? "";
  switch (root) {
    case "":
      return {
        title: "Indian AWS Network",
        subtitle: "Real historical observations · AI-powered quality control",
      };
    case "stations":
      return detail
        ? {
            title: `Station ${detail}`,
            subtitle: "Current observations, data quality and station history",
          }
        : {
            title: "Stations",
            subtitle: "Monitor and inspect the weather station network",
          };
    case "alerts":
      return detail
        ? {
            title: "Alert Detail",
            subtitle: "Triage review for one alert",
          }
        : {
            title: "Alerts",
            subtitle: "Triage queue — what needs attention, and where to look next",
          };
    case "investigations":
      if (detail === "replay") {
        return {
          title: "Replay Anomaly",
          subtitle: "Streamed replay investigation workspace",
        };
      }
      return detail
        ? {
            title: "Investigation",
            subtitle: "Evidence workspace — why SkyGuard made this decision",
          }
        : {
            title: "Investigations",
            subtitle: "Evidence workspace — why SkyGuard made a decision",
          };
    case "network-health":
      return {
        title: "Network Health",
        subtitle: "Monitor station availability and trust health",
      };
    case "judge-probe":
      return {
        title: "Test an Observation",
        subtitle: "Score one observation through the SkyGuard pipeline",
      };
    case "live":
      return {
        title: "Live & Replay",
        subtitle: "Source state, controlled live demonstration and historical replay",
      };
    case "evaluation":
      return {
        title: "SkyGuard Evaluation",
        subtitle: "Validated benchmark and runtime evidence",
      };
    case "analyze-data":
      return {
        title: "Analyze Data",
        subtitle: "Upload a station CSV and run SkyGuard analysis",
      };
    default:
      return {
        title: "SkyGuard AI",
        subtitle: "Context-aware weather intelligence",
      };
  }
}

export function Header({
  theme,
  onThemeChange,
  online,
  dataMode,
}: {
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
  online: boolean;
  dataMode: string | null;
}) {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const meta = pageMetaFor(pathname);
  const replay = dataMode === DATA_MODE_HISTORICAL_REPLAY;
  const overview = pathname === "/" || pathname === "";
  return (
    <header className="flex h-14 shrink-0 items-center justify-between px-5">
      <div>
        <h1
          className={cn(
            "font-extrabold leading-tight text-foreground",
            overview ? "text-[15px] tracking-tight" : "text-xl",
          )}
        >
          {meta.title}
        </h1>
        <p className={cn("font-medium text-muted-foreground", overview ? "text-[11px]" : "text-xs")}>
          {meta.subtitle}
        </p>
      </div>
      <div className="flex items-center gap-1.5">
        {online ? (
          <span className="status-pill px-2.5 py-1 text-[10px] font-semibold bg-success-soft text-success-deep">
            <span className="status-dot bg-success" />
            System Online
          </span>
        ) : (
          <span className="status-pill px-2.5 py-1 text-[10px] font-semibold bg-offline-soft text-offline-deep">
            <span className="status-dot bg-offline" />
            Backend Unreachable
          </span>
        )}
        {replay ? (
          <span
            className="status-pill px-2.5 py-1 text-[10px] font-semibold bg-info-soft text-info"
            title="Observations are replayed history, not a live sensor feed."
          >
            <Activity className="size-3" />
            Historical Replay
          </span>
        ) : (
          <span className="status-pill px-2.5 py-1 text-[10px] font-semibold bg-info-soft text-info">
            <Activity className="size-3" />
            {dataMode ? formatDisplayTerm(dataMode) : "Connecting…"}
          </span>
        )}
        <div
          role="group"
          aria-label="Color theme"
          className="ml-1 flex items-center rounded-full border border-border bg-card p-1 shadow-soft"
        >
          <button
            type="button"
            onClick={() => onThemeChange("light")}
            aria-pressed={theme === "light"}
            aria-label="Light mode"
            title="Light mode"
            className={cn(
              "flex size-7 cursor-pointer items-center justify-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              theme === "light"
                ? "bg-info-soft text-info"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Sun className="size-4" />
          </button>
          <button
            type="button"
            onClick={() => onThemeChange("dark")}
            aria-pressed={theme === "dark"}
            aria-label="Dark mode"
            title="Dark mode"
            className={cn(
              "flex size-7 cursor-pointer items-center justify-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              theme === "dark"
                ? "bg-info-soft text-info"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Moon className="size-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
