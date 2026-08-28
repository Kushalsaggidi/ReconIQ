"""Ingestion, normalisation and validation.

Covers the "bad file" half of the spec: missing columns, malformed amounts,
missing identifiers, duplicates and unusual headers.  The recurring assertion
is that nothing is silently discarded -- every rejection is reportable with a
row number and a reason.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.core.enums import DatasetKind
from app.core.errors import ErrorCode, ValidationFailure
from app.core.money import MoneyParseError, format_money, to_major, to_minor
from app.ingestion.column_map import resolve_columns, slugify
from app.ingestion.loader import load_dataset
from app.ingestion.normalizer import (
    DateParseError,
    normalize_currency,
    normalize_date,
    normalize_id,
)
from tests.conftest import write_csv

ORDERS_HEADER = "order_id,payment_id,order_amount,currency,order_date,status"


def orders_csv(tmp_path: Path, rows: list[str], header: str = ORDERS_HEADER) -> Path:
    return write_csv(tmp_path / "orders.csv", header, rows)


# --- money -----------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1000", 100_000),
        ("1000.00", 100_000),
        ("1,000", 100_000),
        ("₹1,000", 100_000),
        ("₹ 1,000.50", 100_050),
        ("  2000.5  ", 200_050),
        ("(250.00)", -25_000),
        ("-250", -25_000),
        (1000, 100_000),
        (1000.5, 100_050),
        (Decimal("19.999"), 2_000),   # half-up at the paise boundary
    ],
)
def test_amount_parsing(raw: object, expected: int):
    assert to_minor(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "abc", "1.2.3", "N/A", None, "12 34,56"])
def test_unparsable_amounts_raise_with_a_reason(raw: object):
    with pytest.raises(MoneyParseError) as exc:
        to_minor(raw)
    assert exc.value.reason


def test_money_round_trips_and_formats():
    assert to_major(197_640) == Decimal("1976.40")
    assert format_money(197_640) == "₹1,976.40"


# --- identifiers and dates --------------------------------------------------

def test_float_shaped_ids_are_normalised():
    """The classic silent-join-failure: pandas reads 123456 as 123456.0."""
    assert normalize_id(123456.0) == "123456"
    assert normalize_id("123456.0") == "123456"
    assert normalize_id("  pay_001  ") == "pay_001"
    assert normalize_id("") is None
    assert normalize_id("nan") is None


@pytest.mark.parametrize(
    "raw",
    ["2026-08-01", "2026-08-01 10:30:00", "2026-08-01T10:30:00Z", "01/08/2026",
     "01-08-2026", "01-Aug-2026"],
)
def test_common_date_formats_parse(raw: str):
    assert normalize_date(raw) is not None


def test_impossible_date_is_reported_not_guessed():
    with pytest.raises(DateParseError):
        normalize_date("31/02/2026")


def test_currency_symbols_map_to_iso_codes():
    assert normalize_currency("₹") == "INR"
    assert normalize_currency("inr") == "INR"
    assert normalize_currency("") == "INR"
    assert normalize_currency("XYZ") == "INR"  # unknown falls back to default


# --- column resolution ------------------------------------------------------

def test_slugify_handles_real_export_headers():
    assert slugify("Settlement Amount (INR)") == "settlement_amount_inr"
    assert slugify("  Order ID  ") == "order_id"


def test_aliased_headers_resolve():
    mapping = resolve_columns(
        DatasetKind.ORDERS,
        ["Order No", "Razorpay Payment Id", "Amount", "Created At"],
    )
    assert mapping.mapping["order_id"] == "Order No"
    assert mapping.mapping["payment_id"] == "Razorpay Payment Id"
    assert mapping.mapping["order_amount"] == "Amount"
    assert mapping.mapping["order_date"] == "Created At"


def test_missing_required_columns_reports_all_of_them_at_once():
    with pytest.raises(ValidationFailure) as exc:
        resolve_columns(DatasetKind.ORDERS, ["something", "else"])

    codes = {i.code for i in exc.value.issues}
    assert codes == {ErrorCode.MISSING_REQUIRED_COLUMNS}
    missing = {i.column for i in exc.value.issues}
    assert missing == {"order_id", "payment_id", "order_amount"}
    # The error must show what the file actually had, or it is not actionable.
    assert exc.value.context["headersSeen"] == ["something", "else"]


def test_bank_file_needs_a_joinable_key():
    with pytest.raises(ValidationFailure) as exc:
        resolve_columns(DatasetKind.BANK, ["bank_transaction_id", "credit_amount"])
    assert "at least one of" in " ".join(i.message for i in exc.value.issues)


def test_unrecognised_columns_are_reported_not_silently_ignored():
    mapping = resolve_columns(
        DatasetKind.ORDERS, ["order_id", "payment_id", "order_amount", "internal_ref"]
    )
    assert mapping.unmapped_headers == ["internal_ref"]


# --- file loading -----------------------------------------------------------

def test_clean_file_loads(tmp_path: Path):
    path = orders_csv(tmp_path, [
        "O-1,P-1,2000.00,INR,2026-08-01,captured",
        "O-2,P-2,₹1500,INR,2026-08-02,captured",
    ])
    dataset = load_dataset(path, DatasetKind.ORDERS)

    assert dataset.row_count == 2
    assert dataset.rejected_count == 0
    assert dataset.records[1].order_amount == 150_000
    assert dataset.checksum and dataset.checksum.startswith("sha256:")


def test_malformed_amount_rejects_only_that_row(tmp_path: Path):
    path = orders_csv(tmp_path, [
        "O-1,P-1,2000.00,INR,2026-08-01,captured",
        "O-2,P-2,not-a-number,INR,2026-08-02,captured",
        "O-3,P-3,1500.00,INR,2026-08-03,captured",
    ])
    dataset = load_dataset(path, DatasetKind.ORDERS)

    assert dataset.row_count == 2          # the good rows survive
    assert dataset.rejected_count == 1
    issue = dataset.issues["samples"][0]
    assert issue["code"] == ErrorCode.INVALID_AMOUNT.value
    assert issue["rowNumber"] == 3         # the line number in the file
    assert issue["rawValue"] == "not-a-number"


def test_missing_identifier_is_rejected_with_its_row(tmp_path: Path):
    path = orders_csv(tmp_path, [
        "O-1,P-1,2000.00,INR,2026-08-01,captured",
        ",P-2,1500.00,INR,2026-08-02,captured",
        "O-3,,1500.00,INR,2026-08-03,captured",
    ])
    dataset = load_dataset(path, DatasetKind.ORDERS)

    assert dataset.row_count == 1
    assert dataset.issues["byCode"][ErrorCode.MISSING_IDENTIFIER.value] == 2


def test_invalid_date_is_rejected(tmp_path: Path):
    path = orders_csv(tmp_path, [
        "O-1,P-1,2000.00,INR,31/02/2026,captured",
    ])
    with pytest.raises(ValidationFailure):
        load_dataset(path, DatasetKind.ORDERS)  # every row rejected -> file fails


def test_duplicate_ids_keep_the_first_and_warn(tmp_path: Path):
    path = orders_csv(tmp_path, [
        "O-1,P-1,2000.00,INR,2026-08-01,captured",
        "O-1,P-9,9999.00,INR,2026-08-02,captured",
    ])
    dataset = load_dataset(path, DatasetKind.ORDERS)

    assert dataset.row_count == 1
    assert dataset.records[0].payment_id == "P-1"       # first wins
    assert dataset.issues["byCode"][ErrorCode.DUPLICATE_IDENTIFIER.value] == 1


def test_negative_order_amount_is_rejected(tmp_path: Path):
    path = orders_csv(tmp_path, ["O-1,P-1,-2000.00,INR,2026-08-01,captured"])
    with pytest.raises(ValidationFailure) as exc:
        load_dataset(path, DatasetKind.ORDERS)
    assert ErrorCode.NEGATIVE_AMOUNT.value in exc.value.context["issues"]["byCode"]


def test_empty_file_is_reported(tmp_path: Path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(Exception) as exc:
        load_dataset(path, DatasetKind.ORDERS)
    assert "empty" in str(exc.value).lower()


def test_settlement_optional_components_default_to_zero(tmp_path: Path):
    path = write_csv(
        tmp_path / "s.csv",
        "settlement_id,payment_id,settlement_amount,gross_amount,fee,tax",
        ["S-1,P-1,1976.40,2000.00,,"],
    )
    dataset = load_dataset(path, DatasetKind.SETTLEMENTS)

    record = dataset.records[0]
    assert record.fee == 0 and record.tax == 0
    assert record.gross_amount == 200_000


def test_negative_deduction_components_are_normalised_to_magnitudes(tmp_path: Path):
    """Some exports emit fees as negatives; sign lives in the formula, not the data."""
    path = write_csv(
        tmp_path / "s.csv",
        "settlement_id,payment_id,settlement_amount,gross_amount,fee,tax",
        ["S-1,P-1,1976.40,2000.00,-20.00,-3.60"],
    )
    record = load_dataset(path, DatasetKind.SETTLEMENTS).records[0]

    assert record.fee == 2_000
    assert record.tax == 360


def test_chunk_size_does_not_change_the_parsed_result(tmp_path: Path):
    rows = [f"O-{i},P-{i},1000.00,INR,2026-08-01,captured" for i in range(97)]
    path = orders_csv(tmp_path, rows)

    whole = load_dataset(path, DatasetKind.ORDERS, chunk_size=10_000)
    chunked = load_dataset(path, DatasetKind.ORDERS, chunk_size=7)

    assert whole.row_count == chunked.row_count == 97
    assert [r.order_id for r in whole.records] == [r.order_id for r in chunked.records]
