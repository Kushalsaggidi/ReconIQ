"""Scaling benchmark.

    python scripts/benchmark.py                       # 100, 1k, 10k, 100k
    python scripts/benchmark.py --sizes 1000 100000
    python scripts/benchmark.py --sizes 1000000 --skip-generate

Measures the deterministic path only -- generate, ingest, reconcile -- because
that is the part whose cost scales with the dataset.  The AI pass is excluded
by design: it is bounded by ``AI_MAX_EXCEPTIONS_PER_JOB`` and so is O(1) in the
record count, which is the property worth demonstrating separately.

Not a production benchmark.  It exists to answer one question: does the curve
stay linear as the data grows?
"""

from __future__ import annotations

import argparse
import gc
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.enums import DatasetKind  # noqa: E402
from app.ingestion.loader import load_dataset  # noqa: E402
from app.reconciliation.config import ReconciliationConfig  # noqa: E402
from app.reconciliation.engine import ReconciliationEngine  # noqa: E402
from scripts.generate_data import generate  # noqa: E402

try:
    import psutil

    _PROCESS = psutil.Process()
except Exception:  # psutil is optional -- memory columns degrade to n/a
    _PROCESS = None


def rss_mb() -> float:
    return _PROCESS.memory_info().rss / 1e6 if _PROCESS else float("nan")


def fmt(value: float, suffix: str = "") -> str:
    return "n/a" if value != value else f"{value:,.1f}{suffix}"


def run_size(size: int, work_dir: Path, *, batch_size: int, skip_generate: bool) -> dict:
    data_dir = work_dir / str(size)
    gc.collect()
    baseline = rss_mb()

    # -- generate ------------------------------------------------------
    t0 = time.perf_counter()
    if not skip_generate or not (data_dir / "orders.csv").exists():
        generate(size, data_dir, seed=7)
    generate_s = time.perf_counter() - t0

    # -- ingest --------------------------------------------------------
    t0 = time.perf_counter()
    orders = load_dataset(data_dir / "orders.csv", DatasetKind.ORDERS,
                          chunk_size=batch_size, compute_checksum=False)
    settlements = load_dataset(data_dir / "settlements.csv", DatasetKind.SETTLEMENTS,
                               chunk_size=batch_size, compute_checksum=False)
    bank = load_dataset(data_dir / "bank_statement.csv", DatasetKind.BANK,
                        chunk_size=batch_size, compute_checksum=False)
    ingest_s = time.perf_counter() - t0
    after_ingest = rss_mb()

    # -- reconcile -----------------------------------------------------
    engine = ReconciliationEngine(ReconciliationConfig(batch_size=batch_size))
    t0 = time.perf_counter()
    result = engine.run(
        orders.records, settlements.records, bank.records,
        collect_outcomes=False,   # the shape a large job actually runs in
    )
    reconcile_s = time.perf_counter() - t0
    peak = rss_mb()

    metrics = result.metrics
    total = ingest_s + reconcile_s
    return {
        "size": size,
        "rows": metrics.total_records,
        "rejected": orders.rejected_count,
        "generate_s": generate_s,
        "ingest_s": ingest_s,
        "reconcile_s": reconcile_s,
        "total_s": total,
        "rows_per_s": metrics.total_records / total if total else 0,
        "matched": metrics.matched_records,
        "exceptions": metrics.exception_records,
        "unresolved": metrics.unresolved_records,
        "match_rate": metrics.match_rate,
        "mem_ingest_mb": after_ingest - baseline,
        "mem_peak_mb": peak - baseline,
        "batches": result.batches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconciliation scaling benchmark.")
    parser.add_argument("--sizes", type=int, nargs="+",
                        default=[100, 1_000, 10_000, 100_000])
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--work-dir", type=Path, default=Path("data/benchmark"))
    parser.add_argument("--skip-generate", action="store_true",
                        help="reuse existing CSVs in the work directory")
    parser.add_argument("--keep", action="store_true",
                        help="keep generated CSVs instead of deleting them")
    args = parser.parse_args()

    print(f"Reconciliation benchmark  (batch_size={args.batch_size:,})")
    print("=" * 108)
    header = (
        f"{'records':>9} {'ingest':>9} {'reconcile':>10} {'total':>9} "
        f"{'rows/s':>11} {'mem MB':>9} {'matched':>9} {'excep':>7} "
        f"{'unres':>7} {'match %':>8}"
    )
    print(header)
    print("-" * 108)

    rows = []
    try:
        for size in args.sizes:
            r = run_size(size, args.work_dir, batch_size=args.batch_size,
                         skip_generate=args.skip_generate)
            rows.append(r)
            print(
                f"{r['rows']:>9,} {r['ingest_s']:>8.2f}s {r['reconcile_s']:>9.2f}s "
                f"{r['total_s']:>8.2f}s {r['rows_per_s']:>11,.0f} "
                f"{fmt(r['mem_peak_mb']):>9} {r['matched']:>9,} "
                f"{r['exceptions']:>7,} {r['unresolved']:>7,} {r['match_rate']:>7.2f}%"
            )
    finally:
        if not args.keep and args.work_dir.exists():
            shutil.rmtree(args.work_dir, ignore_errors=True)

    # Linearity is the whole point: if throughput holds roughly flat as the
    # input grows by 10x, the joins are behaving as O(n) and not O(n^2).
    if len(rows) > 1:
        print("-" * 108)
        print("\nScaling (throughput should stay roughly flat):")
        first = rows[0]
        for r in rows:
            factor = r["size"] / first["size"]
            time_factor = r["total_s"] / first["total_s"] if first["total_s"] else 0
            print(
                f"  {r['size']:>9,} records: {factor:>7,.0f}x data, "
                f"{time_factor:>6.1f}x time, {r['rows_per_s']:>9,.0f} rows/s"
            )


if __name__ == "__main__":
    main()
