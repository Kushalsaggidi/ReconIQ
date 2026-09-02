import { useNavigate } from "react-router-dom";
import { Cpu, FileSpreadsheet, PlayCircle, PlusCircle, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/Misc";
import { PipelineStrip } from "@/components/recon/Pipeline";
import { useDemoRun } from "@/lib/useDemoRun";

/**
 * The overview is a fresh landing page on every visit — it never surfaces a
 * previous run's numbers. Past reconciliations live in History; opening one
 * there takes you to its results page.
 */
export function Overview() {
  const navigate = useNavigate();
  const { run, starting } = useDemoRun();

  return (
    <div className="space-y-7">
      <section className="max-w-2xl">
        <div className="mb-3 flex items-center gap-2">
          <Badge tone="accent" size="sm" icon={<Cpu className="size-3" />}>
            Reconciliation engine v4.2
          </Badge>
          <Badge tone="ai" size="sm" icon={<Sparkles className="size-3" />}>
            AI-assisted exception analysis
          </Badge>
        </div>
        <h1 className="text-[30px] font-semibold leading-[1.15] tracking-[-0.03em] text-ink sm:text-[34px]">
          Settlement Reconciliation
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-2">
          Reconcile payment settlements, identify exceptions, and understand every discrepancy.
        </p>
      </section>

      <Card>
        <EmptyState
          icon={<FileSpreadsheet className="size-5" />}
          title="Run a reconciliation to see results"
          description="Upload your orders, settlements and bank statement — or try the bundled demo batch — and you'll be taken straight to the results. Looking for a past run? Check Reconciliation History."
          action={
            <div className="flex flex-wrap items-center justify-center gap-2.5">
              <Button size="lg" onClick={() => navigate("/new")}>
                <PlusCircle className="size-4" />
                New Reconciliation
              </Button>
              <Button size="lg" variant="ai" onClick={run} loading={starting}>
                {!starting && <PlayCircle className="size-4" />}
                Try Demo Dataset
              </Button>
            </div>
          }
        />
      </Card>

      <PipelineStrip />
    </div>
  );
}
