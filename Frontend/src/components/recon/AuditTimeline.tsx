import { AlertTriangle, Check, Cpu, Info, Sparkles, User } from "lucide-react";
import { cn, formatClock } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import type { AuditEvent } from "@/services/types";

const ACTOR_ICON = {
  Engine: Cpu,
  "AI Analyst": Sparkles,
  User: User,
  System: Info,
};

/**
 * Chronological, append-only record of what the engine and the model each did.
 * The actor column is the point of the whole screen — an auditor must be able
 * to see which layer produced every step.
 */
export function AuditTimeline({ events }: { events: AuditEvent[] }) {
  return (
    <ol className="relative">
      {/* the spine */}
      <span className="absolute left-[76px] top-2 bottom-2 hidden w-px bg-line sm:block" aria-hidden />

      {events.map((e, i) => {
        const Icon = ACTOR_ICON[e.actor];
        const isAi = e.engine === "ai";
        return (
          <li key={e.id} className="group relative flex gap-4">
            {/* timestamp gutter */}
            <div className="hidden w-[60px] shrink-0 pt-4 text-right sm:block">
              <span className="tnum text-[12px] font-medium text-ink">{formatClock(e.at)}</span>
            </div>

            {/* node */}
            <div className="relative hidden w-8 shrink-0 justify-center pt-4 sm:flex">
              <span
                className={cn(
                  "z-10 grid size-6 place-items-center rounded-full ring-4 ring-plane transition-transform duration-150 group-hover:scale-110",
                  e.status === "warning"
                    ? "bg-warning-soft text-warning-text"
                    : isAi
                      ? "bg-ai-soft text-ai"
                      : e.status === "ok"
                        ? "bg-good-soft text-good-text"
                        : "bg-surface-3 text-ink-2",
                )}
              >
                {e.status === "warning" ? (
                  <AlertTriangle className="size-3" strokeWidth={2.75} />
                ) : e.status === "ok" ? (
                  <Check className="size-3" strokeWidth={3} />
                ) : (
                  <Icon className="size-3" strokeWidth={2.5} />
                )}
              </span>
            </div>

            {/* card */}
            <div
              className={cn(
                "mb-3 min-w-0 flex-1 rounded-xl border bg-surface px-4 py-3.5 shadow-xs transition-[border-color,box-shadow] duration-150 hover:border-line-strong hover:shadow-sm",
                isAi ? "border-ai-line" : "border-line",
                i === events.length - 1 && "mb-0",
              )}
            >
              <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="tnum text-[12px] font-medium text-ink-3 sm:hidden">{formatClock(e.at)}</span>
                    <h4 className="text-[13.5px] font-semibold tracking-[-0.01em] text-ink">{e.title}</h4>
                  </div>
                  <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">{e.description}</p>
                </div>

                <div className="flex shrink-0 items-center gap-1.5">
                  {isAi ? (
                    <Badge tone="ai" size="sm" icon={<Sparkles className="size-3" />}>
                      AI Analyst
                    </Badge>
                  ) : e.actor === "User" ? (
                    <Badge tone="neutral" size="sm" icon={<User className="size-3" />}>
                      User
                    </Badge>
                  ) : e.actor === "System" ? (
                    <Badge tone="neutral" size="sm">
                      System
                    </Badge>
                  ) : (
                    <Badge tone="accent" size="sm" icon={<Cpu className="size-3" />}>
                      Engine
                    </Badge>
                  )}
                </div>
              </div>

              {e.meta && (
                <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-2.5">
                  {Object.entries(e.meta).map(([k, v]) => (
                    <span key={k} className="text-[11.5px] text-ink-3">
                      {k}: <span className="tnum font-medium text-ink-2">{v}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
