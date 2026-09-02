import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Copy, RotateCcw, ShieldAlert } from "lucide-react";
import { cn, formatClock } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/Misc";
import { CopilotAvatar } from "./CopilotAvatar";
import { CopilotMarkdown } from "./copilotMarkdown";
import type { CopilotDisplayMessage } from "./useCopilotChat";

const STARTER_PROMPTS = [
  "Why are there exceptions in this batch?",
  "What are the largest variances?",
  "Which transactions need human review?",
  "Summarize this reconciliation.",
  "Show me the top exception categories.",
];

const THINKING_STAGES = [
  "Checking reconciliation data…",
  "Reviewing exception data…",
  "Verifying response…",
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {
          // clipboard unavailable — no-op
        }
      }}
      className="inline-flex items-center gap-1 text-[11px] text-ink-3 transition-colors hover:text-ink-2"
    >
      {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function CopilotBubble({ message, onRetry }: { message: CopilotDisplayMessage; onRetry: () => void }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-accent px-3.5 py-2.5 text-[13px] leading-relaxed text-accent-ink">
          {message.content}
        </div>
      </div>
    );
  }

  const response = message.response;
  const unverified = !message.error && response && !response.validated;

  return (
    <div className="flex items-start gap-2.5">
      <CopilotAvatar state={message.error ? "error" : unverified ? "uncertain" : "success"} size={26} />
      <div className="min-w-0 flex-1">
        <div
          className={cn(
            "rounded-2xl rounded-tl-sm border px-3.5 py-3",
            message.error
              ? "border-critical-line bg-critical-soft"
              : unverified
                ? "border-warning-line bg-warning-soft"
                : "border-line bg-surface-2",
          )}
        >
          {message.error ? (
            <div className="flex items-start gap-2 text-[13px] leading-relaxed text-critical-text">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              <span>{message.content}</span>
            </div>
          ) : (
            <CopilotMarkdown text={message.content} />
          )}

          {response && response.sources.length > 0 && (
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-line/70 pt-2.5">
              <span className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-ink-3">
                Based on ReconIQ data
              </span>
              {response.sources.map((s, i) => (
                <Badge key={i} tone="neutral" size="sm">
                  {s.label}
                </Badge>
              ))}
            </div>
          )}
        </div>

        <div className="mt-1.5 flex items-center gap-3 px-1">
          <span className="text-[11px] text-ink-3">{formatClock(message.at)}</span>
          {!message.error && <CopyButton text={message.content} />}
          {message.error && (
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-accent-text hover:underline"
            >
              <RotateCcw className="size-3" /> Retry
            </button>
          )}
          {unverified && (
            <span className="inline-flex items-center gap-1 text-[11px] text-warning-text">
              <ShieldAlert className="size-3" /> Unverified — showing a safe fallback
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function CopilotMessages({
  jobId,
  messages,
  pending,
  onSend,
  onRetry,
}: {
  jobId: string | null;
  messages: CopilotDisplayMessage[];
  pending: boolean;
  onSend: (text: string) => void;
  onRetry: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [stageIdx, setStageIdx] = useState(0);

  useEffect(() => {
    if (!pending) {
      setStageIdx(0);
      return;
    }
    const timer = setInterval(() => setStageIdx((i) => Math.min(i + 1, THINKING_STAGES.length - 1)), 900);
    return () => clearInterval(timer);
  }, [pending]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  if (!jobId) {
    return (
      <EmptyState
        className="h-full"
        icon={<AlertTriangle className="size-5" />}
        title="No reconciliation selected"
        description="The Copilot needs an active reconciliation run to answer questions — open a results page first."
      />
    );
  }

  return (
    <div ref={scrollRef} className="thin-scroll h-full space-y-4 overflow-y-auto px-5 py-5">
      {messages.length === 0 && (
        <div className="space-y-2.5">
          <p className="text-[12.5px] text-ink-2">Try asking:</p>
          <div className="flex flex-col gap-2">
            {STARTER_PROMPTS.map((p) => (
              <button
                key={p}
                onClick={() => onSend(p)}
                className="rounded-lg border border-line bg-surface-2 px-3.5 py-2.5 text-left text-[13px] text-ink-2 transition-colors duration-150 hover:border-ai-line hover:bg-ai-soft hover:text-ai-text"
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}

      {messages.map((m) => (
        <CopilotBubble key={m.id} message={m} onRetry={onRetry} />
      ))}

      {pending && (
        <div className="flex items-center gap-2.5 text-[12.5px] text-ink-3">
          <CopilotAvatar state="thinking" size={24} />
          <span>{THINKING_STAGES[stageIdx]}</span>
        </div>
      )}
    </div>
  );
}
