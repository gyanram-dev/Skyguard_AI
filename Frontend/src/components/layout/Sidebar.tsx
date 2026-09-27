import { Link } from "@tanstack/react-router";
import {
  BarChart3,
  Bell,
  FlaskConical,
  HeartPulse,
  MapPin,
  Search,
  ShieldCheck,
} from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAlerts } from "@/hooks/useSkyguard";

const navItems = [
  { label: "Overview", to: "/", icon: BarChart3, exact: true },
  { label: "Stations", to: "/stations", icon: MapPin, exact: false },
  { label: "Alerts", to: "/alerts", icon: Bell, exact: false },
  { label: "Investigations", to: "/investigations", icon: Search, exact: false },
  { label: "Network Health", to: "/network-health", icon: HeartPulse, exact: false },
  { label: "Judge Probe", to: "/judge-probe", icon: FlaskConical, exact: false },
] as const;

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const alertsQuery = useAlerts();
  const alertCount = alertsQuery.data ? String(alertsQuery.data.alerts.length) : null;

  return (
    <>
      <div className="flex items-center gap-2 px-2">
        <div className="flex size-10 items-center justify-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground shadow-logo">
          <ShieldCheck className="size-6" strokeWidth={2.4} />
        </div>
        <div>
          <p className="text-base font-extrabold leading-none text-sidebar-foreground">
            SkyGuard <span className="text-sidebar-highlight">AI</span>
          </p>
          <p className="mt-1 text-[8px] font-semibold uppercase tracking-[0.12em] text-sidebar-muted">
            Climate intelligence
          </p>
        </div>
      </div>
      <p className="mt-3 px-2 text-[10px] font-medium text-sidebar-muted">
        Trusted Data. Safer Tomorrow.
      </p>

      <nav className="mt-8 space-y-1.5" aria-label="Primary navigation">
        {navItems.map((item) => (
          <Link
            key={item.label}
            to={item.to}
            onClick={onNavigate}
            title={item.label}
            activeOptions={item.exact ? { exact: true } : { exact: false }}
            activeProps={{
              className: cn(buttonVariants({ variant: "sidebarActive" }), "w-full justify-start"),
            }}
            className={cn(buttonVariants({ variant: "sidebar" }), "w-full justify-start")}
          >
            <item.icon />
            <span>{item.label}</span>
            {item.label === "Alerts" && alertCount !== null && (
              <span className="ml-auto rounded-full bg-anomaly px-1.5 py-0.5 text-[9px] text-anomaly-foreground">
                {alertCount}
              </span>
            )}
          </Link>
        ))}
      </nav>
    </>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden w-[176px] shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-3 py-5 text-sidebar-foreground lg:flex">
      <SidebarNav />
    </aside>
  );
}
