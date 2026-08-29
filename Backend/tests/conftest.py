"""Shared fixtures.

Each test module gets its own throwaway SQLite file and upload directory, so
tests never see each other's rows and can run in any order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from app.schemas.domain import BankRecord, OrderRecord, SettlementRecord


def rupees(amount: float) -> int:
    """Test helper: rupees -> paise."""
    return int(round(amount * 100))


@pytest.fixture(scope="session", autouse=True)
def _quiet_logs() -> None:
    import logging

    logging.getLogger("app.reconciliation.engine").setLevel(logging.WARNING)


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the app at an isolated database and upload directory."""
    from app.core.config import get_settings
    from app.storage.db import init_db, reset_engine
    from app.storage.files import LocalFileStore, set_file_store

    db_path = tmp_path / "test.db"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_STORAGE_PATH", str(uploads))
    get_settings.cache_clear()
    reset_engine()
    set_file_store(LocalFileStore(uploads))
    init_db()
    yield db_path
    reset_engine()
    get_settings.cache_clear()
    set_file_store(None)  # type: ignore[arg-type]


@pytest.fixture
def session(tmp_db: Path):
    from app.storage.db import get_session_factory

    s = get_session_factory()()
    try:
        yield s
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Record builders -- one clean settlement chain, perturbed per test.
# ---------------------------------------------------------------------------

GROSS = rupees(2000)
FEE = rupees(20)
TAX = rupees(3.60)
NET = GROSS - FEE - TAX  # 197640 paise


def make_order(order_id: str = "O-1", payment_id: str = "P-1", amount: int = GROSS) -> OrderRecord:
    from datetime import datetime

    return OrderRecord(
        order_id=order_id,
        payment_id=payment_id,
        order_amount=amount,
        currency="INR",
        order_date=datetime(2026, 8, 1, 10, 0, 0),
        status="captured",
        method="UPI",
    )


def make_settlement(
    settlement_id: str = "S-1",
    payment_id: str = "P-1",
    *,
    net: int = NET,
    gross: int = GROSS,
    fee: int = FEE,
    tax: int = TAX,
    refund: int = 0,
    utr: str = "UTR-1",
) -> SettlementRecord:
    from datetime import datetime

    return SettlementRecord(
        settlement_id=settlement_id,
        payment_id=payment_id,
        settlement_amount=net,
        gross_amount=gross,
        fee=fee,
        tax=tax,
        refund_amount=refund,
        currency="INR",
        settlement_date=datetime(2026, 8, 3, 12, 0, 0),
        utr=utr,
    )


def make_bank(
    bank_id: str = "B-1",
    settlement_id: str | None = "S-1",
    *,
    credit: int = NET,
    utr: str | None = "UTR-1",
) -> BankRecord:
    from datetime import datetime

    return BankRecord(
        bank_transaction_id=bank_id,
        settlement_id=settlement_id,
        utr=utr,
        credit_amount=credit,
        currency="INR",
        transaction_date=datetime(2026, 8, 3, 12, 0, 0),
        description="NEFT CR RAZORPAY",
    )


@pytest.fixture
def csv_dir(tmp_path: Path) -> Path:
    d = tmp_path / "csv"
    d.mkdir()
    return d


def write_csv(path: Path, header: str, rows: list[str]) -> Path:
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


