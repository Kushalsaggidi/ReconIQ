import { useEffect, useMemo, useState } from "react";
import { Download, Lock, ShieldCheck } from "lucide-react";
import { formatDateTime, formatNumber } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, SectionHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Segmented } from "@/components/ui/Field";
import { Skeleton } from "@/components/ui/Misc";
import { AuditTimeline } from "@/components/recon/AuditTimeline";
import { useRecon } from "@/store/ReconProvider";
import * as api from "@/services/api";
import type { AuditEvent } from "@/services/types";

type Lens = "all" | "deterministic" | "ai";

export function AuditLogs() {
  const { ensureSummary } = useRecon();
  const summary = useMemo(() => ensureSummary(), [ensureSummary]);
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [lens, setLens] = useState<Lens>("all");

  useEffect(() => {
    let alive = true;
    api.getAuditTrail(summary.jobId).then((e) => {
      if (alive) setEvents(e);
    });
    return () => {
      alive = false;
    };
  }, [summary.jobId]);

  const filtered = useMemo(() => {
    if (!events) return null;
    if (lens === "all") return events;
    return events.filter((e) => e.engine === lens);
  }, [events, lens]);

  const counts = useMemo(() => {
    if (!events) return { all: 0, deterministic: 0, ai: 0 };
    return {
      all: events.length,
      deterministic: events.filter((e) => e.engine === "deterministic").length,
      ai: events.filter((e) => e.engine === "ai").length,
    };
  }, [events]);

  const exportJson = () => {
    if (!events) return;
    const blob = new Blob([JSON.stringify({ jobId: summary.jobId, events }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${summary.jobId}-audit-trail.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <SectionHeader
        eyebrow={summary.jobId}
        title="Audit Trail"
        description="An append-only record of every step, with the layer that performed it. Nothing here is editable — the trail is sealed when the report is generated."
        actions={
          <Button variant="secondary" onClick={exportJson}>
            <Download className="size-4" />
            Export trail
          </Button>
        }
      />

      {/* ---------------- seal ---------------- */}
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-4 py-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-good-soft text-good-text">
              <ShieldCheck className="size-4.5" />
            </span>
            <div>
              <p className="text-[13.5px] font-semibold text-ink">Result set sealed</p>
              <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-2">
                {formatNumber(summary.recordsProcessed)} records · {formatNumber(summary.exceptions)} exceptions ·
                completed {formatDateTime(summary.completedAt)}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral" size="sm" icon={<Lock className="size-3" />}>
              sha256:9c41e…
            </Badge>
            <Badge tone="good" size="sm">
              12 events
            </Badge>
          </div>
        </CardBody>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented
          value={lens}
          onChange={setLens}
          options={[
            { value: "all", label: "All events", count: counts.all },
            { value: "deterministic", label: "Engine", count: counts.deterministic },
            { value: "ai", label: "AI Analyst", count: counts.ai },
          ]}
        />
        <span className="text-[11.5px] text-ink-3">Times are in IST · newest last</span>
      </div>

      {!filtered && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      )}

      {filtered && <AuditTimeline events={filtered} />}
    </div>
  );
}
