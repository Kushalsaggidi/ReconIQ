import { Search, X, ChevronDown } from "lucide-react";
import type { ReactNode, SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function SearchInput({
  value,
  onChange,
  placeholder = "Search",
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(
          "h-9.5 w-full rounded-lg border border-line bg-surface pl-9 pr-8 text-[13.5px] text-ink",
          "placeholder:text-ink-3 transition-[border-color,box-shadow] duration-150",
          "hover:border-line-strong focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/12",
        )}
      />
      {value && (
        <button
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded-md text-ink-3 transition-colors hover:bg-surface-3 hover:text-ink"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}

export function Select({
  label,
  className,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  return (
    <div className={cn("relative", className)}>
      {label && (
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[13px] text-ink-3">
          {label}
        </span>
      )}
      <select
        className={cn(
          "h-9.5 w-full cursor-pointer appearance-none rounded-lg border border-line bg-surface pr-8 text-[13.5px] font-medium text-ink",
          "transition-[border-color,box-shadow] duration-150 hover:border-line-strong",
          "focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent/12",
          label ? "pl-[var(--label-pad)]" : "pl-3",
        )}
        style={label ? ({ "--label-pad": `${label.length * 6.6 + 18}px` } as React.CSSProperties) : undefined}
        {...props}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-ink-3" />
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  options: { value: T; label: ReactNode; count?: number }[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-0.5 rounded-lg border border-line bg-surface-2 p-0.5",
        className,
      )}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            className={cn(
              "relative inline-flex h-8 items-center gap-1.5 rounded-[7px] px-3 text-[13px] font-medium",
              "transition-[background-color,color,box-shadow] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)]",
              active
                ? "bg-surface text-ink shadow-xs"
                : "text-ink-2 hover:text-ink",
            )}
          >
            {o.label}
            {o.count !== undefined && (
              <span className={cn("tnum text-[11.5px]", active ? "text-ink-3" : "text-ink-3")}>
                {o.count.toLocaleString("en-IN")}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-6 py-3.5">
      <span className="min-w-0">
        <span className="block text-[13.5px] font-medium text-ink">{label}</span>
        {description && <span className="mt-0.5 block text-[12.5px] leading-relaxed text-ink-2">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 h-5.5 w-9.5 shrink-0 rounded-full transition-colors duration-200",
          checked ? "bg-accent" : "bg-line-strong",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 size-4.5 rounded-full bg-white shadow-sm transition-[left] duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]",
            checked ? "left-[18px]" : "left-0.5",
          )}
        />
      </button>
    </label>
  );
}
