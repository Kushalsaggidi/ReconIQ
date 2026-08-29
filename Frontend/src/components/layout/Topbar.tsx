import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, Menu, Moon, Search, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import { IconButton } from "@/components/ui/Button";
import { useTheme } from "@/store/ThemeProvider";
import { useRecon } from "@/store/ReconProvider";

export function Topbar({
  title,
  breadcrumb,
  actions,
  onOpenNav,
}: {
  title: string;
  breadcrumb?: string[];
  actions?: React.ReactNode;
  onOpenNav: () => void;
}) {
  const { theme, toggle } = useTheme();
  const { jobId, summary } = useRecon();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  // ⌘K / Ctrl+K focuses the order lookup — the field finance ops actually uses.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        document.getElementById("global-search")?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const v = query.trim();
    if (!v) return;
    if (/^O-?\d{5}$/i.test(v)) navigate(`/exceptions/${v.toUpperCase().replace(/^O(?!-)/, "O-")}`);
    else navigate(`/exceptions?q=${encodeURIComponent(v)}`);
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur-md sm:px-6">
      <button
        onClick={onOpenNav}
        aria-label="Open navigation"
        className="grid size-9 shrink-0 place-items-center rounded-lg text-ink-2 hover:bg-surface-3 lg:hidden"
      >
        <Menu className="size-4.5" />
      </button>

      <div className="min-w-0 flex-1">
        {breadcrumb && breadcrumb.length > 0 && (
          <nav className="mb-0.5 flex items-center gap-1 text-[11.5px] text-ink-3">
            {breadcrumb.map((b, i) => (
              <span key={b} className="flex items-center gap-1">
                {i > 0 && <ChevronRight className="size-3" />}
                <span className="truncate">{b}</span>
              </span>
            ))}
          </nav>
        )}
        <h1 className="truncate text-[15px] font-semibold tracking-[-0.015em] text-ink">{title}</h1>
      </div>

      {/* current job status, when there is one */}
      {(summary || jobId) && (
        <button
          onClick={() => navigate(summary ? `/results/${summary.jobId}` : "/new")}
          className={cn(
            "hidden items-center gap-2 rounded-lg border border-line bg-surface-2 py-1.5 pl-2.5 pr-3 md:inline-flex",
            "transition-colors duration-150 hover:border-line-strong hover:bg-surface-3",
          )}
        >
          <span className="size-1.5 rounded-full bg-good" />
          <span className="text-[11.5px] text-ink-2">
            <span className="tnum font-medium text-ink">{summary?.jobId ?? jobId}</span>
            <span className="mx-1.5 text-line-strong">·</span>
            {summary ? `${summary.matchRate.toFixed(2)}% matched` : "in progress"}
          </span>
        </button>
      )}

      <form onSubmit={submit} className="relative hidden w-56 shrink-0 xl:block">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-ink-3" />
        <input
          id="global-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find order or payment ID"
          className="h-9 w-full rounded-lg border border-line bg-surface-2 pl-9 pr-11 text-[12.5px] text-ink placeholder:text-ink-3 transition-[border-color,box-shadow] duration-150 hover:border-line-strong focus:border-accent focus:bg-surface focus:outline-none focus:ring-3 focus:ring-accent/12"
        />
        <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-line bg-surface px-1.5 py-0.5 text-[10px] font-medium text-ink-3">
          ⌘K
        </kbd>
      </form>

      {actions}

      <IconButton label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={toggle}>
        {theme === "dark" ? <Sun className="size-4.5" /> : <Moon className="size-4.5" />}
      </IconButton>

      <div className="flex items-center gap-2.5 border-l border-line pl-3">
        <div className="hidden text-right sm:block">
          <div className="text-[12px] font-medium leading-tight text-ink">Kushal Saggidi</div>
          <div className="text-[11px] leading-tight text-ink-3">Finance Operations</div>
        </div>
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent-soft text-[11.5px] font-semibold text-accent-text ring-1 ring-accent-soft-line">
          KS
        </span>
      </div>
    </header>
  );
}
