import { useState, type ReactNode } from "react";
import { X } from "lucide-react";

import { Header } from "@/components/layout/Header";
import { Sidebar, SidebarNav } from "@/components/layout/Sidebar";
import { ThemeProvider } from "@/components/layout/ThemeContext";

/** Shared application shell: sidebar + route-aware header + page content. */
export function AppShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <ThemeProvider>
      <main className="flex min-h-screen flex-col bg-background text-foreground lg:h-screen lg:overflow-hidden">
        <div className="dashboard-shell flex min-h-[876px] flex-1 overflow-hidden bg-surface lg:h-full lg:min-h-0">
          <Sidebar />

          <section className="flex min-w-0 flex-1 flex-col">
            <Header title={title} subtitle={subtitle} onMenuClick={() => setMobileNavOpen(true)} />
            <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 pt-0 lg:overflow-y-auto">
              {children}
            </div>
          </section>
        </div>

        {mobileNavOpen && (
          <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-label="Navigation">
            <div
              className="absolute inset-0 bg-foreground/40"
              onClick={() => setMobileNavOpen(false)}
              aria-hidden="true"
            />
            <div className="absolute inset-y-0 left-0 flex w-[240px] flex-col bg-sidebar px-3 py-5 text-sidebar-foreground shadow-soft">
              <button
                type="button"
                onClick={() => setMobileNavOpen(false)}
                aria-label="Close navigation"
                className="mb-4 flex size-9 cursor-pointer items-center justify-center self-end rounded-xl border border-sidebar-border text-sidebar-foreground"
              >
                <X className="size-4" />
              </button>
              <SidebarNav onNavigate={() => setMobileNavOpen(false)} />
            </div>
          </div>
        )}
      </main>
    </ThemeProvider>
  );
}
