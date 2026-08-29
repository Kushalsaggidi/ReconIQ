import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import * as api from "@/services/api";
import type {
  DatasetFile,
  DatasetKind,
  ReconciliationSummary,
} from "@/services/types";

const KINDS: DatasetKind[] = ["orders", "settlements", "bank"];

function emptyDataset(kind: DatasetKind): DatasetFile {
  return { kind, name: "", size: 0, rows: null, status: "empty", progress: 0 };
}

interface ReconState {
  datasets: Record<DatasetKind, DatasetFile>;
  isDemo: boolean;
  jobId: string | null;
  summary: ReconciliationSummary | null;

  readyCount: number;
  canRun: boolean;

  attachFile: (kind: DatasetKind, file: File) => Promise<void>;
  removeFile: (kind: DatasetKind) => void;
  loadDemoDatasets: () => void;
  resetDatasets: () => void;
  startRun: () => Promise<string>;
  completeRun: (jobId: string) => void;
  /** Falls back to the demo batch so any screen is deep-linkable. */
  ensureSummary: () => ReconciliationSummary;
}

const Ctx = createContext<ReconState | null>(null);

export function ReconProvider({ children }: { children: ReactNode }) {
  const [datasets, setDatasets] = useState<Record<DatasetKind, DatasetFile>>({
    orders: emptyDataset("orders"),
    settlements: emptyDataset("settlements"),
    bank: emptyDataset("bank"),
  });
  const [isDemo, setIsDemo] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null);

  const patch = useCallback((kind: DatasetKind, next: Partial<DatasetFile>) => {
    setDatasets((prev) => ({ ...prev, [kind]: { ...prev[kind], ...next } }));
  }, []);

  const attachFile = useCallback(
    async (kind: DatasetKind, file: File) => {
      setIsDemo(false);
      patch(kind, {
        kind,
        name: file.name,
        size: file.size,
        status: "uploading",
        progress: 0,
        rows: null,
        error: undefined,
        isDemo: false,
      });
      const result = await api.uploadDataset(kind, file, (p) => patch(kind, { progress: p }));
      patch(kind, result);
    },
    [patch],
  );

  const removeFile = useCallback((kind: DatasetKind) => {
    setDatasets((prev) => ({ ...prev, [kind]: emptyDataset(kind) }));
    setIsDemo(false);
  }, []);

  const loadDemoDatasets = useCallback(() => {
    const files = api.demoDatasetFiles();
    setDatasets({
      orders: files[0],
      settlements: files[1],
      bank: files[2],
    });
    setIsDemo(true);
  }, []);

  const resetDatasets = useCallback(() => {
    setDatasets({
      orders: emptyDataset("orders"),
      settlements: emptyDataset("settlements"),
      bank: emptyDataset("bank"),
    });
    setIsDemo(false);
  }, []);

  const readyCount = KINDS.filter((k) => datasets[k].status === "ready").length;
  // Orders + settlements are mandatory; the bank statement sharpens the match.
  const canRun =
    isDemo || (datasets.orders.status === "ready" && datasets.settlements.status === "ready");

  const startRun = useCallback(async () => {
    const list = KINDS.map((k) => datasets[k]).filter((d) => d.status === "ready");
    const { jobId: id } = await api.runReconciliation({
      datasets: list,
      source: isDemo ? "Demo dataset" : "Manual upload",
    });
    setJobId(id);
    setSummary(null);
    return id;
  }, [datasets, isDemo]);

  const completeRun = useCallback(
    (id: string) => {
      const list = KINDS.map((k) => datasets[k]).filter((d) => d.status === "ready");
      setSummary(api.getResultsSync(id, list.length ? list : undefined));
      setJobId(id);
    },
    [datasets],
  );

  const ensureSummary = useCallback(() => {
    if (summary) return summary;
    const fallback = api.getResultsSync(jobId ?? "RCN-20260828-428");
    return fallback;
  }, [summary, jobId]);

  const value = useMemo<ReconState>(
    () => ({
      datasets,
      isDemo,
      jobId,
      summary,
      readyCount,
      canRun,
      attachFile,
      removeFile,
      loadDemoDatasets,
      resetDatasets,
      startRun,
      completeRun,
      ensureSummary,
    }),
    [
      datasets,
      isDemo,
      jobId,
      summary,
      readyCount,
      canRun,
      attachFile,
      removeFile,
      loadDemoDatasets,
      resetDatasets,
      startRun,
      completeRun,
      ensureSummary,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useRecon() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useRecon must be used inside <ReconProvider>");
  return ctx;
}
