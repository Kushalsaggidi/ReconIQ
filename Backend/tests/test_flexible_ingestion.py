"""Flexible ingestion: multi-format readers, alias coverage, dataset-type
detection, and the real previously-failing ``internal_transactions.csv``.

Nothing here relaxes validation to make a file pass -- every accepted file
still goes through the exact same column resolution, normalisation and
row-level checks as a plain CSV.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.enums import DatasetKind
from app.core.errors import ValidationFailure
from app.ingestion.column_map import detect_dataset_kind, resolve_columns
from app.ingestion.loader import load_dataset
from app.schemas.domain import SettlementRecord
from tests.conftest import write_csv

API = "/api/reconciliation"
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"
SAMPLE_FILE = SAMPLES_DIR / "internal_transactions.csv"
PROCESSOR_FILE = SAMPLES_DIR / "processor_transactions.csv"
BANK_SETTLEMENTS_FILE = SAMPLES_DIR / "bank_settlements.csv"

ORDERS_ROWS = [
    "O-1,P-1,2000.00,INR,2026-08-01 10:00:00,captured",
    "O-2,P-2,1500.00,INR,2026-08-02 10:00:00,captured",
]
ORDERS_HEADER = "order_id,payment_id,order_amount,currency,order_date,status"


# ---------------------------------------------------------------------------
# Format support: CSV / XLSX / XLS / JSON all reach the same canonical shape.
# ---------------------------------------------------------------------------

def _expected_orders(dataset):
    assert dataset.row_count == 2
    ids = sorted(r.order_id for r in dataset.records)
    assert ids == ["O-1", "O-2"]
    assert dataset.records[0].order_amount in (200_000, 150_000)


def test_csv_format(tmp_path: Path):
    path = write_csv(tmp_path / "orders.csv", ORDERS_HEADER, ORDERS_ROWS)
    dataset = load_dataset(path, DatasetKind.ORDERS)
    assert dataset.format == "csv"
    _expected_orders(dataset)


def test_xlsx_format(tmp_path: Path):
    frame = pd.DataFrame(
        [
            {"order_id": "O-1", "payment_id": "P-1", "order_amount": 2000.00,
             "currency": "INR", "order_date": "2026-08-01", "status": "captured"},
            {"order_id": "O-2", "payment_id": "P-2", "order_amount": 1500.00,
             "currency": "INR", "order_date": "2026-08-02", "status": "captured"},
        ]
    )
    path = tmp_path / "orders.xlsx"
    frame.to_excel(path, index=False)
    dataset = load_dataset(path, DatasetKind.ORDERS)
    assert dataset.format == "xlsx"
    _expected_orders(dataset)


def test_xls_dispatches_to_the_excel_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Legacy .xls has no maintained Python writer to build a real fixture
    with, so this pins the dispatch instead: `.xls` must route to the same
    Excel reader class `.xlsx` uses (pandas picks the `xlrd` engine for it
    internally). `ExcelChunkReader.__init__` is stubbed out so no actual
    parsing happens -- only which class `reader_for` chose is asserted."""
    import app.ingestion.readers as readers_mod

    seen: dict[str, type] = {}
    original_init = readers_mod.ExcelChunkReader.__init__

    def fake_init(self, path, *, chunk_size=10_000):
        seen["cls"] = type(self)
        self.path = path
        self.chunk_size = chunk_size
        self.headers = []
        self._frame = None

    monkeypatch.setattr(readers_mod.ExcelChunkReader, "__init__", fake_init)
    path = tmp_path / "orders.xls"
    path.write_bytes(b"placeholder")
    readers_mod.reader_for(path, DatasetKind.ORDERS, 10_000)
    assert seen["cls"] is readers_mod.ExcelChunkReader
    monkeypatch.setattr(readers_mod.ExcelChunkReader, "__init__", original_init)


def test_json_array_format(tmp_path: Path):
    path = tmp_path / "orders.json"
    path.write_text(
        json.dumps(
            [
                {"order_id": "O-1", "payment_id": "P-1", "order_amount": "2000.00",
                 "currency": "INR", "order_date": "2026-08-01", "status": "captured"},
                {"order_id": "O-2", "payment_id": "P-2", "order_amount": "1500.00",
                 "currency": "INR", "order_date": "2026-08-02", "status": "captured"},
            ]
        ),
        encoding="utf-8",
    )
    dataset = load_dataset(path, DatasetKind.ORDERS)
    assert dataset.format == "json"
    _expected_orders(dataset)


