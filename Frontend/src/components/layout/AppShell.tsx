import { useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell({
  title,
  breadcrumb,
  actions,
  children,
  routeKey,
}: {
  title: string;
  breadcrumb?: string[];
  actions?: ReactNode;
  children: ReactNode;
  routeKey: string;
}) {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="flex h-full min-h-screen bg-plane">
      {/* desktop sidebar */}
      <aside className="hidden w-[262px] shrink-0 border-r border-line lg:block">
        <div className="sticky top-0 h-screen">
          <Sidebar />
        </div>
      </aside>

      {/* mobile drawer nav */}
      <AnimatePresence>
        {navOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <motion.div
              className="absolute inset-0 bg-[#0b0f16]/40"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              onClick={() => setNavOpen(false)}
            />
            <motion.div
              className="relative h-full w-[276px] border-r border-line shadow-lg"
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
            >
              <Sidebar onNavigate={() => setNavOpen(false)} onClose={() => setNavOpen(false)} />
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar title={title} breadcrumb={breadcrumb} actions={actions} onOpenNav={() => setNavOpen(true)} />
        <main className="min-w-0 flex-1">
          <AnimatePresence mode="wait">
            <motion.div
              key={routeKey}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              className="mx-auto w-full max-w-[1440px] px-4 py-7 sm:px-6 lg:px-8 lg:py-9"
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
