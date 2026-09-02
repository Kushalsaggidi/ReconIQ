"""Copilot orchestration.

    USER QUESTION -> UNDERSTAND INTENT -> SELECT TOOL(S) -> BACKEND EXECUTES
    TOOL -> VERIFIED DATA RETURNED -> MODEL EXPLAINS -> VALIDATE -> RETURN

Every step after "verified data returned" can fail without taking down the
request: a bad tool call becomes a ``{"error": ...}`` payload the model can
see (:func:`app.copilot.tools.run_tool`), a broken provider becomes a safe
fallback message (:class:`app.core.errors.LLMUnavailable`), and an ungrounded
or write-claiming answer is rejected before it ever reaches the user
(:func:`app.copilot.grounding.validate_answer`). Nothing in this module can
alter a reconciliation figure -- there is no write path here at all, only
``repo.write_audit`` for the Copilot's own interaction log.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.copilot import grounding
from app.copilot.factory import get_copilot_provider
from app.copilot.prompts import build_system_prompt
from app.copilot.provider_base import ChatMessage, CopilotProvider
from app.copilot.tools import TOOLS, ToolCallResult, run_tool
from app.core.enums import AuditEventType
from app.core.errors import LLMUnavailable
from app.core.logging import get_logger
from app.schemas.api import CopilotRequest, CopilotResponse, CopilotSource, CopilotToolCallSummary
from app.services import results_service as rs
from app.storage import repository as repo

logger = get_logger(__name__)

#: Older turns beyond this are dropped -- bounds prompt size and cost. The
#: active job's own data is fetched fresh via tools on every turn regardless,
#: so trimming history never loses access to a figure, only to small talk.
MAX_HISTORY_MESSAGES = 12

SAFE_FALLBACK = (
    "I wasn't able to produce a sufficiently grounded answer from the available reconciliation "
    "data. Please inspect the exception details directly."
)
PROVIDER_DOWN_FALLBACK = (
    "The Copilot's AI layer is temporarily unavailable. The reconciliation results themselves are "
    "unaffected -- please use the Results, Exceptions and Audit pages directly, or try again shortly."
)

_TOOL_LABELS: dict[str, str] = {
    "get_reconciliation_summary": "Reconciliation Summary",
    "get_exception_categories": "Exception Categories",
    "list_exceptions": "Exception List",
    "get_exception": "Exception Detail",
    "get_largest_variances": "Largest Variances",
    "get_human_review_items": "Human Review Queue",
    "get_audit_events": "Audit Trail",
    "get_transaction": "Transaction Detail",
}


def _source_label(call: ToolCallResult) -> str:
    base = _TOOL_LABELS.get(call.name, call.name)
    order_id = call.data.get("orderId") if call.ok else call.args.get("orderId")
    if order_id and call.name in ("get_exception", "get_transaction"):
        return f"{base} — {order_id}"
    return base


@dataclass(slots=True)
class CopilotService:
    provider: CopilotProvider

    def ask(self, session: Session, job_id: str, payload: CopilotRequest) -> CopilotResponse:
        rs.require_job(session, job_id)  # raises NotFoundError -> 404 if the job id is wrong

        history = [
            ChatMessage(role=m.role, content=m.content)
            for m in payload.history[-MAX_HISTORY_MESSAGES:]
        ]
        system_prompt = build_system_prompt(job_id)

        def _tool_runner(name: str, args: dict) -> ToolCallResult:
            return run_tool(session, job_id, name, args)

        try:
            turn = self.provider.converse(
                system_prompt=system_prompt,
                history=history,
                message=payload.message,
                tools=list(TOOLS),
                tool_runner=_tool_runner,
            )
        except LLMUnavailable as exc:
            logger.warning("copilot provider unavailable for job %s: %s", job_id, exc)
            return self._unavailable(session, job_id, str(exc))
        except Exception:
            logger.exception("unexpected copilot failure for job %s", job_id)
            return self._unavailable(session, job_id, "unexpected provider error")

        tool_results = [c.data for c in turn.tool_calls if c.ok]
        validation = grounding.validate_answer(
            turn.answer, tool_results=tool_results, user_message=payload.message
        )

        if not validation.ok:
            logger.warning("copilot answer failed grounding for job %s: %s", job_id, validation.reason)
            self._safe_audit(
                session, job_id, AuditEventType.COPILOT_VALIDATION_FAILED,
                f"Copilot answer withheld: {validation.reason}",
                actor="AI Analyst", engine="ai", severity="warning",
                metadata={"model": self.provider.model},
            )
            return CopilotResponse(
                answer=SAFE_FALLBACK,
                status="validation_failed",
                validated=False,
                model=self.provider.model,
                toolCalls=[CopilotToolCallSummary(tool=c.name, ok=c.ok) for c in turn.tool_calls],
            )

        self._safe_audit(
            session, job_id, AuditEventType.COPILOT_QUERY,
            f"Copilot answered a question using {len(turn.tool_calls)} tool call(s).",
            actor="AI Analyst", engine="ai", severity="ok",
            metadata={
                "model": self.provider.model,
                "tools": ",".join(c.name for c in turn.tool_calls) or "none",
                "tokens": str(turn.tokens),
            },
        )

        return CopilotResponse(
            answer=turn.answer,
            status="ok",
            validated=True,
            model=self.provider.model,
            sources=[CopilotSource(label=_source_label(c), tool=c.name) for c in turn.tool_calls if c.ok],
            toolCalls=[CopilotToolCallSummary(tool=c.name, ok=c.ok) for c in turn.tool_calls],
        )

    def _unavailable(self, session: Session, job_id: str, detail: str) -> CopilotResponse:
        self._safe_audit(
            session, job_id, AuditEventType.COPILOT_ERROR,
            f"Copilot could not produce an answer: {detail}",
            actor="AI Analyst", engine="ai", severity="warning",
        )
        return CopilotResponse(
            answer=PROVIDER_DOWN_FALLBACK,
            status="provider_unavailable",
            validated=False,
            model=self.provider.model,
        )

    @staticmethod
    def _safe_audit(session: Session, job_id: str, event_type: AuditEventType, message: str, **kwargs: object) -> None:
        """Best-effort audit logging.

        ``app/storage/db.py``'s ``busy_timeout`` PRAGMA is the primary defence
        against writer contention with the job pipeline's background AI
        analysis; this is the fallback for whatever gets past it. A failure
        writing the Copilot's *own* audit trail must never turn a good,
        already-validated answer into a 500 -- so it is caught, logged, and
        the session rolled back to a usable state, rather than re-raised.
        """
        try:
            repo.write_audit(session, job_id, event_type, message, **kwargs)  # type: ignore[arg-type]
            session.flush()
        except Exception as exc:
            logger.warning("copilot audit write failed for job %s (non-fatal): %s", job_id, exc)
            session.rollback()


_cached_service: CopilotService | None = None


def get_copilot_service() -> CopilotService:
    """Rebuilds the service if the underlying provider singleton was swapped
    (see ``app.copilot.factory.set_copilot_provider``, used by tests)."""
    global _cached_service
    provider = get_copilot_provider()
    if _cached_service is None or _cached_service.provider is not provider:
        _cached_service = CopilotService(provider=provider)
    return _cached_service


def reset_copilot_service() -> None:
    """Test hook -- forces the next call to re-read the provider singleton."""
    global _cached_service
    _cached_service = None


__all__ = [
    "CopilotService",
    "get_copilot_service",
    "reset_copilot_service",
    "SAFE_FALLBACK",
    "PROVIDER_DOWN_FALLBACK",
]
