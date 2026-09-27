import { createFileRoute, Outlet, useLocation } from "@tanstack/react-router";

import { AppShell } from "@/components/layout/AppShell";

export const Route = createFileRoute("/_app")({
  component: AppLayout,
});

type Title = { title: string; subtitle: string };

const TITLES: Array<{ prefix: string; exact?: boolean; title: Title }> = [
  {
    prefix: "/",
    exact: true,
    title: {
      title: "Live Overview",
      subtitle: "National weather station monitoring and anomaly intelligence",
    },
  },
  {
    prefix: "/stations",
    title: { title: "Stations", subtitle: "Monitor and inspect the weather station network" },
  },
  {
    prefix: "/alerts",
    title: { title: "Alerts", subtitle: "Review detected anomalies and data availability events" },
  },
  {
    prefix: "/investigations",
    title: { title: "Investigations", subtitle: "Understand why observations were flagged" },
  },
  {
    prefix: "/network-health",
    title: {
      title: "Network Health",
      subtitle: "Monitor station availability and trust health",
    },
  },
  {
    prefix: "/judge-probe",
    title: {
      title: "Judge Probe",
      subtitle: "Test a weather observation through SkyGuard",
    },
  },
];

const FALLBACK: Title = {
  title: "SkyGuard AI",
  subtitle: "Context-aware weather intelligence and station trust monitoring",
};

function titleForPath(pathname: string): Title {
  for (const entry of TITLES) {
    if (entry.exact ? pathname === entry.prefix : pathname.startsWith(entry.prefix)) {
      return entry.title;
    }
  }
  return FALLBACK;
}

function AppLayout() {
  const { pathname } = useLocation();
  const { title, subtitle } = titleForPath(pathname);

  return (
    <AppShell title={title} subtitle={subtitle}>
      <Outlet />
    </AppShell>
  );
}
