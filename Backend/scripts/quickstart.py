"""Try ReconIQ in minutes -- one command, no server to keep running.

    python scripts/quickstart.py

Generates the bundled demo dataset if it isn't there yet, drives the real
FastAPI app in-process (the same routes `uvicorn` would serve, via
`TestClient` -- no port, no separate process to manage), and prints the
reconciliation summary. Defaults to `LLM_PROVIDER=null` (the deterministic
fallback explainer) so it works with zero configuration and no API key; set
`LLM_PROVIDER=gemini` with `LLM_API_KEY` in the environment first if you want
this same run to use live Gemini explanations instead.

This exercises the exact upload -> run -> poll -> results flow documented
under "Try it end to end" in the README, without the manual dataset-id
copy-pasting between curl commands.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("LLM_PROVIDER", "null")
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/quickstart.db")

DEMO_DIR = ROOT / "data" / "demo"


def ensure_demo_data() -> None:
    if all((DEMO_DIR / f"{n}.csv").exists() for n in ("orders", "settlements", "bank_statement")):
        return
    print(f"Generating demo dataset in {DEMO_DIR} ...")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_data.py"), "--records", "1000", "--out", str(DEMO_DIR)],
        check=True, cwd=ROOT,
    )


def main() -> None:
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("app.reconciliation.engine").setLevel(logging.WARNING)

    ensure_demo_data()

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        dataset_ids: dict[str, str] = {}
        for kind, filename in (
            ("orders", "orders.csv"),
            ("settlements", "settlements.csv"),
            ("bank", "bank_statement.csv"),
        ):
            path = DEMO_DIR / filename
            with path.open("rb") as fh:
                resp = client.post(
                    "/api/reconciliation/upload",
                    data={"kind": kind},
                    files={"file": (filename, fh, "text/csv")},
                )
            resp.raise_for_status()
            body = resp.json()
            dataset_ids[kind] = body["datasetId"]
            print(f"  uploaded {filename:<20} -> {body['rows']:,} rows accepted, {body['rejected']} rejected")

        run_resp = client.post(
            "/api/reconciliation/run",
            json={
                "ordersDatasetId": dataset_ids["orders"],
                "settlementsDatasetId": dataset_ids["settlements"],
                "bankDatasetId": dataset_ids["bank"],
            },
        )
        run_resp.raise_for_status()
        job_id = run_resp.json()["jobId"]
        print(f"\n  job {job_id} queued, polling for completion...")

        for _ in range(200):
            status = client.get(f"/api/reconciliation/{job_id}/status").json()
            if status["status"] in ("completed", "failed"):
                break
            time.sleep(0.1)
        else:
            print("  job did not finish in time"); sys.exit(1)

        results = client.get(f"/api/reconciliation/{job_id}/results").json()

    print()
    print("=" * 64)
    print(f"  Records processed : {results['recordsProcessed']:,}")
    print(f"  Match rate        : {results['matchRate']:.2f}%")
    print(f"  Matched           : {results['matched']:,}")
    print(f"  Exceptions        : {results['exceptions']:,}")
    print(f"  Unresolved        : {results['unresolved']:,}")
    print(f"  AI status         : {results['aiStatus']} ({results['aiAnalysedCount']} classified)")
    print("=" * 64)
    print(
        f"\nJob {job_id} is in {os.environ['DATABASE_URL']} -- start the real API\n"
        f"(`uvicorn app.main:app --reload`) and open the frontend to browse it,\n"
        f"or continue with the curl commands under 'Try it end to end' in the README."
    )


if __name__ == "__main__":
    main()
