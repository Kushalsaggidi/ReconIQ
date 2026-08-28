"""FastAPI application factory.

The API is a shell around the engine, not the other way round: everything below
is wiring, CORS and error translation.  ``app.reconciliation`` has no idea this
file exists.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, reconciliation
from app.core.config import get_settings
from app.core.errors import ErrorCode, ReconError
from app.core.logging import configure_logging, get_logger
from app.services.job_service import get_job_runner, shutdown_job_runner
from app.storage.db import init_db

logger = get_logger(__name__)

DESCRIPTION = """
Deterministic three-way settlement reconciliation with an advisory AI layer.

**Division of labour**

* Python computes every figure: matching, joins, fees, tax, refunds, variance
  and all metrics. Money is handled as integer minor units (paise) end to end.
* The LLM only classifies and explains exceptions, reasoning over structured
  facts the engine already finalised. It never performs arithmetic, never
  matches records, and never marks anything reconciled.
* If the LLM fails, times out or returns invalid JSON, the affected exceptions
  are marked `ai_status: failed` and the deterministic result is unchanged.

**Typical flow**

1. `POST /api/reconciliation/upload` once per dataset (orders, settlements, bank)
2. `POST /api/reconciliation/run` with the three dataset ids -> `{ jobId }`
3. Poll `GET /api/reconciliation/{job_id}/status`
4. Read `/results`, `/transactions`, `/exceptions`, `/audit`
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    init_db()
    get_job_runner()
    logger.info(
        "%s ready (env=%s, llm=%s)",
        settings.app_name, settings.environment, settings.llm_provider,
    )
    yield
    shutdown_job_runner()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- error translation: one shape for every failure --------------------

    @app.exception_handler(ReconError)
    async def _recon_error(_request: Request, exc: ReconError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "REQUEST_VALIDATION_ERROR",
                    "message": "The request payload is invalid.",
                    "context": {},
                    "issues": [
                        {
                            "code": "REQUEST_VALIDATION_ERROR",
                            "severity": "ERROR",
                            "message": e.get("msg", ""),
                            "column": ".".join(str(p) for p in e.get("loc", ())),
                        }
                        for e in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        # Log the detail, return a safe message: internals are not client data.
        logger.exception("unhandled error")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": ErrorCode.RECONCILIATION_FAILED.value,
                    "message": "An unexpected server error occurred.",
                    "context": {},
                    "issues": [],
                }
            },
        )

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(reconciliation.router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "docs": "/docs",
            "health": f"{settings.api_prefix}/health",
        }

    return app


app = create_app()
