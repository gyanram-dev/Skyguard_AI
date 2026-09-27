import { Outlet } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { Header, type Theme } from "@/components/layout/Header";
import { MobileNav, Sidebar } from "@/components/layout/Sidebar";
import { useAlerts, useHealth } from "@/hooks/useSkyguard";

/** Shared application shell: sidebar + header + theme, rendered once. */
export function AppShell() {
  const [theme, setTheme] = useState<Theme>("light");
  const healthQuery = useHealth();
  const alertsQuery = useAlerts(1000);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  const dataMode = healthQuery.data?.data_mode ?? alertsQuery.data?.data_mode ?? null;
  const backendFailed = healthQuery.isError && alertsQuery.isError;

  return (
    <main className="flex min-h-screen flex-col bg-background text-foreground lg:h-screen lg:overflow-hidden">
      <div className="dashboard-shell flex min-h-[876px] flex-1 overflow-hidden bg-surface lg:h-full lg:min-h-0">
        <Sidebar alertCount={alertsQuery.data ? String(alertsQuery.data.alerts.length) : null} />

        <section className="flex min-w-0 flex-1 flex-col">
          <Header
            theme={theme}
            onThemeChange={setTheme}
            online={!backendFailed}
            dataMode={dataMode}
          />
          <MobileNav />
          <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 pt-0 lg:overflow-y-auto">
            <Outlet />
          </div>
        </section>
      </div>
    </main>
  );
}
