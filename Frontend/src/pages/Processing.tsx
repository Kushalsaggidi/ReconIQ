import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  Check,
  CheckCircle2,
  Circle,
  Cpu,
  Gauge,
  Loader2,
  Sparkles,
  Timer,
} from "lucide-react";
import { cn, formatNumber } from "@/lib/utils";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { ProgressBar } from "@/components/ui/Misc";
import { CountUp } from "@/components/ui/CountUp";
import * as api from "@/services/api";
import { useRecon } from "@/store/ReconProvider";
import type { JobProgress } from "@/services/types";

const POLL_MS = 900;

const IDLE_PROGRESS: JobProgress = {
  jobId: "",
  status: "queued",
  recordsDetected: 0,
  recordsProcessed: 0,
  matchedSoFar: 0,
  exceptionsSoFar: 0,
  ratePerSecond: 0,
  elapsedMs: 0,
  etaMs: 0,
  percent: 0,
  stages: [],
  currentStageLabel: "Queued",
};

export function Processing() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const { completeRun, isDemo } = useRecon();
  const [progress, setProgress] = useState<JobProgress>({ ...IDLE_PROGRESS, jobId });
  const handedOff = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const next = await api.getJobStatus(jobId);
        if (cancelled) return;
        setProgress(next);

        if (next.status === "completed" && !handedOff.current) {
          handedOff.current = true;
          await completeRun(jobId);
          if (cancelled) return;
          // let the completion state land before the screen changes
          setTimeout(() => {
            if (!cancelled) navigate(`/results/${jobId}`, { replace: true });
          }, 1_050);
          return;
        }
        if (next.status === "failed") return;
        timer = setTimeout(poll, POLL_MS);
      } catch {
        if (!cancelled) timer = setTimeout(poll, POLL_MS);
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, completeRun, navigate]);

  const done = progress.status === "completed";
  const failed = progress.status === "failed";
  const eta = Math.max(0, Math.ceil(progress.etaMs / 1000));

  if (failed) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 text-center">
        <Badge tone="critical" icon={<AlertTriangle className="size-3.5" />}>
          Failed
        </Badge>
        <h1 className="text-[24px] font-semibold tracking-[-0.025em] text-ink">Reconciliation failed</h1>
        <p className="text-[14px] leading-relaxed text-ink-2">
          {progress.error ?? "The job could not be completed. Check the audit trail for details."}
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      {/* ---------------- header ---------------- */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2.5 flex items-center gap-2">
            {done ? (
              <Badge tone="good" icon={<CheckCircle2 className="size-3.5" />}>
                Completed
              </Badge>
            ) : (
              <Badge tone="accent" icon={<Loader2 className="size-3.5 animate-spin" />}>
                Running
              </Badge>
            )}
            {isDemo && (
              <Badge tone="ai" size="sm">
                Demo dataset
              </Badge>
            )}
          </div>
          <h1 className="text-[26px] font-semibold tracking-[-0.025em] text-ink">
            {done ? "Reconciliation complete" : "Reconciliation in progress"}
          </h1>
          <p className="mt-2 text-[14px] leading-relaxed text-ink-2">
            {done
              ? "Opening the result set…"
              : "Deterministic matching runs first. The model is only called once the engine has finished computing every figure."}
          </p>
        </div>

        <div className="rounded-xl border border-line bg-surface px-4 py-3 shadow-xs">
          <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-3">Job ID</p>
          <p className="tnum mt-1 text-[14px] font-semibold text-ink">{jobId}</p>
          <p className="tnum mt-1.5 text-[11.5px] text-ink-3">
            {formatNumber(progress.recordsDetected)} records detected
          </p>
        </div>
      </div>

      {/* ---------------- progress ---------------- */}
      <Card>
        <CardBody className="pb-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-[12.5px] font-medium text-ink-2">{progress.currentStageLabel}</p>
              <p className="mt-1.5 flex items-baseline gap-2">
                <span className="tnum text-[30px] font-semibold leading-none tracking-[-0.03em] text-ink">
                  <CountUp
                    value={progress.recordsProcessed}
                    duration={260}
                    format={formatNumber}
                  />
                </span>
                <span className="tnum text-[15px] text-ink-3">
                  / {formatNumber(progress.recordsDetected)} records
                </span>
              </p>
            </div>
            <div className="text-right">
              <span className="tnum text-[26px] font-semibold leading-none tracking-[-0.02em] text-accent-text">
                {progress.percent.toFixed(1)}%
              </span>
              <p className="mt-1.5 text-[11.5px] text-ink-3">
                {done ? "finished" : eta > 0 ? `~${eta}s remaining` : "finalising"}
              </p>
            </div>
          </div>

          <ProgressBar percent={progress.percent} height={10} animated={!done} className="mt-4" tone={done ? "good" : "accent"} />

          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <LiveStat
              icon={<CheckCircle2 className="size-3.5" />}
              label="Matched so far"
              value={progress.matchedSoFar}
              format={formatNumber}
            />
            <LiveStat
              icon={<AlertTriangle className="size-3.5" />}
              label="Exceptions detected"
              value={progress.exceptionsSoFar}
              format={formatNumber}
              tone="serious"
            />
            <LiveStat
              icon={<Gauge className="size-3.5" />}
              label="Processing rate"
              value={progress.ratePerSecond}
              format={(n) => `${formatNumber(n)}/s`}
            />
            <LiveStat
              icon={<Timer className="size-3.5" />}
              label="Elapsed"
              value={progress.elapsedMs / 1000}
              format={(n) => `${n.toFixed(1)}s`}
            />
          </div>
        </CardBody>
      </Card>

      {/* ---------------- stages ---------------- */}
      <Card>
        <CardHeader
          title="Pipeline stages"
          description="Each stage is recorded in the audit trail with its own timestamp."
          compact
          actions={
            <span className="hidden items-center gap-1.5 text-[11.5px] text-ink-3 sm:flex">
              <Activity className="size-3.5" />
              live
            </span>
          }
        />
        <ol className="divide-y divide-line">
          {progress.stages.map((s) => {
            const isAi = s.engine === "ai";
            return (
              <li
                key={s.id}
                className={cn(
                  "flex items-center gap-3.5 px-6 py-3.5 transition-colors duration-300",
                  s.status === "active" && (isAi ? "bg-ai-soft/60" : "bg-accent-soft/50"),
                )}
              >
                <span className="grid size-6 shrink-0 place-items-center">
                  <AnimatePresence mode="wait" initial={false}>
                    {s.status === "done" ? (
                      <motion.span
                        key="done"
                        initial={{ scale: 0.6, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                        className="grid size-5.5 place-items-center rounded-full bg-good-soft text-good-text"
                      >
                        <Check className="size-3.5" strokeWidth={3} />
                      </motion.span>
                    ) : s.status === "active" ? (
                      <motion.span
                        key="active"
                        initial={{ scale: 0.8, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        className={cn(
                          "grid size-5.5 place-items-center rounded-full pulse-ring",
                          isAi ? "bg-ai text-white" : "bg-accent text-white",
                        )}
                      >
                        <Loader2 className="size-3.5 animate-spin" strokeWidth={2.75} />
                      </motion.span>
                    ) : (
                      <motion.span key="pending" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Circle className="size-4 text-line-strong" strokeWidth={2} />
                      </motion.span>
                    )}
                  </AnimatePresence>
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        "text-[13.5px] font-medium",
                        s.status === "pending" ? "text-ink-3" : "text-ink",
                      )}
                    >
                      {s.label}
                    </span>
                    {isAi && (
                      <Badge tone="ai" size="sm" icon={<Sparkles className="size-3" />}>
                        AI
                      </Badge>
                    )}
                  </div>
                  <p
                    className={cn(
                      "mt-0.5 text-[12px] leading-relaxed",
                      s.status === "pending" ? "text-ink-3/70" : "text-ink-2",
                    )}
                  >
                    {s.detail}
                  </p>
                </div>

                <span className="shrink-0 text-right">
                  {s.status === "done" ? (
                    <span className="text-[11.5px] font-medium text-good-text">done</span>
                  ) : s.status === "active" ? (
                    <span className={cn("text-[11.5px] font-medium", isAi ? "text-ai-text" : "text-accent-text")}>
                      running
                    </span>
                  ) : (
                    <span className="text-[11.5px] text-ink-3">queued</span>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      </Card>

      <p className="flex items-center justify-center gap-2 text-center text-[12px] text-ink-3">
        <Cpu className="size-3.5" />
        Matching, variance and totals are computed deterministically in Python. The model classifies and explains
        exceptions — it never produces a financial figure.
      </p>
    </div>
  );
}

function LiveStat({
  icon,
  label,
  value,
  format,
  tone = "default",
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  format: (n: number) => string;
  tone?: "default" | "serious";
}) {
  return (
    <div className="rounded-lg border border-line bg-surface-2 px-4 py-3">
      <div className="flex items-center gap-1.5 text-ink-3">
        {icon}
        <span className="text-[11.5px] font-medium text-ink-2">{label}</span>
      </div>
      <p
        className={cn(
          "tnum mt-1.5 text-[19px] font-semibold tracking-[-0.02em]",
          tone === "serious" ? "text-serious-text" : "text-ink",
        )}
      >
        <CountUp value={value} duration={260} format={format} />
      </p>
    </div>
  );
}
