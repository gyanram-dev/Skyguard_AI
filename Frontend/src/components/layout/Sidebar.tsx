import { Link } from "@tanstack/react-router";
import {
  Award,
  BarChart3,
  Bell,
  FlaskConical,
  HeartPulse,
  MapPin,
  Radio,
  Search,
  ShieldCheck,
  Upload,
} from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useOpenLiveEpisodes } from "@/hooks/useSkyguard";

const navItems = [
  { label: "Overview", icon: BarChart3, to: "/" },
  { label: "Stations", icon: MapPin, to: "/stations" },
  { label: "Alerts", icon: Bell, to: "/alerts" },
  { label: "Investigations", icon: Search, to: "/investigations" },
  { label: "Network Health", icon: HeartPulse, to: "/network-health" },
  { label: "Live", icon: Radio, to: "/live" },
  { label: "Judge Probe", icon: FlaskConical, to: "/judge-probe" },
  { label: "Evaluation", icon: Award, to: "/evaluation" },
  { label: "Analyze Data", icon: Upload, to: "/analyze-data" },
] as const;

const idleClass = cn(
  buttonVariants({ variant: "sidebar" }),
  "h-[42px] w-full justify-start gap-3 rounded-lg px-3 text-[15px] font-medium [&_svg]:size-[17px]",
);
const activeClass = cn(
  buttonVariants({ variant: "sidebarActive" }),
  "nav-active h-[42px] w-full justify-start gap-3 rounded-lg px-3 text-[15px] font-medium [&_svg]:size-[17px]",
);

export function Sidebar() {
  const openEpisodes = useOpenLiveEpisodes();
  return (
    <aside className="hidden w-[200px] shrink-0 flex-col border-r border-sidebar-border/80 bg-sidebar px-[18px] pb-[18px] pt-[28px] text-sidebar-foreground lg:flex">
      <div className="flex items-center gap-2 px-[4px]">
        <div className="flex size-9 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground shadow-logo">
          <ShieldCheck className="size-5" strokeWidth={2.2} />
        </div>
        <div>
          <p className="text-[17px] font-semibold leading-none text-sidebar-foreground">
            SkyGuard <span className="text-sidebar-highlight">AI</span>
          </p>
          <p className="mt-1 text-[9px] font-medium uppercase tracking-[0.14em] text-sidebar-muted">
            Climate intelligence
          </p>
        </div>
      </div>
      <nav className="mt-4 space-y-[3px]" aria-label="Primary navigation">
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
            {item.label === "Alerts" && openEpisodes > 0 && (
              <span
                aria-label={`${openEpisodes} active live alerts`}
                className="ml-auto flex size-[19px] shrink-0 items-center justify-center rounded-full bg-[#FF4141] text-[10px] font-bold text-white"
              >
                {openEpisodes > 99 ? "99+" : openEpisodes}
              </span>
            )}
          </Link>
        ))}
      </nav>
      <p className="mt-auto px-2 pt-4 text-[10px] font-medium leading-snug text-sidebar-muted/80">
        Trusted Data.
        <br />
        Safer Tomorrow.
      </p>
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
