"""Exception analysis orchestration.

The contract this module exists to enforce:

    **A failure in the AI layer never fails a reconciliation job.**

Every call is wrapped.  A timeout, a malformed response, a missing API key, a
verdict citing an invented figure -- all of them mark the affected exceptions
``ai_status = failed`` (or ``skipped``) and leave every deterministic figure
exactly as the engine computed it.

Volume control is structural, not advisory: only ``ExceptionRecord`` rows are
ever considered, only the ``ai_max_exceptions_per_job`` largest by unexplained
value are selected, and they are sent in small batches.  There is no code path
that sends a whole dataset to a model.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session

from app.ai.base import AIService
from app.ai.schemas import AiVerdict, ExceptionFacts
from app.core.config import Settings, get_settings
from app.core.enums import AiStatus, AuditEventType, ExceptionType
from app.core.errors import LLMUnavailable
from app.core.logging import get_logger
from app.core.money import to_major
from app.models.base import utcnow
from app.models.entities import ExceptionRecord
from app.storage import repository as repo

logger = get_logger(__name__)


def build_facts(record: ExceptionRecord) -> ExceptionFacts:
    """Project a stored exception into the payload the model may see.

    Amounts are converted to major units for readability, but they are *copies*
    of figures the engine already finalised -- this function performs no
    reconciliation arithmetic of its own.
    """
    cur = record.currency or "INR"
    evidence_present = {
        item.get("source", f"source_{i}"): bool(item.get("present"))
        for i, item in enumerate(record.evidence or [])
    }
    return ExceptionFacts(
        exception_id=record.id,
        order_id=record.order_id,
        payment_id=record.payment_id,
        settlement_id=record.settlement_id,
        currency=cur,
        expected_amount=float(to_major(record.expected_amount, cur)),
        actual_amount=float(to_major(record.actual_amount, cur)),
        difference=float(to_major(record.difference, cur)),
        fee=float(to_major(record.fee, cur)),
        tax=float(to_major(record.tax, cur)),
        refund=float(to_major(record.refund, cur)),
        adjustment=float(to_major(record.adjustment, cur)),
        accounted_for=float(to_major(record.accounted_for, cur)),
        unexplained=float(to_major(record.unexplained, cur)),
        deterministic_type=record.exception_type,
        deterministic_cause=record.cause,
        deterministic_reason=record.reason,
        checks=list(record.checks or []),
        evidence_present=evidence_present,
    )


class ExceptionAnalyzer:
    """Runs the advisory pass over a job's exceptions."""

    def __init__(self, service: AIService, settings: Settings | None = None) -> None:
        self.service = service
        self.settings = settings or get_settings()

    def analyse_job(self, session: Session, job_id: str) -> dict[str, object]:
        """Analyse a job's exceptions.  Returns a summary; never raises."""
        settings = self.settings
        if not settings.ai_enabled:
            self._mark_all(session, job_id, AiStatus.SKIPPED, "AI analysis disabled by config.")
            repo.write_audit(
                session, job_id, AuditEventType.AI_ANALYSIS_SKIPPED,
                "AI analysis skipped: disabled by configuration.",
                actor="System", engine="ai", severity="info",
            )
            return {"status": AiStatus.SKIPPED.value, "analysed": 0, "failed": 0}

        pending = repo.iter_exceptions_for_ai(
            session, job_id, settings.ai_max_exceptions_per_job
        )
        if not pending:
            return {"status": AiStatus.COMPLETED.value, "analysed": 0, "failed": 0}

        held_back = self._count_pending_beyond_cap(session, job_id, len(pending))
        repo.write_audit(
            session, job_id, AuditEventType.AI_ANALYSIS_STARTED,
            f"{len(pending)} exception(s) routed to the classifier"
            + (f"; {held_back} held back by the per-job cap." if held_back else "."),
            actor="AI Analyst", engine="ai", severity="info",
            metadata={"model": self.service.model, "provider": self.service.name},
        )

        analysed = 0
        failed = 0
        tokens = 0
        batch_size = max(1, settings.ai_batch_size)

        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            facts = [build_facts(r) for r in batch]
            try:
                result = self.service.explain_exceptions(facts)
                tokens += result.usage.tokens
                analysed += self._apply(session, batch, facts, result.verdicts)
                failed += self._fail_unanswered(session, batch, result.verdicts)
            except LLMUnavailable as exc:
                failed += self._fail_batch(session, batch, str(exc))
                logger.warning("AI batch failed (job %s): %s", job_id, exc)
            except Exception as exc:  # provider bug, network stack, anything
                failed += self._fail_batch(session, batch, f"unexpected AI error: {exc}")
                logger.exception("unexpected AI failure on job %s", job_id)
            session.flush()

        status = (
            AiStatus.COMPLETED
            if analysed and not failed
            else AiStatus.FAILED
            if not analysed
            else AiStatus.COMPLETED
        )
        if analysed:
            repo.write_audit(
                session, job_id, AuditEventType.AI_ANALYSIS_COMPLETED,
                f"{analysed} exception(s) classified with an explanation"
                + (f"; {failed} could not be analysed." if failed else "."),
                actor="AI Analyst", engine="ai",
                severity="warning" if failed else "ok",
                metadata={"model": self.service.model, "tokens": str(tokens)},
            )
        else:
            repo.write_audit(
                session, job_id, AuditEventType.AI_ANALYSIS_FAILED,
                f"AI analysis unavailable for {failed} exception(s). "
                "Deterministic results are unaffected.",
                actor="AI Analyst", engine="ai", severity="warning",
            )

        return {
            "status": status.value,
            "analysed": analysed,
            "failed": failed,
            "tokens": tokens,
            "heldBack": held_back,
        }

    # -- internals -------------------------------------------------------

    @staticmethod
    def _count_pending_beyond_cap(session: Session, job_id: str, taken: int) -> int:
        from sqlalchemy import func, select

        total = session.scalar(
            select(func.count())
            .select_from(ExceptionRecord)
            .where(
                ExceptionRecord.job_id == job_id,
                ExceptionRecord.ai_status == AiStatus.PENDING.value,
            )
        ) or 0
        return max(0, total - taken)

    def _apply(
        self,
        session: Session,
        batch: Sequence[ExceptionRecord],
        facts: Sequence[ExceptionFacts],
        verdicts: Sequence[AiVerdict],
    ) -> int:
        by_id = {v.exception_id: v for v in verdicts}
        applied = 0
        for record in batch:
            verdict = by_id.get(record.id)
            if verdict is None:
                continue
            record.ai_status = AiStatus.COMPLETED.value
            record.ai_classification = verdict.classification
            record.ai_explanation = verdict.explanation
            record.ai_confidence = verdict.confidence.value
            record.ai_signals = verdict.signals
            record.ai_recommended_action = verdict.recommended_action
            record.ai_model = self.service.model
            record.ai_analysed_at = utcnow()
            record.ai_error = None
            # Human review is the union of the engine's judgement and the
            # model's: the model may add a flag, never clear one.
            record.requires_human_review = bool(
                record.requires_human_review
                or verdict.requires_human_review
                or verdict.classification == ExceptionType.UNRESOLVED.value
            )
            applied += 1
        return applied

    @staticmethod
    def _fail_unanswered(
        session: Session, batch: Sequence[ExceptionRecord], verdicts: Sequence[AiVerdict]
    ) -> int:
        answered = {v.exception_id for v in verdicts}
        failed = 0
        for record in batch:
            if record.id in answered:
                continue
            record.ai_status = AiStatus.FAILED.value
            record.ai_error = "Model returned no valid verdict for this exception."
            record.requires_human_review = True
            failed += 1
        return failed

    @staticmethod
    def _fail_batch(session: Session, batch: Sequence[ExceptionRecord], message: str) -> int:
        for record in batch:
            record.ai_status = AiStatus.FAILED.value
            record.ai_error = message[:500]
            record.requires_human_review = True
        return len(batch)

    @staticmethod
    def _mark_all(session: Session, job_id: str, status: AiStatus, message: str) -> None:
        session.query(ExceptionRecord).filter(
            ExceptionRecord.job_id == job_id,
            ExceptionRecord.ai_status == AiStatus.PENDING.value,
        ).update({"ai_status": status.value, "ai_error": message}, synchronize_session=False)
