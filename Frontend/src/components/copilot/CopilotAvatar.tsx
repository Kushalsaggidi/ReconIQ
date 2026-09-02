import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

export type CopilotAvatarState = "idle" | "thinking" | "success" | "error" | "uncertain";

const RING: Record<CopilotAvatarState, string> = {
  idle: "ring-ai-line",
  thinking: "ring-ai",
  success: "ring-good-line",
  error: "ring-critical-line",
  uncertain: "ring-warning-line",
};

const PUPIL: Record<CopilotAvatarState, string> = {
  idle: "bg-ai-text",
  thinking: "bg-ai-text",
  success: "bg-good-text",
  error: "bg-critical-text",
  uncertain: "bg-warning-text",
};

const DOT: Record<CopilotAvatarState, string> = {
  idle: "",
  thinking: "bg-ai pulse-ring",
  success: "bg-good",
  error: "bg-critical",
  uncertain: "bg-warning",
};

/**
 * A small, premium-feeling assistant orb — not a generic bot icon.
 *
 * Blinking is a single JS timer per mount (cheap, bounded); the only
 * continuous CSS animation runs while `state === "thinking"`, and stops the
 * instant the state changes, so an idle panel costs nothing on the GPU.
 */
export function CopilotAvatar({
  state = "idle",
  size = 32,
  className,
}: {
  state?: CopilotAvatarState;
  size?: number;
  className?: string;
}) {
  const [blink, setBlink] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      const delay = 2600 + Math.random() * 2800;
      timer = setTimeout(() => {
        if (!alive) return;
        setBlink(true);
        timer = setTimeout(() => {
          if (!alive) return;
          setBlink(false);
          schedule();
        }, 130);
      }, delay);
    };
    schedule();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  return (
    <div
      className={cn(
        "relative grid shrink-0 place-items-center rounded-full bg-ai-soft ring-2 transition-colors duration-300",
        RING[state],
        className,
      )}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <div className="flex items-center" style={{ gap: size * 0.14, width: size * 0.5 }}>
        {[0, 1].map((i) => (
          <span
            key={i}
            className={cn(
              "block rounded-full transition-transform duration-100",
              PUPIL[state],
              state === "thinking" && "copilot-eye-thinking",
            )}
            style={{
              width: size * 0.17,
              height: size * 0.17,
              transform: blink ? "scaleY(0.15)" : undefined,
            }}
          />
        ))}
      </div>
      {DOT[state] && (
        <span
          className={cn("absolute rounded-full ring-2 ring-surface", DOT[state])}
          style={{ width: size * 0.28, height: size * 0.28, bottom: -1, right: -1 }}
        />
      )}
    </div>
  );
}