def test_json_wrapped_in_records_key(tmp_path: Path):
    path = tmp_path / "orders.json"
    path.write_text(
        json.dumps(
            {
                "records": [
                    {"order_id": "O-1", "payment_id": "P-1", "order_amount": "2000.00",
                     "currency": "INR", "order_date": "2026-08-01", "status": "captured"},
                    {"order_id": "O-2", "payment_id": "P-2", "order_amount": "1500.00",
                     "currency": "INR", "order_date": "2026-08-02", "status": "captured"},
                ]
            }
        ),
        encoding="utf-8",
    )
    dataset = load_dataset(path, DatasetKind.ORDERS)
    _expected_orders(dataset)


def test_json_must_be_an_array(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"order_id": "O-1"}), encoding="utf-8")
    with pytest.raises(Exception):
        load_dataset(path, DatasetKind.ORDERS)


def test_unsupported_format_is_rejected(tmp_path: Path):
    path = tmp_path / "orders.pdf"
    path.write_bytes(b"%PDF-1.4 not a real pdf")
    from app.core.errors import IngestionError

    with pytest.raises(IngestionError):
        load_dataset(path, DatasetKind.ORDERS)


# ---------------------------------------------------------------------------
# Alias coverage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "header",
    [
        "order_id,payment_id,order_amount,currency,order_date,status",
        "Order ID,Payment ID,Order Amount,currency,order_date,status",
        "Order No,razorpay_payment_id,gross_amount,currency,order_date,status",
        "merchant_order_id,internal_payment_id,transaction_amount,currency,order_date,status",
        "razorpay_order_id,txn_id,Order Amount,currency,order_date,status",
    ],
)
def test_orders_header_aliases_resolve(header: str):
    mapping = resolve_columns(DatasetKind.ORDERS, header.split(","))
    assert mapping.has("order_id")
    assert mapping.has("payment_id")
    assert mapping.has("order_amount")


def test_internal_transactions_columns_map_as_expected():
    headers = [
        "internal_payment_id", "merchant_order_id", "occurred_at", "gross_amount",
        "currency", "payment_status", "payment_method", "synthetic_customer_reference",
    ]
    mapping = resolve_columns(DatasetKind.ORDERS, headers)
    assert mapping.header_for("payment_id") == "internal_payment_id"
    assert mapping.header_for("order_id") == "merchant_order_id"
    assert mapping.header_for("order_date") == "occurred_at"
    assert mapping.header_for("order_amount") == "gross_amount"
    assert mapping.header_for("status") == "payment_status"
    assert mapping.header_for("method") == "payment_method"
    # Unknown, non-required column is left unmapped rather than forced in.
    assert "synthetic_customer_reference" in mapping.unmapped_headers


# ---------------------------------------------------------------------------
# Dataset-type detection
# ---------------------------------------------------------------------------

def test_detects_orders():
    d = detect_dataset_kind(["order_id", "payment_id", "order_amount", "order_date"])
    assert d.best is DatasetKind.ORDERS
    assert not d.ambiguous


def test_detects_settlements():
    d = detect_dataset_kind(
        ["settlement_id", "payment_id", "settlement_amount", "fee", "tax", "utr"]
    )
    assert d.best is DatasetKind.SETTLEMENTS


def test_detects_bank_statement():
    d = detect_dataset_kind(["bank_transaction_id", "utr", "credit_amount", "narration"])
    assert d.best is DatasetKind.BANK


def test_settlement_file_sharing_order_and_payment_ids_is_not_misread_as_orders():
    """A settlement is naturally linked to an order and a payment, so a real
    settlement export legitimately carries order_id/payment_id alongside its
    own distinguishing fields (settlement_id, fee, tax, utr, settlement_date).
    That overlap must not tip classification towards Orders."""
    d = detect_dataset_kind(
        [
            "settlement_id", "order_id", "payment_id", "settlement_amount",
            "fee", "tax", "utr", "settlement_date", "settlement_status",
        ]
    )
    assert d.best is DatasetKind.SETTLEMENTS
    assert not d.ambiguous
    assert d.scores[DatasetKind.SETTLEMENTS] > d.scores[DatasetKind.ORDERS]


def test_generic_shared_words_alone_do_not_strongly_indicate_any_kind():
    """`amount`, `date`, `status`, `currency` appear in every real export of
    every kind -- on their own they must not push a confident classification
    either way (this is the alias-specificity discount, not the required-field
    ratio the previous implementation used)."""
    generic_only = detect_dataset_kind(["amount", "date", "status", "currency"])
    specific = detect_dataset_kind(
        ["settlement_id", "settlement_amount", "settlement_date", "settlement_status"]
    )
    assert specific.confidence > generic_only.confidence


