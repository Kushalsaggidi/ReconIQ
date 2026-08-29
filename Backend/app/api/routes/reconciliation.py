"""Reconciliation REST API.

Thin by design: parse, delegate, serialise.  No business logic, no SQL.

Pagination is mandatory on every collection endpoint and capped server-side, so
there is no request that can return a million rows.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import AuditEventType, DatasetKind, JobStatus
from app.core.errors import ErrorCode, IngestionError, ReconError
from app.core.logging import get_logger
from app.ingestion.loader import load_dataset
from app.ingestion.readers import validate_upload
from app.schemas.api import (
    AuditPage,
    DatasetFileResponse,
    ExceptionDetailResponse,
    HistoryEntryResponse,
    JobProgressResponse,
    ReconciliationSummaryResponse,
    RunRequest,
    RunResponse,
    TransactionPage,
    TrendPointResponse,
)
from app.services import results_service as rs
from app.services.job_service import JobRequest, get_job_runner
from app.storage import repository as repo
from app.storage.db import get_db, session_scope
from app.storage.files import get_file_store

logger = get_logger(__name__)
router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=DatasetFileResponse, status_code=201)
async def upload_dataset(
    kind: Annotated[DatasetKind, Form(description="orders | settlements | bank")],
    file: Annotated[UploadFile, File(...)],
) -> DatasetFileResponse:
    """Accept one CSV, validate and normalise it, and register it for a run.

    The file is streamed to the file store and only its key is persisted.  Its
    contents are parsed as data and never executed or evaluated.
    """
    settings = get_settings()
    store = get_file_store()
    filename = file.filename or "upload.csv"

    key, size = store.save(file.file, filename, prefix=f"{kind.value}/")
    try:
        validate_upload(filename, size, settings.allowed_suffix_set, settings.max_upload_bytes)
        # Parsing at upload time means the operator learns about a bad column
        # or a malformed amount now, not five minutes into a run.
        dataset = load_dataset(
            store.path_for(key), kind, chunk_size=settings.batch_size
        )
    except ReconError:
        # A rejected upload leaves nothing behind.
        store.delete(key)
        raise
    except Exception as exc:
        store.delete(key)
        raise IngestionError(
            f"Could not read {filename}: {exc}", code=ErrorCode.UNREADABLE_FILE
        ) from exc

    with session_scope() as session:
        record = repo.create_dataset(
            session,
            kind=kind.value,
            original_name=filename,
            storage_key=key,
            size_bytes=size,
            row_count=dataset.row_count,
            rejected_count=dataset.rejected_count,
            checksum=dataset.checksum,
            column_mapping=dataset.column_mapping,
            validation_report=dataset.issues,
            status="ready",
        )
        dataset_id = record.id
        created_at = record.created_at
        repo.write_audit(
            session, None, AuditEventType.DATASET_UPLOADED,
            f"{kind.value.capitalize()} dataset '{filename}' uploaded: "
            f"{dataset.row_count:,} row(s) accepted, {dataset.rejected_count} rejected.",
            entity_id=dataset_id, actor="User", engine="system",
            severity="warning" if dataset.rejected_count else "ok",
            metadata={"checksum": dataset.checksum or "", "sizeBytes": str(size)},
        )

    return DatasetFileResponse(
        datasetId=dataset_id,
        kind=kind,
        name=filename,
        size=size,
        rows=dataset.row_count,
        rejected=dataset.rejected_count,
        status="ready",
        progress=100,
        uploadedAt=created_at,
        checksum=dataset.checksum,
        columnMapping=dataset.column_mapping,
        unmappedColumns=dataset.unmapped_headers,
        issues=dataset.issues,
        format=dataset.format,
        detectedKind=DatasetKind(dataset.detected_kind) if dataset.detected_kind else None,
        detectionConfidence=dataset.detected_confidence,
        warnings=dataset.warnings,
        ready=True,
    )


@router.get("/datasets", response_model=list[DatasetFileResponse])
def list_datasets(session: DbSession, limit: int = Query(50, ge=1, le=200)):
    return [
        DatasetFileResponse(
            datasetId=d.id,
            kind=DatasetKind(d.kind),
            name=d.original_name,
            size=d.size_bytes,
            rows=d.row_count,
            rejected=d.rejected_count,
            status=d.status,
            uploadedAt=d.created_at,
            checksum=d.checksum,
            columnMapping=d.column_mapping or {},
            issues=d.validation_report,
        )
        for d in repo.list_datasets(session, limit)
    ]


# ---------------------------------------------------------------------------
# Run + poll
# ---------------------------------------------------------------------------

@router.post("/run", response_model=RunResponse, status_code=202)
def run_reconciliation(payload: RunRequest) -> RunResponse:
    """Queue a job and return immediately.

    202 + a job id, never a long synchronous response -- which is what lets the
    processing implementation change later without touching the frontend.
    """
    job_id = get_job_runner().submit(
        JobRequest(
            orders_dataset_id=payload.ordersDatasetId,
            settlements_dataset_id=payload.settlementsDatasetId,
            bank_dataset_id=payload.bankDatasetId,
            source=payload.source,
        )
    )
    with session_scope() as session:
        job = repo.get_job(session, job_id)
        detected = job.records_detected if job else 0
    return RunResponse(jobId=job_id, status=JobStatus.QUEUED, recordsDetected=detected)


@router.get("/jobs", response_model=list[HistoryEntryResponse])
def list_jobs(session: DbSession, limit: int = Query(25, ge=1, le=100)):
    return rs.build_history(repo.list_jobs(session, limit))


@router.get("/{job_id}/status", response_model=JobProgressResponse)
def job_status(job_id: str, session: DbSession) -> JobProgressResponse:
    return rs.build_progress(rs.require_job(session, job_id))


@router.get("/{job_id}/results", response_model=ReconciliationSummaryResponse)
def job_results(job_id: str, session: DbSession) -> ReconciliationSummaryResponse:
    return rs.build_summary(session, rs.require_job(session, job_id))


@router.get("/{job_id}/trend", response_model=list[TrendPointResponse])
def job_trend(job_id: str, session: DbSession):
    return rs.build_trend(rs.require_job(session, job_id))


# ---------------------------------------------------------------------------
# Result sets
# ---------------------------------------------------------------------------

def _page_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=repo.MAX_PAGE_SIZE, alias="page_size"),
    status: str | None = Query(None, description="matched | exception | unresolved | all"),
    exception_type: str | None = Query(
        None, description="partial_payment | refund | fee_tax | rounding | unresolved | all"
    ),
    search: str | None = Query(None, description="Order, payment, settlement ID or UTR"),
    sort_by: str = Query("orderId"),
    sort_dir: Literal["asc", "desc"] = Query("asc"),
) -> dict[str, object]:
    return {
        "page": page,
        "page_size": page_size,
        "status": status,
        "exception_type": exception_type,
        "search": search,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }


PageParams = Annotated[dict, Depends(_page_params)]


@router.get("/{job_id}/transactions", response_model=TransactionPage)
def job_transactions(job_id: str, session: DbSession, params: PageParams) -> TransactionPage:
    rs.require_job(session, job_id)
    return rs.build_transaction_page(
        repo.query_transactions(session, job_id, exceptions_only=False, **params)
    )


@router.get("/{job_id}/exceptions", response_model=TransactionPage)
def job_exceptions(job_id: str, session: DbSession, params: PageParams) -> TransactionPage:
    rs.require_job(session, job_id)
    return rs.build_transaction_page(
        repo.query_transactions(session, job_id, exceptions_only=True, **params)
    )


@router.get("/{job_id}/exceptions/{order_id}", response_model=ExceptionDetailResponse)
def exception_detail(job_id: str, order_id: str, session: DbSession) -> ExceptionDetailResponse:
    rs.require_job(session, job_id)
    return rs.build_exception_detail(session, job_id, order_id)


@router.get("/{job_id}/audit", response_model=AuditPage)
def job_audit(
    job_id: str,
    session: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=repo.MAX_PAGE_SIZE),
) -> AuditPage:
    rs.require_job(session, job_id)
    return rs.build_audit_page(
        repo.query_audit(session, job_id, page=page, page_size=page_size)
    )


@router.get("/{job_id}/export")
def job_export(
    job_id: str,
    session: DbSession,
    exceptions_only: bool = Query(False),
    limit: int = Query(5_000, ge=1, le=100_000),
) -> Response:
    """CSV export, hard-capped.  Built page-by-page, never in one query."""
    rs.require_job(session, job_id)
    body = rs.export_rows(session, job_id, exceptions_only=exceptions_only, limit=limit)
    suffix = "exceptions" if exceptions_only else "transactions"
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{job_id}_{suffix}.csv"'
        },
    )


