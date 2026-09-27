import { Activity, Menu, Moon, Sun } from "lucide-react";

import { cn } from "@/lib/utils";
import { DATA_MODE_HISTORICAL_REPLAY } from "@/lib/api";
import { useHealth } from "@/hooks/useSkyguard";
import { useTheme } from "@/components/layout/ThemeContext";

export function Header({
  title,
  subtitle,
  onMenuClick,
}: {
  title: string;
  subtitle: string;
  onMenuClick: () => void;
}) {
  const { theme, setTheme } = useTheme();
  const healthQuery = useHealth();
  const online = !healthQuery.isError;
  const dataMode = healthQuery.data?.data_mode ?? null;
  const replay = dataMode === DATA_MODE_HISTORICAL_REPLAY;

  return (
    <header className="flex h-[72px] shrink-0 items-center justify-between gap-2 px-5">
      <div className="flex min-w-0 items-center gap-2">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Open navigation"
          className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-xl border border-border bg-card text-foreground shadow-soft lg:hidden"
        >
          <Menu className="size-4" />
        </button>
        <div className="min-w-0">
          <h1 className="truncate text-[25px] font-extrabold leading-tight text-foreground">
            {title}
          </h1>
          <p className="truncate text-xs font-medium text-muted-foreground">{subtitle}</p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {online ? (
          <span className="status-pill bg-success-soft text-success-deep">
            <span className="status-dot bg-success" />
            System Online
          </span>
        ) : (
          <span className="status-pill bg-offline-soft text-offline-deep">
            <span className="status-dot bg-offline" />
            Backend Unreachable
          </span>
        )}
        {replay ? (
          <span
            className="status-pill bg-info-soft text-info"
            title="API data_mode: historical_replay — observations are replayed history, not a live sensor feed."
          >
            <Activity className="size-3.5" />
            Historical Replay
          </span>
        ) : (
          <span className="status-pill bg-info-soft text-info">
            <Activity className="size-3.5" />
            {dataMode ?? "Connecting…"}
          </span>
        )}
        <div
          role="group"
          aria-label="Color theme"
          className="ml-1 flex items-center rounded-full border border-border bg-card p-1 shadow-soft"
        >
          <button
            type="button"
            onClick={() => setTheme("light")}
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
            onClick={() => setTheme("dark")}
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
