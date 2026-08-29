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
  loadDemoDatasets: () => Promise<void>;
  resetDatasets: () => void;
  startRun: () => Promise<string>;
  completeRun: (jobId: string) => Promise<void>;
  /** Fetches and stores the result set for a job, real GET each time. */
  refreshSummary: (jobId: string) => Promise<void>;
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
      const validationError = await api.validateFileBeforeUpload(file);
      if (validationError) {
        patch(kind, {
          kind,
          name: file.name,
          size: file.size,
          status: "error",
          progress: 100,
          rows: null,
          error: validationError,
          isDemo: false,
        });
        return;
      }
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

  const loadDemoDatasets = useCallback(async () => {
    setIsDemo(true);
    await Promise.all(
      KINDS.map(async (kind) => {
        patch(kind, {
          kind,
          name: api.DATASET_META[kind].demoFile,
          size: 0,
          status: "uploading",
          progress: 0,
          rows: null,
          error: undefined,
          isDemo: true,
        });
        const result = await api.loadDemoDataset(kind, (p) => patch(kind, { progress: p }));
        patch(kind, { ...result, isDemo: true });
      }),
    );
  }, [patch]);

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
    datasets.orders.status === "ready" && datasets.settlements.status === "ready";

  const startRun = useCallback(async () => {
    const orders = datasets.orders;
    const settlements = datasets.settlements;
    const bank = datasets.bank;
    if (!orders.datasetId || !settlements.datasetId) {
      throw new Error("Orders and settlements datasets must be uploaded before running.");
    }
    const { jobId: id } = await api.runReconciliation({
      ordersDatasetId: orders.datasetId,
      settlementsDatasetId: settlements.datasetId,
      bankDatasetId: bank.status === "ready" ? bank.datasetId : undefined,
      source: isDemo ? "Demo dataset" : "Manual upload",
    });
    setJobId(id);
    setSummary(null);
    return id;
  }, [datasets, isDemo]);

  const refreshSummary = useCallback(async (id: string) => {
    const s = await api.getResults(id);
    setSummary(s);
    setJobId(id);
  }, []);

  const completeRun = useCallback(
    async (id: string) => {
      await refreshSummary(id);
    },
    [refreshSummary],
  );

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
      refreshSummary,
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
      refreshSummary,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useRecon() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useRecon must be used inside <ReconProvider>");
  return ctx;
}
