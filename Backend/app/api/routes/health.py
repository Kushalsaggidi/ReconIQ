"""Liveness and configuration introspection."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.ai.factory import get_ai_service
from app.core.config import get_settings
from app.schemas.api import HealthResponse
from app.storage.db import get_engine

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # surfaced, not raised -- health must always answer
        database = f"error: {exc}"

    service = get_ai_service()
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        environment=settings.environment,
        database=database,
        ai={
            "provider": service.name,
            "model": service.model,
            "enabled": settings.ai_enabled,
            # Never echo the key itself -- only whether one is configured.
            "keyConfigured": bool(settings.llm_api_key),
            "maxExceptionsPerJob": settings.ai_max_exceptions_per_job,
        },
    )
