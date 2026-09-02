"""Database engine and session management.

One engine per process.  ``session_scope`` is the only sanctioned way to write:
it commits on success and rolls back on any exception, so a failed job can
never leave half-written results behind.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.base import Base

logger = get_logger(__name__)

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _configure_sqlite(engine: Engine) -> None:
    """SQLite defaults are wrong for a service; fix them at connect time.

    WAL lets the API read while a background job writes -- without it, polling
    /status during a run blocks on the writer's lock. ``busy_timeout`` covers
    the remaining case: two *writers* at once (the job pipeline's background
    thread and, e.g., a Copilot request's audit-log write arriving mid-run).
    Without it, SQLite's default is to fail immediately with "database is
    locked" instead of waiting -- this makes a transient, sub-second
    contention wait it out rather than surface as a request failure.
    """

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        is_sqlite = url.startswith("sqlite")
        _engine = create_engine(
            url,
            echo=settings.sql_echo,
            future=True,
            # The background job runs on a worker thread; the default
            # check_same_thread=True would reject its connections.
            connect_args={"check_same_thread": False} if is_sqlite else {},
            pool_pre_ping=not is_sqlite,
        )
        if is_sqlite:
            _configure_sqlite(_engine)
        logger.info("database engine ready (%s)", url.split("://", 1)[0])
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True
        )
    return _SessionFactory


def init_db() -> None:
    """Create tables if absent.

    Fine for a hackathon and for local dev.  Introduce Alembic before the first
    schema change against a database anyone else is using.
    """
    Base.metadata.create_all(bind=get_engine())
    logger.info("schema ensured (%s tables)", len(Base.metadata.tables))


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency -- read-only request scope."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    """Drop cached engine/session factory.  Used by tests to swap databases."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
