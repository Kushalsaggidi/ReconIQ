"""Copilot REST API.

One endpoint, thin by design like every other route in this package: parse,
delegate, serialise. All tool-calling, grounding and validation logic lives in
:mod:`app.copilot`.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.copilot.service import get_copilot_service
from app.schemas.api import CopilotRequest, CopilotResponse
from app.storage.db import session_scope

router = APIRouter(prefix="/reconciliation", tags=["copilot"])


@router.post("/{job_id}/copilot", response_model=CopilotResponse)
def copilot_ask(job_id: str, payload: CopilotRequest) -> CopilotResponse:
    """Ask the read-only ReconIQ Copilot a question about this job.

    A failure anywhere in the AI layer -- provider timeout, malformed
    response, a validation rejection -- comes back as a normal 200 with a safe
    fallback answer, never a 500: a chat feature failing must never look like
    the reconciliation itself failed. A missing or invalid job id is the one
    case that surfaces as an error response (404), the same as every other
    job-scoped endpoint.
    """
    with session_scope() as session:
        return get_copilot_service().ask(session, job_id, payload)
