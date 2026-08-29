import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRecon } from "@/store/ReconProvider";

/**
 * The one-click hackathon path: load the demo batch, open a job, and hand off
 * to the processing screen. Shared by the dashboard, the empty states and the
 * upload screen so the demo behaves identically wherever it is triggered.
 */
export function useDemoRun() {
  const { loadDemoDatasets, startRun } = useRecon();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);

  const run = useCallback(async () => {
    if (starting) return;
    setStarting(true);
    try {
      await loadDemoDatasets();
      const jobId = await startRun();
      navigate(`/processing/${jobId}`);
    } finally {
      setStarting(false);
    }
  }, [starting, loadDemoDatasets, startRun, navigate]);

  return { run, starting };
}
