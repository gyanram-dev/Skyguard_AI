import { Link } from "@tanstack/react-router";
import {
  Award,
  BarChart3,
  Bell,
  FlaskConical,
  HeartPulse,
  MapPin,
  Search,
  ShieldCheck,
  Upload,
} from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { label: "Overview", icon: BarChart3, to: "/" },
  { label: "Stations", icon: MapPin, to: "/stations" },
  { label: "Alerts", icon: Bell, to: "/alerts" },
  { label: "Investigations", icon: Search, to: "/investigations" },
  { label: "Network Health", icon: HeartPulse, to: "/network-health" },
  { label: "Judge Probe", icon: FlaskConical, to: "/judge-probe" },
  { label: "Evaluation", icon: Award, to: "/evaluation" },
  { label: "Analyze Data", icon: Upload, to: "/analyze-data" },
] as const;

const idleClass = cn(buttonVariants({ variant: "sidebar" }), "w-full justify-start");
const activeClass = cn(buttonVariants({ variant: "sidebarActive" }), "w-full justify-start");

export function Sidebar({ alertCount }: { alertCount: string | null }) {
  return (
    <aside className="hidden w-[176px] shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-3 py-5 text-sidebar-foreground lg:flex">
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
            className={idleClass}
            activeProps={{ className: activeClass }}
            activeOptions={{ exact: item.to === "/" }}
            title={item.label}
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
    </aside>
  );
}

/** Compact navigation for viewports where the sidebar is hidden. */
export function MobileNav() {
  return (
    <nav
      className="flex shrink-0 gap-1.5 overflow-x-auto px-3 pb-1 lg:hidden"
      aria-label="Primary navigation"
    >
      {navItems.map((item) => (
        <Link
          key={item.label}
          to={item.to}
          className={cn(buttonVariants({ variant: "sidebar", size: "sm" }), "shrink-0")}
          activeProps={{
            className: cn(buttonVariants({ variant: "sidebarActive", size: "sm" }), "shrink-0"),
          }}
          activeOptions={{ exact: item.to === "/" }}
        >
          <item.icon />
          <span>{item.label}</span>
        </Link>
      ))}
    </nav>
  );
}
