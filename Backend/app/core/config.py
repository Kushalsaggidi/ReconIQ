"""Application configuration, sourced entirely from the environment.

Nothing here has a secret as a default.  ``.env.example`` documents every knob.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ----------------------------------------------------------
    app_name: str = "ReconIQ — AI-Powered Settlement Reconciliation Agent"
    environment: Literal["local", "dev", "staging", "prod"] = "local"
    debug: bool = True
    api_prefix: str = "/api"

    # --- CORS (the Lovable/Next.js frontend origin) --------------------
    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:5174,http://localhost:8080"

    # --- Persistence ---------------------------------------------------
    # SQLite for local dev; set DATABASE_URL to a postgresql+psycopg:// URL in
    # any shared environment. Model definitions are Postgres-compatible.
    database_url: str = Field(default=f"sqlite:///{(BASE_DIR / 'data' / 'recon.db').as_posix()}")
    sql_echo: bool = False

    # --- File storage ---------------------------------------------------
    # A local directory today; swap STORAGE_BACKEND for s3/gcs later without
    # touching callers (see app/storage/files.py).
    storage_backend: Literal["local"] = "local"
    upload_storage_path: Path = BASE_DIR / "data" / "uploads"
    max_upload_bytes: int = 512 * 1024 * 1024  # 512 MiB
    #: Single source of truth for supported upload formats -- the frontend
    #: mirrors this via GET /health rather than hard-coding its own list.
    allowed_upload_suffixes: str = ".csv,.xlsx,.xls,.json"

    # --- Reconciliation engine ------------------------------------------
    #: Batch size the engine pulls per iteration. Bounds peak memory.
    batch_size: int = 10_000
    #: |unexplained| at or below this many minor units is a rounding artefact.
    rounding_tolerance_minor: int = 100  # Rs 1.00
    #: Everything above this is a hard variance, never "rounding".
    default_currency: str = "INR"

    # --- LLM -------------------------------------------------------------
    llm_provider: Literal["null", "anthropic", "openai", "gemini"] = "null"
    llm_api_key: str = ""
    model_name: str = "gemini-3.5-flash-lite"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    #: Hard ceiling on exceptions sent to the LLM per job. Protects cost and
    #: latency: we never stream a whole dataset to a model.
    ai_max_exceptions_per_job: int = 500
    #: Exceptions per LLM request.
    ai_batch_size: int = 20
    ai_enabled: bool = True

    @field_validator("upload_storage_path", mode="after")
    @classmethod
    def _ensure_dir(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_suffix_set(self) -> set[str]:
        return {s.strip().lower() for s in self.allowed_upload_suffixes.split(",") if s.strip()}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    return settings
