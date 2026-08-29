import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, CheckCircle2, Info, PlayCircle, RotateCcw, Sparkles } from "lucide-react";
import { formatNumber } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { SectionHeader } from "@/components/ui/Card";
import { HowItWorks } from "@/components/recon/Pipeline";
import { UploadCard } from "@/components/recon/UploadCard";
import { useRecon } from "@/store/ReconProvider";
import type { DatasetKind } from "@/services/types";

const ORDER: DatasetKind[] = ["orders", "settlements", "bank"];

export function NewReconciliation() {
  const {
    datasets,
    isDemo,
    canRun,
    readyCount,
    attachFile,
    removeFile,
    loadDemoDatasets,
    resetDatasets,
    startRun,
  } = useRecon();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);

  const totalRows = ORDER.reduce((sum, k) => sum + (datasets[k].rows ?? 0), 0);
  const uploading = ORDER.some((k) => datasets[k].status === "uploading");
  const errored = ORDER.filter((k) => datasets[k].status === "error");

  const start = async () => {
    setStarting(true);
    const jobId = await startRun();
    navigate(`/processing/${jobId}`);
  };

  return (
    <div className="space-y-7">
      <SectionHeader
        title="Start a new reconciliation"
        description="Upload the required datasets and we'll reconcile them automatically."
        actions={
          <div className="flex items-center gap-2">
            {readyCount > 0 && (
              <Button variant="ghost" size="sm" onClick={resetDatasets}>
                <RotateCcw className="size-3.5" />
                Clear all
              </Button>
            )}
            <Button variant="ai" onClick={loadDemoDatasets}>
              <Sparkles className="size-4" />
              Try Demo Dataset
            </Button>
          </div>
        }
      />

      {/* ---------------- uploads ---------------- */}
      <section className="grid gap-5 lg:grid-cols-3">
        {ORDER.map((kind) => (
          <UploadCard
            key={kind}
            dataset={datasets[kind]}
            required={kind !== "bank"}
            onFile={(file) => attachFile(kind, file)}
            onRemove={() => removeFile(kind)}
          />
        ))}
      </section>

      {/* ---------------- demo banner ---------------- */}
      <AnimatePresence>
        {isDemo && (
          <motion.div
            initial={{ opacity: 0, y: -6, height: 0 }}
            animate={{ opacity: 1, y: 0, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-ai-line bg-ai-soft px-5 py-3.5">
              <Sparkles className="size-4 shrink-0 text-ai" />
              <p className="min-w-0 flex-1 text-[13px] leading-relaxed text-ink">
                <span className="font-semibold text-ai-text">Demo dataset loaded.</span> A 100,000-record August 2026
                settlement batch, including one deliberately unresolved transaction so you can see how the product
                handles a case it cannot explain.
              </p>
              <Button variant="secondary" size="sm" onClick={resetDatasets}>
                Use my own files
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {errored.length > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-critical-line bg-critical-soft px-5 py-3.5">
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-critical" />
          <p className="text-[13px] leading-relaxed text-ink">
            <span className="font-semibold text-critical-text">
              {errored.length} file{errored.length > 1 ? "s" : ""} could not be read.
            </span>{" "}
            Replace the highlighted upload{errored.length > 1 ? "s" : ""} to continue. Nothing is sent to the engine
            until every dataset parses cleanly.
          </p>
        </div>
      )}

      <HowItWorks />

      {/* ---------------- run bar ---------------- */}
      <section className="sticky bottom-4 z-20">
        <div className="flex flex-col gap-4 rounded-xl border border-line bg-surface/95 px-5 py-4 shadow-md backdrop-blur-md sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span
              className={`mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg ${
                canRun ? "bg-good-soft text-good-text" : "bg-surface-3 text-ink-3"
              }`}
            >
              {canRun ? <CheckCircle2 className="size-4" /> : <Info className="size-4" />}
            </span>
            <div className="min-w-0">
              <p className="text-[13.5px] font-medium text-ink">
                {canRun
                  ? `Ready to reconcile ${formatNumber(totalRows || 100000)} records`
                  : "Orders and settlement datasets are required"}
              </p>
              <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-2">
                {canRun ? (
                  <>
                    {readyCount} of 3 datasets attached
                    {datasets.bank.status !== "ready" && " · a bank statement improves match confidence"}
                  </>
                ) : (
                  "Attach both files, or load the demo dataset to run the full pipeline now."
                )}
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2.5">
            {isDemo && (
              <Badge tone="ai" size="sm">
                Demo mode
              </Badge>
            )}
            <Button size="lg" disabled={!canRun || uploading} loading={starting} onClick={start}>
              {!starting && <PlayCircle className="size-4" />}
              Run Reconciliation
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
