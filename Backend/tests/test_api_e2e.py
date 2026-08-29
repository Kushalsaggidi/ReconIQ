"""End-to-end API test.

Drives the exact sequence the frontend will: upload three CSVs, run, poll,
then read results, transactions, exceptions, detail and audit.  Also asserts
the response *shape*, because the frontend's types file is a contract and a
silent rename here would break it.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import write_csv

API = "/api/reconciliation"


@pytest.fixture
def client(tmp_db: Path) -> TestClient:
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def csvs(tmp_path: Path) -> dict[str, Path]:
    """A tiny dataset covering matched, exception and unresolved outcomes."""
    orders = write_csv(
        tmp_path / "orders.csv",
        "order_id,payment_id,order_amount,currency,order_date,status,payment_method",
        [
            "O-1,P-1,2000.00,INR,2026-08-01 10:00:00,captured,UPI",      # matched
            "O-2,P-2,2000.00,INR,2026-08-01 11:00:00,captured,Card",     # partial
            "O-3,P-3,2000.00,INR,2026-08-01 12:00:00,captured,UPI",      # unresolved
            "O-4,P-4,2000.00,INR,2026-08-01 13:00:00,captured,Wallet",   # rounding
        ],
    )
    settlements = write_csv(
        tmp_path / "settlements.csv",
        "settlement_id,payment_id,gross_amount,fee,tax,refund_amount,"
        "settlement_amount,currency,settlement_date,utr",
        [
            "S-1,P-1,2000.00,20.00,3.60,0,1976.40,INR,2026-08-03,UTR-1",
            "S-2,P-2,2000.00,20.00,3.60,0,1976.40,INR,2026-08-03,UTR-2",
            "S-4,P-4,2000.00,20.00,3.60,0,1976.40,INR,2026-08-03,UTR-4",
        ],
    )
    bank = write_csv(
        tmp_path / "bank.csv",
        "bank_transaction_id,settlement_id,utr,credit_amount,currency,value_date,narration",
        [
            "B-1,S-1,UTR-1,1976.40,INR,2026-08-03,NEFT CR RAZORPAY",
            "B-2,S-2,UTR-2,1726.40,INR,2026-08-03,NEFT CR RAZORPAY",
            "B-4,S-4,UTR-4,1975.90,INR,2026-08-03,NEFT CR RAZORPAY",
        ],
    )
    return {"orders": orders, "settlements": settlements, "bank": bank}


def upload(client: TestClient, kind: str, path: Path) -> dict:
    with path.open("rb") as fh:
        response = client.post(
            f"{API}/upload",
            data={"kind": kind},
            files={"file": (path.name, fh, "text/csv")},
        )
    assert response.status_code == 201, response.text
    return response.json()


def run_to_completion(client: TestClient, ids: dict[str, str], timeout: float = 30.0) -> str:
    response = client.post(
        f"{API}/run",
        json={
            "ordersDatasetId": ids["orders"],
            "settlementsDatasetId": ids["settlements"],
            "bankDatasetId": ids["bank"],
            "source": "pytest",
        },
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["jobId"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"{API}/{job_id}/status").json()
        if status["status"] in ("completed", "failed"):
            assert status["status"] == "completed", status.get("error")
            return job_id
        time.sleep(0.05)
    pytest.fail("job did not finish within the timeout")


# --- tests ------------------------------------------------------------------

def test_health(client: TestClient):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    # A key must never be echoed back, only whether one exists.
    assert set(body["ai"]) >= {"provider", "model", "keyConfigured"}
    assert body["ai"]["keyConfigured"] in (True, False)


def test_upload_reports_rows_and_checksum(client: TestClient, csvs):
    body = upload(client, "orders", csvs["orders"])

    assert body["rows"] == 4
    assert body["rejected"] == 0
    assert body["checksum"].startswith("sha256:")
    assert body["columnMapping"]["order_amount"] == "order_amount"


def test_upload_rejects_a_file_missing_required_columns(client: TestClient, tmp_path: Path):
    bad = write_csv(tmp_path / "bad.csv", "foo,bar", ["1,2"])
    with bad.open("rb") as fh:
        response = client.post(
            f"{API}/upload", data={"kind": "orders"},
            files={"file": (bad.name, fh, "text/csv")},
        )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "MISSING_REQUIRED_COLUMNS"
    assert {i["column"] for i in error["issues"]} == {"order_id", "payment_id", "order_amount"}
    assert error["context"]["headersSeen"] == ["foo", "bar"]


def test_upload_rejects_a_non_csv(client: TestClient, tmp_path: Path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello", encoding="utf-8")
    with bad.open("rb") as fh:
        response = client.post(
            f"{API}/upload", data={"kind": "orders"},
            files={"file": (bad.name, fh, "text/plain")},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE_TYPE"


def test_full_reconciliation_flow(client: TestClient, csvs):
    ids = {kind: upload(client, kind, path)["datasetId"] for kind, path in csvs.items()}
    job_id = run_to_completion(client, ids)

    # --- results -----------------------------------------------------
    results = client.get(f"{API}/{job_id}/results").json()
    assert results["recordsProcessed"] == 4
    assert results["matched"] == 1
    assert results["unresolved"] == 1
    assert results["exceptions"] == 2
    assert results["matchRate"] == 25.0
    assert results["grossValue"] == 800_000        # 4 x Rs 2000, in paise
    assert results["currency"] == "INR"
    # Buckets always arrive in display order with zeros included.
    assert [b["type"] for b in results["buckets"]] == [
        "partial_payment", "refund", "fee_tax", "rounding", "unresolved"
    ]
    assert results["breakdown"]["partial_payment_count"] == 1
    assert results["breakdown"]["rounding_count"] == 1
    assert results["breakdown"]["unresolved_count"] == 1
    assert {d["kind"] for d in results["datasets"]} == {"orders", "settlements", "bank"}

    # --- transactions ------------------------------------------------
    page = client.get(f"{API}/{job_id}/transactions?page=1&page_size=2").json()
    assert page["total"] == 4
    assert page["totalPages"] == 2
    assert len(page["rows"]) == 2
    assert page["facets"] == {"matched": 1, "exception": 2, "unresolved": 1}

    row = page["rows"][0]
    assert row["orderId"] == "O-1"
    assert row["expected"] == 200_000              # integer paise, not a float
    assert row["settled"] == 197_640
    assert row["difference"] == 2_360
    assert row["status"] == "matched"
    assert row["exceptionType"] is None

    # --- filtering ---------------------------------------------------
    filtered = client.get(
        f"{API}/{job_id}/transactions?status=exception&exception_type=rounding"
    ).json()
    assert filtered["total"] == 1
    assert filtered["rows"][0]["orderId"] == "O-4"

    searched = client.get(f"{API}/{job_id}/transactions?search=O-2").json()
    assert searched["total"] == 1

    # --- exceptions --------------------------------------------------
    exceptions = client.get(f"{API}/{job_id}/exceptions").json()
    assert exceptions["total"] == 3                # never includes matched rows
    assert all(r["status"] != "matched" for r in exceptions["rows"])

    # --- exception detail --------------------------------------------
    detail = client.get(f"{API}/{job_id}/exceptions/O-2").json()
    assert detail["transaction"]["orderId"] == "O-2"
    computed = detail["computed"]
    assert computed["expected"] == 200_000
    assert computed["settled"] == 172_640
    assert computed["difference"] == 27_360
    assert computed["accountedFor"] == 2_360
    assert computed["unexplained"] == 25_000
    assert any(c["label"] == "Variance fully accounted for" and not c["passed"]
               for c in computed["checks"])
    assert {e["source"] for e in detail["evidence"]} == {
        "Orders dataset", "Razorpay settlement", "Bank statement"
    }
    assert detail["ai"]["status"] in ("completed", "failed", "skipped")

    # The unresolved record must not carry a fabricated explanation.
    unresolved = client.get(f"{API}/{job_id}/exceptions/O-3").json()
    assert unresolved["transaction"]["status"] == "unresolved"
    assert unresolved["ai"]["requiresHumanReview"] is True

    # --- audit --------------------------------------------------------
    audit = client.get(f"{API}/{job_id}/audit").json()
    types = [e["title"] for e in audit["rows"]]
    assert "Reconciliation job created" in types
    assert "Records reconciled" in types
    assert "Report generated" in types
    assert audit["rows"] == sorted(audit["rows"], key=lambda e: e["at"])

    # --- export -------------------------------------------------------
    export = client.get(f"{API}/{job_id}/export?exceptions_only=true")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert len(export.text.strip().splitlines()) == 4      # header + 3 exceptions


def test_status_of_an_unknown_job_is_404(client: TestClient):
    response = client.get(f"{API}/NOPE/status")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_run_with_an_unknown_dataset_is_404(client: TestClient):
    response = client.post(
        f"{API}/run",
        json={"ordersDatasetId": "nope", "settlementsDatasetId": "nope"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DATASET_NOT_FOUND"


def test_page_size_is_capped_server_side(client: TestClient, csvs):
    ids = {kind: upload(client, kind, path)["datasetId"] for kind, path in csvs.items()}
    job_id = run_to_completion(client, ids)

    response = client.get(f"{API}/{job_id}/transactions?page_size=100000")
    assert response.status_code == 422   # rejected rather than silently honoured
