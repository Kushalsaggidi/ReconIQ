"""The Copilot's entire universe: eight read-only, job-scoped tools.

Every handler takes ``(session, job_id, args)`` and returns a plain JSON-able
dict -- never an ORM row, never a raw SQL result. Each one reads through
:mod:`app.storage.repository` or :mod:`app.services.results_service`, the same
modules the REST API uses, so there is exactly one place that knows how to
read a job's data, not two.

Nothing here accepts a job id from the model: ``job_id`` is threaded in by the
caller (:mod:`app.copilot.service`) from the URL path, so a tool call can never
reach across reconciliation runs. Amounts are converted to major units (rupees,
not paise) for readability, mirroring :func:`app.ai.analyzer.build_facts`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.money import to_major
from app.services import results_service as rs
from app.storage import repository as repo

logger = get_logger(__name__)

ToolHandler = Callable[[Session, str, dict[str, Any]], dict[str, Any]]


def _clamp_int(value: Any, *, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _money(minor: int, currency: str) -> float:
    return float(to_major(minor, currency))


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _get_reconciliation_summary(session: Session, job_id: str, args: dict[str, Any]) -> dict[str, Any]:
    job = repo.get_job(session, job_id)
    if job is None:
        return {"error": "No reconciliation job with this id."}
    summary = rs.build_summary(session, job)
    cur = summary.currency
    return {
        "jobId": summary.jobId,
        "status": summary.status.value,
        "recordsProcessed": summary.recordsProcessed,
        "matched": summary.matched,
        "exceptions": summary.exceptions,
        "unresolved": summary.unresolved,
        "matchRatePercent": summary.matchRate,
        "currency": cur,
        "grossValue": _money(summary.grossValue, cur),
        "settledValue": _money(summary.settledValue, cur),
        "varianceValue": _money(summary.varianceValue, cur),
        "buckets": [
            {
                "type": b.type.value,
                "label": b.label,
                "count": b.count,
                "amount": _money(b.amount, cur),
                "autoExplainedByEngine": b.autoExplained,
            }
            for b in summary.buckets
        ],
        "aiStatus": summary.aiStatus.value,
        "aiAnalysedCount": summary.aiAnalysedCount,
        "completedAt": summary.completedAt.isoformat() if summary.completedAt else None,
    }


def _get_exception_categories(session: Session, job_id: str, args: dict[str, Any]) -> dict[str, Any]:
    job = repo.get_job(session, job_id)
    if job is None:
        return {"error": "No reconciliation job with this id."}
    summary = rs.build_summary(session, job)
    return {
        "totalExceptions": summary.exceptions,
        "totalUnresolved": summary.unresolved,
        "currency": summary.currency,
        "categories": [
            {
                "type": b.type.value,
                "label": b.label,
                "count": b.count,
                "amount": _money(b.amount, summary.currency),
                "autoExplainedByEngine": b.autoExplained,
            }
            for b in summary.buckets
        ],
    }


def _list_exceptions(session: Session, job_id: str, args: dict[str, Any]) -> dict[str, Any]:
    job = repo.get_job(session, job_id)
    if job is None:
        return {"error": "No reconciliation job with this id."}
    limit = _clamp_int(args.get("limit"), default=10, lo=1, hi=25)
    status = (args.get("status") or "").strip() or None
    exception_type = (args.get("exceptionType") or "").strip() or None
    payload = repo.query_transactions(
        session,
        job_id,
        page=1,
        page_size=limit,
        status=status,
        exception_type=exception_type,
        exceptions_only=True,
        sort_by="difference",
        sort_dir="desc",
    )
    cur = job.currency
    rows = [
        {
            "orderId": r.order_id,
            "paymentId": r.payment_id,
            "status": r.status,
            "exceptionType": r.exception_type,
            "unexplained": _money(r.unexplained, cur),
            "reason": r.reason,
        }
        for r in payload["rows"]
    ]
    return {"totalMatchingFilter": payload["total"], "returned": len(rows), "exceptions": rows}


def _get_exception(session: Session, job_id: str, args: dict[str, Any]) -> dict[str, Any]:
    order_id = str(args.get("orderId") or "").strip()
    if not order_id:
        return {"error": "orderId is required."}
    job = repo.get_job(session, job_id)
    if job is None:
        return {"error": "No reconciliation job with this id."}
    try:
        detail = rs.build_exception_detail(session, job_id, order_id)
    except NotFoundError:
        return {
            "found": False,
            "orderId": order_id,
            "message": f"No exception record for order '{order_id}' in this reconciliation.",
        }
    cur = detail.transaction.currency
    return {
        "found": True,
        "exceptionId": detail.exceptionId,
        "orderId": detail.transaction.orderId,
        "paymentId": detail.transaction.paymentId,
        "settlementId": detail.transaction.settlementId,
        "status": detail.transaction.status.value,
        "exceptionType": detail.transaction.exceptionType.value if detail.transaction.exceptionType else None,
        "currency": cur,
        "expected": _money(detail.computed.expected, cur),
        "settled": _money(detail.computed.settled, cur),
        "difference": _money(detail.computed.difference, cur),
        "fee": _money(detail.computed.fee, cur),
        "tax": _money(detail.computed.tax, cur),
        "refund": _money(detail.computed.refund, cur),
        "accountedFor": _money(detail.computed.accountedFor, cur),
        "unexplained": _money(detail.computed.unexplained, cur),
        "deterministicReason": detail.transaction.reason,
        "checks": [{"label": c.label, "passed": c.passed, "detail": c.detail} for c in detail.computed.checks],
        "requiresHumanReview": detail.ai.requiresHumanReview,
        "aiAnalysis": {
            "status": detail.ai.status.value,
            "classification": detail.ai.classification,
            "confidence": detail.ai.confidence.value if detail.ai.confidence else None,
            "explanation": detail.ai.explanation,
            "signals": detail.ai.signals,
            "recommendedAction": detail.ai.recommendedAction,
        },
        "evidence": [
            {
                "source": e.source,
                "present": e.present,
                "fields": [{"label": f.label, "value": f.value} for f in e.fields],
            }
            for e in detail.evidence
        ],
    }


def _get_largest_variances(session: Session, job_id: str, args: dict[str, Any]) -> dict[str, Any]:
    job = repo.get_job(session, job_id)
    if job is None:
        return {"error": "No reconciliation job with this id."}
    limit = _clamp_int(args.get("limit"), default=5, lo=1, hi=20)
    rows = repo.get_largest_variances(session, job_id, limit)
    cur = job.currency
    return {
        "returned": len(rows),
        "variances": [
            {
                "orderId": r.order_id,
                "paymentId": r.payment_id,
                "status": r.status,
                "exceptionType": r.exception_type,
                "unexplained": _money(r.unexplained, cur),
                "reason": r.reason,
            }
            for r in rows
        ],
    }


def _get_human_review_items(session: Session, job_id: str, args: dict[str, Any]) -> dict[str, Any]:
    job = repo.get_job(session, job_id)
    if job is None:
        return {"error": "No reconciliation job with this id."}
    limit = _clamp_int(args.get("limit"), default=10, lo=1, hi=25)
    rows = repo.get_human_review_exceptions(session, job_id, limit)
    cur = job.currency
    return {
        "returned": len(rows),
        "items": [
            {
                "exceptionId": r.id,
                "orderId": r.order_id,
                "exceptionType": r.exception_type,
                "unexplained": _money(r.unexplained, cur),
                "aiStatus": r.ai_status,
                "aiClassification": r.ai_classification,
                "reason": r.reason,
            }
            for r in rows
        ],
    }


def _get_audit_events(session: Session, job_id: str, args: dict[str, Any]) -> dict[str, Any]:
    job = repo.get_job(session, job_id)
    if job is None:
        return {"error": "No reconciliation job with this id."}
    limit = _clamp_int(args.get("limit"), default=10, lo=1, hi=25)
    event_type = (args.get("eventType") or "").strip() or None
    payload = repo.query_audit(session, job_id, page=1, page_size=limit, event_type=event_type)
    return {
        "totalMatchingFilter": payload["total"],
        "events": [
            {
                "id": str(e.id),
                "at": e.created_at.isoformat(),
                "type": e.event_type,
                "message": e.message,
                "actor": e.actor,
                "severity": e.severity,
                "entityId": e.entity_id,
            }
            for e in payload["rows"]
        ],
    }


def _get_transaction(session: Session, job_id: str, args: dict[str, Any]) -> dict[str, Any]:
    order_id = str(args.get("orderId") or "").strip()
    if not order_id:
        return {"error": "orderId is required."}
    job = repo.get_job(session, job_id)
    if job is None:
        return {"error": "No reconciliation job with this id."}
    txn = repo.get_transaction(session, job_id, order_id)
    if txn is None:
        return {
            "found": False,
            "orderId": order_id,
            "message": f"No transaction record for order '{order_id}' in this reconciliation.",
        }
    cur = txn.currency
    return {
        "found": True,
        "orderId": txn.order_id,
        "paymentId": txn.payment_id,
        "settlementId": txn.settlement_id,
        "bankReference": txn.bank_reference,
        "status": txn.status,
        "exceptionType": txn.exception_type,
        "currency": cur,
        "expected": _money(txn.expected_amount, cur),
        "settled": _money(txn.settled_amount, cur),
        "difference": _money(txn.difference, cur),
        "unexplained": _money(txn.unexplained, cur),
        "reason": txn.reason,
        "method": txn.method,
        "settlementDate": txn.settlement_date.isoformat() if txn.settlement_date else None,
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def declaration(self) -> dict[str, Any]:
        """Gemini ``functionDeclarations`` shape."""
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_reconciliation_summary",
        description=(
            "Returns the verified, engine-computed summary for the active reconciliation job: "
            "status, records processed, matched/exception/unresolved counts, match rate, gross/"
            "settled/variance value, exception-type buckets and AI-analysis status. Use this for "
            "any question about overall totals, match rate, or 'how many exceptions'."
        ),
        parameters={"type": "OBJECT", "properties": {}},
        handler=_get_reconciliation_summary,
    ),
    ToolSpec(
        name="get_exception_categories",
        description=(
            "Returns verified counts and amounts of exceptions grouped by category (partial "
            "payment, refund, fee/tax, rounding, unresolved) for the active job. Use this when "
            "the user asks why a batch has exceptions or wants a category breakdown."
        ),
        parameters={"type": "OBJECT", "properties": {}},
        handler=_get_exception_categories,
    ),
    ToolSpec(
        name="list_exceptions",
        description=(
            "Lists individual exceptions for the active job, optionally filtered by status "
            "('exception' or 'unresolved') or exceptionType (partial_payment | refund | fee_tax | "
            "rounding | unresolved). Returns at most `limit` rows (default 10, max 25), largest "
            "difference first. Use this to show a list of exceptions."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "status": {"type": "STRING", "description": "'exception' or 'unresolved'."},
                "exceptionType": {
                    "type": "STRING",
                    "description": "partial_payment | refund | fee_tax | rounding | unresolved",
                },
                "limit": {"type": "INTEGER", "description": "Max rows to return (default 10, max 25)."},
            },
        },
        handler=_list_exceptions,
    ),
    ToolSpec(
        name="get_exception",
        description=(
            "Returns the full verified detail for one exception by order id: expected/settled/"
            "fee/tax/refund/accounted-for/unexplained amounts, the deterministic checks, evidence "
            "records, and the advisory AI classification/explanation if one exists. Use this "
            "whenever the user asks about a specific order or payment, or why it is unresolved."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {"orderId": {"type": "STRING", "description": "The order id, e.g. 'ORD-1042'."}},
            "required": ["orderId"],
        },
        handler=_get_exception,
    ),
    ToolSpec(
        name="get_largest_variances",
        description=(
            "Returns the exceptions/unresolved records with the largest unexplained amount for "
            "the active job, largest first. Use this when the user asks for the biggest or "
            "largest variances."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {"limit": {"type": "INTEGER", "description": "Max rows (default 5, max 20)."}},
        },
        handler=_get_largest_variances,
    ),
    ToolSpec(
        name="get_human_review_items",
        description=(
            "Returns exceptions flagged as requiring human review for the active job, largest "
            "unexplained amount first. Use this when the user asks what needs human review or "
            "what to investigate first."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {"limit": {"type": "INTEGER", "description": "Max rows (default 10, max 25)."}},
        },
        handler=_get_human_review_items,
    ),
    ToolSpec(
        name="get_audit_events",
        description=(
            "Returns the append-only audit trail for the active job -- what the deterministic "
            "engine and the AI analyser did, and when. Optionally filter by eventType (e.g. "
            "'AI_ANALYSIS_COMPLETED', 'EXCEPTION_DETECTED'). Use this when the user asks what the "
            "audit trail recorded, or what happened during the run."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "eventType": {"type": "STRING", "description": "Exact audit event type to filter by."},
                "limit": {"type": "INTEGER", "description": "Max rows (default 10, max 25)."},
            },
        },
        handler=_get_audit_events,
    ),
    ToolSpec(
        name="get_transaction",
        description=(
            "Returns the verified reconciled transaction record for one order id, including "
            "match status, settlement id, bank reference and amounts. Use this for a plain lookup "
            "of a specific order/payment that is not necessarily an exception."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {"orderId": {"type": "STRING", "description": "The order id, e.g. 'ORD-1042'."}},
            "required": ["orderId"],
        },
        handler=_get_transaction,
    ),
)

TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}


@dataclass(slots=True)
class ToolCallResult:
    name: str
    args: dict[str, Any]
    ok: bool
    data: dict[str, Any]


def run_tool(session: Session, job_id: str, name: str, args: dict[str, Any] | None) -> ToolCallResult:
    """Execute one tool call.

    Never raises: an unknown tool name or a handler exception becomes a
    structured ``{"error": ...}`` payload the model can see and react to,
    rather than a failed request. This is what makes a hallucinated tool name
    or a transient DB hiccup a recoverable conversational turn instead of a
    500.
    """
    safe_args = dict(args or {})
    spec = TOOLS_BY_NAME.get(name)
    if spec is None:
        return ToolCallResult(name=name, args=safe_args, ok=False, data={"error": f"Unknown tool '{name}'."})
    try:
        data = spec.handler(session, job_id, safe_args)
    except Exception as exc:  # a tool must never crash the conversation
        logger.exception("copilot tool '%s' failed for job %s", name, job_id)
        return ToolCallResult(name=name, args=safe_args, ok=False, data={"error": f"Tool failed: {exc}"})
    return ToolCallResult(name=name, args=safe_args, ok="error" not in data, data=data)


__all__ = ["TOOLS", "TOOLS_BY_NAME", "ToolSpec", "ToolCallResult", "run_tool"]
