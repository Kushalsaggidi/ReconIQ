"""SQLAlchemy declarative base and shared column types.

Written against the SQLAlchemy 2.0 typed API and kept Postgres-compatible:

* money is ``BigInteger`` minor units -- never ``FLOAT``, never ``NUMERIC`` with
  an implicit scale;
* JSON payloads use the generic ``JSON`` type, which maps to ``jsonb`` on
  Postgres and to a TEXT-backed column on SQLite;
* every timestamp is naive UTC, set server-side by Python so both backends
  agree.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, JSON, String
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class Money(TypeDecorator):
    """Integer minor units.

    A distinct type so a reader can see at a glance that a column is money, and
    so a future migration to ``NUMERIC(20,4)`` has exactly one place to change.
    """

    impl = BigInteger
    cache_ok = True


def id_column(prefix: str):
    return mapped_column(String(64), primary_key=True, default=lambda: new_id(prefix))


def timestamp_column(**kwargs):
    return mapped_column(DateTime, default=utcnow, **kwargs)
