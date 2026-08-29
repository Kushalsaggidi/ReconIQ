import { NavLink } from "react-router-dom";
import {
  AlertTriangle,
  FileClock,
  LayoutDashboard,
  ListChecks,
  PlusCircle,
  Settings,
  X,
} from "lucide-react";
import { cn, formatNumber } from "@/lib/utils";
import { EXCEPTION_COUNT } from "@/services/api";

export const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/new", label: "New Reconciliation", icon: PlusCircle },
  { to: "/history", label: "Reconciliation History", icon: ListChecks },
  { to: "/exceptions", label: "Exceptions", icon: AlertTriangle, badge: EXCEPTION_COUNT },
  { to: "/audit", label: "Audit Logs", icon: FileClock },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar({ onNavigate, onClose }: { onNavigate?: () => void; onClose?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-sidebar">
      <div className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-line px-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-accent-ink shadow-xs">
            <svg viewBox="0 0 24 24" className="size-4.5" fill="currentColor" aria-hidden>
              <path d="M6 18.5 11 4h3.4l-2.6 7.2h2.9L10.6 22H7.4l2.3-5.6H7.2z" />
            </svg>
          </span>
          <div className="min-w-0">
            <div className="truncate text-[13.5px] font-semibold leading-tight tracking-[-0.01em] text-ink">
              Settlement Reconciler
            </div>
            <div className="truncate text-[11px] leading-tight text-ink-3">Razorpay · Finance Ops</div>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            aria-label="Close navigation"
            className="grid size-8 shrink-0 place-items-center rounded-md text-ink-2 hover:bg-surface-3 lg:hidden"
          >
            <X className="size-4" />
          </button>
        )}
      </div>

      <nav className="thin-scroll flex-1 overflow-y-auto px-3 py-4">
        <p className="px-2 pb-2 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-3">
          Reconciliation
        </p>
        <ul className="space-y-0.5">
          {NAV.map(({ to, label, icon: Icon, end, badge }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    "group relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium",
                    "transition-colors duration-150",
                    isActive
                      ? "bg-accent-soft text-accent-text"
                      : "text-ink-2 hover:bg-surface-3 hover:text-ink",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={cn(
                        "absolute left-0 top-1/2 h-4 w-[2.5px] -translate-y-1/2 rounded-r-full bg-accent transition-opacity duration-150",
                        isActive ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <Icon
                      className={cn("size-4 shrink-0", isActive ? "text-accent" : "text-ink-3 group-hover:text-ink-2")}
                      strokeWidth={2}
                    />
                    <span className="min-w-0 flex-1 truncate">{label}</span>
                    {badge !== undefined && (
                      <span
                        className={cn(
                          "tnum shrink-0 rounded-md px-1.5 py-px text-[11px] font-semibold",
                          isActive ? "bg-accent text-accent-ink" : "bg-surface-3 text-ink-2",
                        )}
                      >
                        {formatNumber(badge)}
                      </span>
                    )}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="shrink-0 border-t border-line p-3">
        <div className="rounded-lg border border-line bg-surface-2 p-3">
          <div className="flex items-center gap-2">
            <span className="size-1.5 rounded-full bg-good" />
            <span className="text-[11.5px] font-semibold text-ink">Engine online</span>
          </div>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-3">
            Deterministic matching v4.2 · classifier v3
          </p>
        </div>
      </div>
    </div>
  );
}