def test_ambiguous_headers_are_flagged():
    # payment_id + amount + date fit orders and settlements almost equally --
    # neither should win with a confident, unambiguous margin.
    d = detect_dataset_kind(["payment_id", "amount", "date"])
    assert d.ambiguous


def test_confident_mismatch_blocks_upload(tmp_path: Path):
    # A settlements-shaped file uploaded as orders should be rejected with a
    # clear, actionable message rather than silently forced through.
    path = write_csv(
        tmp_path / "settlements.csv",
        "settlement_id,payment_id,settlement_amount,fee,tax,utr,settlement_date",
        ["S-1,P-1,1976.40,20.00,3.60,UTR-1,2026-08-03"],
    )
    with pytest.raises(ValidationFailure) as exc:
        load_dataset(path, DatasetKind.ORDERS)
    assert "settlements" in exc.value.message.lower()


# ---------------------------------------------------------------------------
# Safety: no dangerous fuzzy guessing
# ---------------------------------------------------------------------------

def test_amount_does_not_silently_become_tax_amount():
    """`amount` must resolve to the dataset's primary amount field, never to
    a deduction component it merely resembles."""
    mapping = resolve_columns(
        DatasetKind.SETTLEMENTS,
        ["settlement_id", "payment_id", "amount", "utr"],
    )
    assert mapping.header_for("settlement_amount") == "amount"
    assert not mapping.has("tax")


def test_two_columns_claiming_the_same_field_is_ambiguous_not_guessed():
    with pytest.raises(ValidationFailure) as exc:
        resolve_columns(
            DatasetKind.ORDERS,
            ["order_id", "payment_id", "amount", "gross_amount", "order_date"],
        )
    assert any(i.code.value == "AMBIGUOUS_COLUMN" for i in exc.value.issues)


def test_settlements_without_any_payment_id_column_still_resolve_via_order_id():
    """A settlement export with only a merchant order reference (no payment
    id at all) must resolve columns successfully -- the one_of(payment_id,
    order_id) group, not a hard payment_id requirement."""
    mapping = resolve_columns(
        DatasetKind.SETTLEMENTS,
        ["settlement_id", "order_id", "settlement_amount", "utr"],
    )
    assert not mapping.has("payment_id")
    assert mapping.header_for("order_id") == "order_id"


def test_settlements_with_neither_payment_id_nor_order_id_is_rejected():
    with pytest.raises(ValidationFailure) as exc:
        resolve_columns(
            DatasetKind.SETTLEMENTS,
            ["settlement_id", "settlement_amount", "utr"],
        )
    assert any(i.code.value == "MISSING_REQUIRED_COLUMNS" for i in exc.value.issues)


def test_order_id_only_settlement_still_joins_to_its_order():
    """Matcher-level regression: a settlement with no payment_id must still
    reconcile against its order via the order_id fallback index, end to end
    through the real (unmodified) reconciliation engine."""
    from app.reconciliation.engine import reconcile
    from tests.conftest import make_bank, make_order

    order = make_order(order_id="O-9", payment_id="P-9", amount=200_000)
    settlement = SettlementRecord(
        settlement_id="S-9",
        settlement_amount=197_640,
        order_id="O-9",  # no payment_id at all
        fee=2_000,
        tax=360,
        utr="BATCH-9",
    )
    bank = make_bank(bank_id="B-9", settlement_id=None, utr="BATCH-9", credit=197_640)

    result = reconcile([order], [settlement], [bank])
    assert result.metrics.matched_records == 1
    assert result.outcomes[0].status.value == "matched"


