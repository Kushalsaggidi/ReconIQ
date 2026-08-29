"""Job orchestration.

The frontend never waits on a long request.  ``submit`` writes a QUEUED job,
returns immediately, and a worker thread runs the pipeline:

    load -> validate -> normalise -> reconcile -> persist -> AI -> finalise

The executor is a ``ThreadPoolExecutor`` today.  It is deliberately hidden
behind ``JobRunner``: replacing it with Celery, RQ or an SQS consumer means
implementing ``submit`` again and changing nothing else -- not the engine, not
the API, not the frontend contract.

Threads are the right choice here rather than an asyncio task: the reconciliation
loop is CPU- and DB-bound, and running it on the event loop would stall every
/status poll it is supposed to serve.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.ai.analyzer import ExceptionAnalyzer
from app.ai.factory import get_ai_service
from app.core.config import get_settings
from app.core.enums import (
    AiStatus,
    AuditEventType,
    DatasetKind,
    JobStage,
    JobStatus,
)
from app.core.errors import ErrorCode, ReconError
from app.core.logging import get_logger
from app.ingestion.loader import load_dataset
from app.models.base import new_id, utcnow
from app.reconciliation.config import ReconciliationConfig
from app.reconciliation.engine import ReconciliationEngine
from app.schemas.domain import NormalizedDataset
from app.storage import repository as repo
from app.storage.db import session_scope
from app.storage.files import get_file_store

logger = get_logger(__name__)

#: Ordered pipeline stages, with the fraction of the run each one owns. The
#: frontend renders these directly, so the ids and labels are contract.
STAGE_PLAN: tuple[tuple[JobStage, str, str, str], ...] = (
    (JobStage.VALIDATE, "Files validated", "Schema, encoding and column checks", "deterministic"),
    (JobStage.NORMALIZE, "Data normalized", "Currency, date and identifier normalisation", "deterministic"),
    (JobStage.MATCH, "Transactions matched", "Deterministic join on payment ID, settlement ID and UTR", "deterministic"),
    (JobStage.DETECT, "Detecting exceptions", "Variance computed and bucketed by rule", "deterministic"),
    (JobStage.AI, "AI analysis", "Exception classification and explanation", "ai"),
    (JobStage.FINALIZE, "Finalizing report", "Metrics aggregated and audit trail sealed", "deterministic"),
)


def new_job_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d")
    return f"RCN-{stamp}-{new_id('')[1:9].upper()}"


@dataclass
class JobRequest:
    orders_dataset_id: str
    settlements_dataset_id: str
    bank_dataset_id: str | None = None
    source: str = "Manual upload"


class _StageTracker:
    """Builds the stage list the /status endpoint returns."""

    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = {
            stage.value: {
                "id": stage.value,
                "label": label,
                "detail": detail,
                "engine": engine,
                "status": "pending",
                "startedAt": None,
                "finishedAt": None,
            }
            for stage, label, detail, engine in STAGE_PLAN
        }
        self.current: str | None = None

    def start(self, stage: JobStage) -> None:
        self.current = stage.value
        self._state[stage.value]["status"] = "active"
        self._state[stage.value]["startedAt"] = utcnow().isoformat()

    def finish(self, stage: JobStage) -> None:
        self._state[stage.value]["status"] = "done"
        self._state[stage.value]["finishedAt"] = utcnow().isoformat()

    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(v) for v in self._state.values()]

    def label(self) -> str:
        return self._state[self.current]["label"] if self.current else "Queued"


class JobRunner:
    """Submits and executes reconciliation jobs."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="recon"
        )
        self._lock = threading.Lock()
        self._running: set[str] = set()

    # -- public ----------------------------------------------------------

    def submit(self, request: JobRequest) -> str:
        """Create a QUEUED job and hand it to a worker.  Returns immediately."""
        settings = get_settings()
        job_id = new_job_id()
        tracker = _StageTracker()

        with session_scope() as session:
            for attr, kind in (
                ("orders_dataset_id", DatasetKind.ORDERS),
                ("settlements_dataset_id", DatasetKind.SETTLEMENTS),
                ("bank_dataset_id", DatasetKind.BANK),
            ):
                dataset_id = getattr(request, attr)
                if dataset_id and repo.get_dataset(session, dataset_id) is None:
                    raise ReconError(
                        f"No uploaded {kind.value} dataset with id '{dataset_id}'.",
                        code=ErrorCode.DATASET_NOT_FOUND,
                        status_code=404,
                    )

            repo.create_job(
                session,
                job_id,
                status=JobStatus.QUEUED.value,
                source=request.source,
                orders_dataset_id=request.orders_dataset_id,
                settlements_dataset_id=request.settlements_dataset_id,
                bank_dataset_id=request.bank_dataset_id,
                stages=tracker.snapshot(),
                currency=settings.default_currency,
            )
            repo.write_audit(
                session, job_id, AuditEventType.RECONCILIATION_STARTED,
                f"Reconciliation job {job_id} queued.",
                actor="User", engine="system", severity="info",
                metadata={"source": request.source},
            )

        with self._lock:
            self._running.add(job_id)
        self._executor.submit(self._run_guarded, job_id, request)
        return job_id

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # -- worker ----------------------------------------------------------

    def _run_guarded(self, job_id: str, request: JobRequest) -> None:
        try:
            self._run(job_id, request)
        except ReconError as exc:
            self._fail(job_id, exc.code.value, exc.message, exc.to_dict()["error"])
        except Exception as exc:  # never let a worker die silently
            logger.exception("job %s crashed", job_id)
            self._fail(job_id, ErrorCode.RECONCILIATION_FAILED.value, str(exc), None)
        finally:
            with self._lock:
                self._running.discard(job_id)

    def _run(self, job_id: str, request: JobRequest) -> None:
        settings = get_settings()
        store = get_file_store()
        tracker = _StageTracker()
        started = time.perf_counter()

        with session_scope() as session:
            repo.update_job(
                session, job_id,
                status=JobStatus.RUNNING.value,
                started_at=utcnow(),
                stage=JobStage.VALIDATE.value,
                stages=tracker.snapshot(),
            )

        # ---- 1/2. Load, validate, normalise --------------------------
        tracker.start(JobStage.VALIDATE)
        datasets: dict[DatasetKind, NormalizedDataset] = {}
        for kind, dataset_id in (
            (DatasetKind.ORDERS, request.orders_dataset_id),
            (DatasetKind.SETTLEMENTS, request.settlements_dataset_id),
            (DatasetKind.BANK, request.bank_dataset_id),
        ):
            if not dataset_id:
                continue
            with session_scope() as session:
                record = repo.get_dataset(session, dataset_id)
                if record is None:
                    raise ReconError(
                        f"Dataset '{dataset_id}' disappeared.",
                        code=ErrorCode.DATASET_NOT_FOUND, status_code=404,
                    )
                storage_key, original_name = record.storage_key, record.original_name

            dataset = load_dataset(
                store.path_for(storage_key), kind, chunk_size=settings.batch_size
            )
            datasets[kind] = dataset

            with session_scope() as session:
                repo.update_job(session, job_id, stages=tracker.snapshot())
                repo.write_audit(
                    session, job_id, AuditEventType.DATASET_VALIDATED,
                    f"{kind.value.capitalize()} dataset loaded: {dataset.row_count:,} row(s) "
                    f"parsed, {dataset.rejected_count} rejected.",
                    entity_id=dataset_id, actor="Engine",
                    severity="warning" if dataset.rejected_count else "ok",
                    metadata={
                        "file": original_name,
                        "rows": str(dataset.row_count),
                        "rejected": str(dataset.rejected_count),
                        "columns": ", ".join(sorted(dataset.column_mapping)),
                    },
                )
        tracker.finish(JobStage.VALIDATE)

        tracker.start(JobStage.NORMALIZE)
        orders = datasets[DatasetKind.ORDERS].records
        settlements = datasets[DatasetKind.SETTLEMENTS].records
        bank_rows = (
            datasets[DatasetKind.BANK].records if DatasetKind.BANK in datasets else []
        )
        tracker.finish(JobStage.NORMALIZE)

        with session_scope() as session:
            repo.update_job(
                session, job_id,
                records_detected=len(orders),
                stage=JobStage.MATCH.value,
                stages=tracker.snapshot(),
            )
            repo.write_audit(
                session, job_id, AuditEventType.DATASET_NORMALIZED,
                f"{len(orders):,} order(s), {len(settlements):,} settlement(s) and "
                f"{len(bank_rows):,} bank line(s) normalised to "
                f"{settings.default_currency} minor units.",
                actor="Engine",
            )

        # ---- 3/4. Reconcile, streaming results to the database --------
        tracker.start(JobStage.MATCH)
        engine = ReconciliationEngine(
            ReconciliationConfig(
                currency=settings.default_currency,
                rounding_tolerance_minor=settings.rounding_tolerance_minor,
                batch_size=settings.batch_size,
            )
        )

        def persist(batch: list[Any]) -> None:
            with session_scope() as session:
                repo.persist_outcomes(session, job_id, batch)

        def on_progress(processed: int, total: int, matched: int, exceptions: int) -> None:
            with session_scope() as session:
                repo.update_job(
                    session, job_id,
                    records_processed=processed,
                    matched_so_far=matched,
                    exceptions_so_far=exceptions,
                )

        result = engine.run(
            orders, settlements, bank_rows,
            progress=on_progress,
            collect_outcomes=False,   # keeps peak memory flat on large jobs
            on_batch=persist,
        )
        tracker.finish(JobStage.MATCH)

        tracker.start(JobStage.DETECT)
        metrics = result.metrics
        tracker.finish(JobStage.DETECT)

        with session_scope() as session:
            repo.update_job(
                session, job_id,
                stage=JobStage.AI.value,
                stages=tracker.snapshot(),
                records_processed=metrics.total_records,
                matched_so_far=metrics.matched_records,
                exceptions_so_far=metrics.exception_records + metrics.unresolved_records,
                total_records=metrics.total_records,
                matched_records=metrics.matched_records,
                exception_records=metrics.exception_records,
                unresolved_records=metrics.unresolved_records,
                match_rate=metrics.match_rate,
                gross_value=metrics.gross_value,
                settled_value=metrics.settled_value,
                variance_value=metrics.variance_value,
                metrics=metrics.to_dict(),
            )
            repo.write_audit(
                session, job_id, AuditEventType.RECORD_MATCHED,
                f"{metrics.matched_records:,} record(s) reconciled "
                f"({metrics.match_rate}% match rate).",
                actor="Engine",
                metadata={"matchRate": f"{metrics.match_rate}%"},
            )
            exceptions_total = metrics.exception_records + metrics.unresolved_records
            if exceptions_total:
                repo.write_audit(
                    session, job_id, AuditEventType.EXCEPTION_DETECTED,
                    f"{exceptions_total:,} exception(s) detected; variance computed "
                    "per record and bucketed by rule.",
                    actor="Engine", severity="warning",
                    metadata={k: str(v) for k, v in metrics.breakdown().items()},
                )

        # ---- 5. Advisory AI pass. Cannot fail the job. ----------------
        tracker.start(JobStage.AI)
        ai_summary: dict[str, Any] = {"status": AiStatus.SKIPPED.value, "analysed": 0}
        try:
            analyzer = ExceptionAnalyzer(get_ai_service(), settings)
            with session_scope() as session:
                ai_summary = analyzer.analyse_job(session, job_id)
        except Exception as exc:
            # analyse_job already swallows provider errors; this is the last
            # line of defence against a bug in the analyser itself.
            logger.exception("AI stage failed for job %s", job_id)
            ai_summary = {"status": AiStatus.FAILED.value, "analysed": 0, "error": str(exc)}
            with session_scope() as session:
                repo.write_audit(
                    session, job_id, AuditEventType.AI_ANALYSIS_FAILED,
                    "AI analysis could not run. Deterministic reconciliation results "
                    "are complete and unaffected.",
                    actor="AI Analyst", engine="ai", severity="warning",
                )
        tracker.finish(JobStage.AI)

        # ---- 6. Finalise ----------------------------------------------
        tracker.start(JobStage.FINALIZE)
        duration_ms = int((time.perf_counter() - started) * 1000)
        with session_scope() as session:
            if metrics.unresolved_records:
                repo.write_audit(
                    session, job_id, AuditEventType.HUMAN_REVIEW_REQUIRED,
                    f"{metrics.unresolved_records:,} record(s) flagged for human review. "
                    "No supporting record explains the variance and no value was inferred.",
                    actor="Engine", severity="warning",
                )
            tracker.finish(JobStage.FINALIZE)
            repo.update_job(
                session, job_id,
                status=JobStatus.COMPLETED.value,
                stage=JobStage.FINALIZE.value,
                stages=tracker.snapshot(),
                completed_at=utcnow(),
                duration_ms=duration_ms,
                ai_status=str(ai_summary.get("status", AiStatus.SKIPPED.value)),
                ai_analysed_count=int(ai_summary.get("analysed", 0) or 0),
                ai_error=str(ai_summary.get("error")) if ai_summary.get("error") else None,
                validation_report={
                    kind.value: {
                        "rows": ds.row_count,
                        "rejected": ds.rejected_count,
                        "checksum": ds.checksum,
                        "sourceName": ds.source_name,
                        "columnMapping": ds.column_mapping,
                        "issues": ds.issues,
                    }
                    for kind, ds in datasets.items()
                },
            )
            repo.write_audit(
                session, job_id, AuditEventType.RECONCILIATION_COMPLETED,
                f"Reconciliation completed in {duration_ms:,} ms. "
                f"{metrics.total_records:,} record(s) processed.",
                actor="System", engine="system",
                metadata={
                    "durationMs": str(duration_ms),
                    "matchRate": f"{metrics.match_rate}%",
                },
            )

    def _fail(
        self, job_id: str, code: str, message: str, detail: dict[str, Any] | None
    ) -> None:
        logger.error("job %s failed: %s", job_id, message)
        with session_scope() as session:
            repo.update_job(
                session, job_id,
                status=JobStatus.FAILED.value,
                completed_at=utcnow(),
                error_code=code,
                error_message=message,
                validation_report=detail,
            )
            repo.write_audit(
                session, job_id, AuditEventType.RECONCILIATION_FAILED,
                message, actor="System", engine="system", severity="warning",
                metadata={"code": code},
            )


_runner: JobRunner | None = None


def get_job_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner


def shutdown_job_runner() -> None:
    global _runner
    if _runner is not None:
        _runner.shutdown()
        _runner = None
