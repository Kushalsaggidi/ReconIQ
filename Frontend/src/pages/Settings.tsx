import { useState } from "react";
import { Cpu, Moon, Server, Sparkles } from "lucide-react";
import { Card, CardBody, CardHeader, SectionHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Select, Toggle } from "@/components/ui/Field";
import { DetailRow } from "@/components/ui/Misc";
import { useTheme } from "@/store/ThemeProvider";
import { API_BASE } from "@/services/api";

export function Settings() {
  const { theme, toggle } = useTheme();
  const [tolerance, setTolerance] = useState("1.00");
  const [aiEnabled, setAiEnabled] = useState(true);
  const [autoClose, setAutoClose] = useState(true);
  const [holdUnresolved, setHoldUnresolved] = useState(true);
  const [notify, setNotify] = useState(false);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <SectionHeader
        title="Settings"
        description="Matching rules are enforced by the engine. AI settings only affect how exceptions are explained — never how they are calculated."
      />

      {/* ---------------- matching ---------------- */}
      <Card>
        <CardHeader
          title="Matching rules"
          description="Applied deterministically to every record before any interpretation step."
          actions={<Badge tone="accent" size="sm" icon={<Cpu className="size-3" />}>Engine</Badge>}
        />
        <CardBody className="py-2">
          <div className="flex items-center justify-between gap-6 border-b border-line py-3.5">
            <div>
              <p className="text-[13.5px] font-medium text-ink">Rounding tolerance</p>
              <p className="mt-0.5 text-[12.5px] text-ink-2">
                Differences at or below this value are bucketed as rounding.
              </p>
            </div>
            <Select
              value={tolerance}
              onChange={(e) => setTolerance(e.target.value)}
              className="w-[132px] shrink-0"
            >
              {["0.50", "1.00", "2.00", "5.00"].map((v) => (
                <option key={v} value={v}>
                  ₹{v}
                </option>
              ))}
            </Select>
          </div>
          <div className="divide-y divide-line">
            <Toggle
              checked={autoClose}
              onChange={setAutoClose}
              label="Auto-close fully explained exceptions"
              description="Close an exception when fee, tax and refund records account for the variance to the paise."
            />
            <Toggle
              checked={holdUnresolved}
              onChange={setHoldUnresolved}
              label="Always hold unresolved variances"
              description="Never close a record whose variance no source document explains. Recommended — and required by most audit policies."
            />
          </div>
        </CardBody>
      </Card>

      {/* ---------------- AI ---------------- */}
      <Card>
        <CardHeader
          title="AI-assisted analysis"
          description="The model classifies and explains exceptions. It has no write access and cannot alter a figure."
          actions={<Badge tone="ai" size="sm" icon={<Sparkles className="size-3" />}>AI layer</Badge>}
        />
        <CardBody className="py-2">
          <div className="divide-y divide-line">
            <Toggle
              checked={aiEnabled}
              onChange={setAiEnabled}
              label="Enable exception classification"
              description="With this off, exceptions are still detected and bucketed by rule — you simply lose the natural-language explanation."
            />
            <Toggle
              checked={notify}
              onChange={setNotify}
              label="Email me when unresolved exceptions exceed 1%"
              description="Sent once per batch to the finance operations distribution list."
            />
          </div>
          <div className="mt-2 rounded-lg border border-ai-line bg-ai-soft px-4 py-3">
            <p className="text-[12px] leading-relaxed text-ink-2">
              <span className="font-semibold text-ai-text">Guardrail.</span> The model receives only the computed
              variance and the matched records. It cannot post entries, cannot change amounts, and cannot mark an
              unresolved record as resolved.
            </p>
          </div>
        </CardBody>
      </Card>

      {/* ---------------- appearance + connection ---------------- */}
      <Card>
        <CardHeader title="Appearance" actions={<Moon className="size-4 text-ink-3" />} />
        <CardBody className="py-2">
          <Toggle
            checked={theme === "dark"}
            onChange={toggle}
            label="Dark theme"
            description="Chart palettes are re-stepped for the dark surface rather than inverted."
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Backend connection"
          description="The UI talks to a mock service layer today. Point these at the Python service to go live."
          actions={<Badge tone="warning" size="sm" icon={<Server className="size-3" />}>Mock</Badge>}
        />
        <CardBody className="py-2">
          <div className="divide-y divide-line">
            <DetailRow label="Base URL" value={API_BASE} mono />
            <DetailRow label="POST /reconciliation/upload" value="mocked" mono tone="muted" />
            <DetailRow label="POST /reconciliation/run" value="mocked" mono tone="muted" />
            <DetailRow label="GET /reconciliation/:jobId/status" value="mocked" mono tone="muted" />
            <DetailRow label="GET /reconciliation/:jobId/results" value="mocked" mono tone="muted" />
            <DetailRow label="GET /reconciliation/:jobId/exceptions" value="mocked" mono tone="muted" />
            <DetailRow label="GET /reconciliation/:jobId/audit" value="mocked" mono tone="muted" />
          </div>
          <p className="mt-3 text-[12px] leading-relaxed text-ink-3">
            Every call above lives in <span className="tnum font-medium text-ink-2">src/services/api.ts</span>. Swap the
            function bodies for fetch calls and no component changes.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}