# ---------------------------------------------------------------------------
# Real end-to-end: the actual previously-failing file through the real API.
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_db: Path) -> TestClient:
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_internal_transactions_csv_passes_through_the_real_upload_endpoint(client: TestClient):
    assert SAMPLE_FILE.exists(), "fixture file missing"
    with SAMPLE_FILE.open("rb") as fh:
        resp = client.post(
            f"{API}/upload",
            data={"kind": "orders"},
            files={"file": ("internal_transactions.csv", fh, "text/csv")},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["rows"] == 1000
    assert body["format"] == "csv"
    assert body["columnMapping"]["payment_id"] == "internal_payment_id"
    assert body["columnMapping"]["order_id"] == "merchant_order_id"
    assert body["columnMapping"]["order_date"] == "occurred_at"
    assert body["columnMapping"]["order_amount"] == "gross_amount"
    assert "synthetic_customer_reference" in body["unmappedColumns"]
    assert body["ready"] is True


def test_processor_transactions_csv_is_classified_and_mapped_as_settlements(client: TestClient):
    """Regression for the reported bug: a settlements export that legitimately
    carries order_id (a settlement is naturally linked to an order) and no
    payment id at all must still be classified as Settlements, not Orders,
    and must still resolve columns even without a payment_id column."""
    assert PROCESSOR_FILE.exists(), "fixture file missing"
    with PROCESSOR_FILE.open("rb") as fh:
        resp = client.post(
            f"{API}/upload",
            data={"kind": "settlements"},
            files={"file": ("processor_transactions.csv", fh, "text/csv")},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["detectedKind"] == "settlements"
    assert body["columnMapping"]["settlement_id"] == "processor_transaction_id"
    # This file carries no payment id at all -- order_id is the only join key.
    assert "payment_id" not in body["columnMapping"]
    assert body["columnMapping"]["order_id"] == "merchant_order_id"
    assert body["columnMapping"]["settlement_amount"] == "net_amount"
    assert body["columnMapping"]["gross_amount"] == "gross_amount"
    assert body["columnMapping"]["fee"] == "fee_amount"
    assert body["columnMapping"]["settlement_date"] == "processor_event_time"
    assert body["columnMapping"]["utr"] == "settlement_batch_id"
    assert body["columnMapping"]["status"] == "processor_status"
    assert "processor_event_type" in body["unmappedColumns"]
    assert body["ready"] is True


def test_bank_settlements_csv_is_classified_and_mapped_as_bank(client: TestClient):
    assert BANK_SETTLEMENTS_FILE.exists(), "fixture file missing"
    with BANK_SETTLEMENTS_FILE.open("rb") as fh:
        resp = client.post(
            f"{API}/upload",
            data={"kind": "bank"},
            files={"file": ("bank_settlements.csv", fh, "text/csv")},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["detectedKind"] == "bank"
    assert body["columnMapping"]["bank_transaction_id"] == "bank_entry_id"
    assert body["columnMapping"]["utr"] == "settlement_batch_id"
    assert body["columnMapping"]["credit_amount"] == "credited_amount"
    assert body["columnMapping"]["description"] == "description"
    assert body["columnMapping"]["transaction_date"] == "booked_at"
    # `bank_reference` is this file's own descriptive reference, not the
    # cross-file join key (`settlement_batch_id` is) -- must not collide with
    # it and force an AMBIGUOUS_COLUMN error.
    assert "bank_reference" in body["unmappedColumns"]
    assert body["ready"] is True


def test_orders_settlements_bank_reconcile_together_end_to_end(client: TestClient):
    """The three real sample files, uploaded to their real slots, run through
    the unmodified reconciliation engine without error -- not just "uploads
    successfully". These files have no payment_id in the settlements leg (only
    order_id) and no direct settlement_id/utr shared with bank (only a batch
    reference), both of which previously had no working join path at all."""
    dataset_ids: dict[str, str] = {}
    for kind, path in (
        ("orders", SAMPLE_FILE),
        ("settlements", PROCESSOR_FILE),
        ("bank", BANK_SETTLEMENTS_FILE),
    ):
        with path.open("rb") as fh:
            resp = client.post(
                f"{API}/upload", data={"kind": kind}, files={"file": (path.name, fh, "text/csv")}
            )
        assert resp.status_code == 201, resp.text
        dataset_ids[kind] = resp.json()["datasetId"]

    run_resp = client.post(
        f"{API}/run",
        json={
            "ordersDatasetId": dataset_ids["orders"],
            "settlementsDatasetId": dataset_ids["settlements"],
            "bankDatasetId": dataset_ids["bank"],
            "source": "test",
        },
    )
    assert run_resp.status_code == 202, run_resp.text
    job_id = run_resp.json()["jobId"]

    import time

    for _ in range(50):
        status = client.get(f"{API}/{job_id}/status").json()
        if status["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert status["status"] == "completed", status

    results = client.get(f"{API}/{job_id}/results").json()
    # recordsProcessed includes orphan settlements (money with no matching
    # order) appended as their own unresolved records, so it can exceed the
    # order count -- that is by design, not a bug.
    assert results["recordsProcessed"] >= 1000
    # At least some orders resolved via the order_id join path -- proves the
    # fallback key is actually wired into the matcher, not just accepted at
    # the column-mapping layer.
    assert results["matched"] > 0
