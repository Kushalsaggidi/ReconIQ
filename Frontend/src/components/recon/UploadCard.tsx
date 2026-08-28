import { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  FileSpreadsheet,
  Landmark,
  Receipt,
  RefreshCw,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { cn, formatBytes, formatNumber } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { ProgressBar } from "@/components/ui/Misc";
import { DATASET_META } from "@/services/api";
import type { DatasetFile, DatasetKind } from "@/services/types";

const ICONS: Record<DatasetKind, typeof Receipt> = {
  orders: Receipt,
  settlements: Building2,
  bank: Landmark,
};

export function UploadCard({
  dataset,
  required,
  onFile,
  onRemove,
}: {
  dataset: DatasetFile;
  required?: boolean;
  onFile: (file: File) => void;
  onRemove: () => void;
}) {
  const meta = DATASET_META[dataset.kind];
  const Icon = ICONS[dataset.kind];
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const state = dataset.status;

  return (
    <div
      className={cn(
        "relative flex flex-col overflow-hidden rounded-xl border bg-surface shadow-xs transition-[border-color,box-shadow,background-color] duration-200",
        dragging
          ? "border-accent bg-accent-soft ring-3 ring-accent/12"
          : state === "ready"
            ? "border-good-line"
            : state === "error"
              ? "border-critical-line"
              : "border-line hover:border-line-strong hover:shadow-sm",
      )}
      onDragOver={(e) => {
        e.preventDefault();
        if (state !== "uploading") setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const f = e.dataTransfer.files?.[0];
        if (f && state !== "uploading") onFile(f);
      }}
    >
      <div className="flex items-start justify-between gap-3 px-5 pt-5">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={cn(
              "grid size-9 shrink-0 place-items-center rounded-lg border transition-colors duration-200",
              state === "ready"
                ? "border-good-line bg-good-soft text-good-text"
                : "border-line bg-surface-2 text-ink-2",
            )}
          >
            <Icon className="size-4.5" strokeWidth={2} />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-[14px] font-semibold tracking-[-0.01em] text-ink">{meta.title}</h3>
              {required ? (
                <span className="text-[10.5px] font-semibold uppercase tracking-wide text-ink-3">required</span>
              ) : (
                <span className="text-[10.5px] font-semibold uppercase tracking-wide text-ink-3">optional</span>
              )}
            </div>
            <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-2">{meta.description}</p>
          </div>
        </div>
        {state === "ready" && (
          <CheckCircle2 className="size-5 shrink-0 text-good" strokeWidth={2.25} />
        )}
      </div>

      <div className="flex flex-1 flex-col px-5 pb-5 pt-4">
        <AnimatePresence mode="wait" initial={false}>
          {state === "empty" && (
            <motion.button
              key="empty"
              type="button"
              onClick={() => inputRef.current?.click()}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.16 }}
              className={cn(
                "group flex flex-1 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line-strong",
                "px-4 py-7 text-center transition-colors duration-150 hover:border-accent hover:bg-accent-soft/50",
              )}
            >
              <UploadCloud className="size-5 text-ink-3 transition-colors duration-150 group-hover:text-accent" />
              <span className="text-[12.5px] font-medium text-ink">
                Drop file or <span className="text-accent-text underline decoration-accent-soft-line">browse</span>
              </span>
              <span className="text-[11.5px] text-ink-3">{meta.accepts.replace(/\./g, "").toUpperCase()} · up to 200 MB</span>
            </motion.button>
          )}

          {state === "uploading" && (
            <motion.div
              key="uploading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.16 }}
              className="flex flex-1 flex-col justify-center rounded-lg border border-line bg-surface-2 px-4 py-5"
            >
              <div className="flex items-center gap-2.5">
                <FileSpreadsheet className="size-4 shrink-0 text-accent" />
                <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-ink">{dataset.name}</span>
                <span className="tnum shrink-0 text-[12px] font-medium text-ink-2">{dataset.progress}%</span>
              </div>
              <ProgressBar percent={dataset.progress} height={6} animated className="mt-3" />
              <p className="mt-2.5 text-[11.5px] text-ink-3">
                Uploading · {formatBytes(Math.round((dataset.size * dataset.progress) / 100))} of{" "}
                {formatBytes(dataset.size)}
              </p>
            </motion.div>
          )}

          {state === "ready" && (
            <motion.div
              key="ready"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              className="flex flex-1 flex-col justify-center rounded-lg border border-line bg-surface-2 px-4 py-4"
            >
              <div className="flex items-start gap-2.5">
                <FileSpreadsheet className="mt-0.5 size-4 shrink-0 text-good" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12.5px] font-medium text-ink">{dataset.name}</p>
                  <p className="tnum mt-1 text-[11.5px] text-ink-3">
                    {formatBytes(dataset.size)}
                    {dataset.rows !== null && <> · {formatNumber(dataset.rows)} rows</>}
                    {dataset.isDemo && <> · demo</>}
                  </p>
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-3">
                <span className="tnum truncate text-[11px] text-ink-3">{dataset.checksum}</span>
                <div className="flex shrink-0 items-center gap-1">
                  <SmallAction onClick={() => inputRef.current?.click()} icon={RefreshCw} label="Replace" />
                  <SmallAction onClick={onRemove} icon={Trash2} label="Remove" danger />
                </div>
              </div>
            </motion.div>
          )}

          {state === "error" && (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex flex-1 flex-col justify-center rounded-lg border border-critical-line bg-critical-soft px-4 py-4"
            >
              <div className="flex items-start gap-2.5">
                <AlertCircle className="mt-0.5 size-4 shrink-0 text-critical" />
                <div className="min-w-0">
                  <p className="truncate text-[12.5px] font-medium text-ink">{dataset.name}</p>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-critical-text">{dataset.error}</p>
                </div>
              </div>
              <div className="mt-3 flex items-center gap-1 border-t border-critical-line pt-3">
                <SmallAction onClick={() => inputRef.current?.click()} icon={RefreshCw} label="Choose another file" />
                <SmallAction onClick={onRemove} icon={Trash2} label="Remove" danger />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {state === "ready" && dataset.isDemo && (
          <Badge tone="accent" size="sm" className="mt-3 self-start">
            Demo dataset loaded
          </Badge>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={meta.accepts}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function SmallAction({
  onClick,
  icon: Icon,
  label,
  danger,
}: {
  onClick: () => void;
  icon: typeof RefreshCw;
  label: string;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11.5px] font-medium transition-colors duration-150",
        danger ? "text-ink-2 hover:bg-critical-soft hover:text-critical-text" : "text-ink-2 hover:bg-surface-3 hover:text-ink",
      )}
    >
      <Icon className="size-3.5" />
      {label}
    </button>
  );
}
