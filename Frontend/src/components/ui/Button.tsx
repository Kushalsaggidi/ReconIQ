import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "ai";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-ink shadow-xs hover:bg-accent-hover active:bg-accent-press disabled:bg-line-strong disabled:text-ink-3 disabled:shadow-none",
  secondary:
    "bg-surface text-ink border border-line-strong shadow-xs hover:bg-surface-2 hover:border-line-strong active:bg-surface-3 disabled:text-ink-3 disabled:bg-surface-2",
  ghost: "text-ink-2 hover:bg-surface-3 hover:text-ink disabled:text-ink-3",
  danger:
    "bg-critical text-white shadow-xs hover:brightness-95 active:brightness-90 disabled:bg-line-strong disabled:text-ink-3",
  ai: "bg-ai-soft text-ai-text border border-ai-line hover:brightness-[0.98]",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5 rounded-md",
  md: "h-9.5 px-4 text-sm gap-2 rounded-lg",
  lg: "h-11 px-5 text-[15px] gap-2 rounded-lg",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", loading, disabled, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center whitespace-nowrap font-medium",
        "transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)]",
        "active:scale-[0.985] disabled:pointer-events-none disabled:active:scale-100",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {loading && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  );
});

export const IconButton = forwardRef<HTMLButtonElement, ButtonProps & { label: string }>(
  function IconButton({ className, label, children, ...props }, ref) {
    return (
      <button
        ref={ref}
        aria-label={label}
        title={label}
        className={cn(
          "inline-flex size-9 items-center justify-center rounded-lg text-ink-2",
          "transition-colors duration-150 hover:bg-surface-3 hover:text-ink",
          "disabled:pointer-events-none disabled:text-ink-3",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);
