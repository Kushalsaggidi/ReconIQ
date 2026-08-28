"""Ingestion orchestration: read -> resolve columns -> validate -> normalise.

The output is a :class:`NormalizedDataset` of canonical dataclasses plus a
complete issue report.  A row that cannot be turned into a canonical record is
*rejected and reported* -- never silently dropped, and never guessed at.

The loader consumes an ``Iterator[RowChunk]``, so replacing the CSV reader with
a database cursor requires no change here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterator

from app.core.enums import DatasetKind
from app.core.errors import (
    ErrorCode,
    IssueCollector,
    RecordIssue,
    Severity,
    ValidationFailure,
)
from app.core.money import MoneyParseError
from app.ingestion.column_map import ColumnMapping, resolve_columns
from app.ingestion.normalizer import (
    DateParseError,
    normalize_amount,
    normalize_currency,
    normalize_date,
    normalize_id,
    normalize_text,
)
from app.ingestion.readers import ChunkReader, RowChunk, checksum_file, reader_for
from app.schemas.domain import BankRecord, NormalizedDataset, OrderRecord, SettlementRecord

#: A row that produces one of these is rejected; the job continues.
_ROW_ERRORS = (MoneyParseError, DateParseError, ValueError)


class _RowContext:
    """Per-row helper that pulls canonical fields through the column mapping."""

    __slots__ = ("row", "mapping", "line", "dataset")

    def __init__(self, row: dict[str, Any], mapping: ColumnMapping, line: int, dataset: str) -> None:
        self.row = row
        self.mapping = mapping
        self.line = line
        self.dataset = dataset

    def raw(self, field: str) -> Any:
        header = self.mapping.header_for(field)
        return self.row.get(header) if header else None

    def issue(self, code: ErrorCode, message: str, field: str, record_id: str | None = None) -> RecordIssue:
        return RecordIssue(
            code=code,
            severity=Severity.ERROR,
            message=message,
            dataset=self.dataset,
            row_number=self.line,
            column=self.mapping.header_for(field) or field,
            raw_value=self.raw(field),
            record_id=record_id,
        )


def _require_id(ctx: _RowContext, field: str) -> str:
    value = normalize_id(ctx.raw(field))
    if not value:
        raise _RowRejected(
            ctx.issue(ErrorCode.MISSING_IDENTIFIER, f"'{field}' is missing or empty.", field)
        )
    return value


class _RowRejected(Exception):
    def __init__(self, issue: RecordIssue) -> None:
        self.issue = issue
        super().__init__(issue.message)


# --------------------------------------------------------------------------
# Record builders -- one per dataset kind.
# --------------------------------------------------------------------------

def _build_order(ctx: _RowContext) -> OrderRecord:
    order_id = _require_id(ctx, "order_id")
    payment_id = _require_id(ctx, "payment_id")
    currency = normalize_currency(ctx.raw("currency"))
    try:
        amount = normalize_amount(ctx.raw("order_amount"), currency)
    except MoneyParseError as exc:
        raise _RowRejected(
            ctx.issue(ErrorCode.INVALID_AMOUNT, f"order_amount: {exc.reason}", "order_amount", order_id)
        ) from exc
    if amount < 0:
        raise _RowRejected(
            ctx.issue(
                ErrorCode.NEGATIVE_AMOUNT,
                "order_amount is negative; an order cannot have negative gross value.",
                "order_amount",
                order_id,
            )
        )
    try:
        order_date = normalize_date(ctx.raw("order_date"))
    except DateParseError as exc:
        raise _RowRejected(
            ctx.issue(ErrorCode.INVALID_DATE, str(exc), "order_date", order_id)
        ) from exc

    return OrderRecord(
        order_id=order_id,
        payment_id=payment_id,
        order_amount=amount,
        currency=currency,
        order_date=order_date,
        status=normalize_text(ctx.raw("status")),
        method=normalize_text(ctx.raw("method")),
        source_row=ctx.line,
    )


def _build_settlement(ctx: _RowContext) -> SettlementRecord:
    settlement_id = _require_id(ctx, "settlement_id")
    payment_id = _require_id(ctx, "payment_id")
    currency = normalize_currency(ctx.raw("currency"))

    def amount(field: str, default: int | None) -> int:
        try:
            return normalize_amount(ctx.raw(field), currency, default=default)
        except MoneyParseError as exc:
            raise _RowRejected(
                ctx.issue(ErrorCode.INVALID_AMOUNT, f"{field}: {exc.reason}", field, settlement_id)
            ) from exc

    settlement_amount = amount("settlement_amount", None)
    gross_raw = ctx.raw("gross_amount")
    gross = amount("gross_amount", 0) if gross_raw is not None else None
    if gross == 0 and not ctx.mapping.has("gross_amount"):
        gross = None

    try:
        settlement_date = normalize_date(ctx.raw("settlement_date"))
    except DateParseError as exc:
        raise _RowRejected(
            ctx.issue(ErrorCode.INVALID_DATE, str(exc), "settlement_date", settlement_id)
        ) from exc

    return SettlementRecord(
        settlement_id=settlement_id,
        payment_id=payment_id,
        settlement_amount=settlement_amount,
        gross_amount=gross,
        # Deduction components are stored as positive magnitudes; some exports
        # emit them negative, so we take the absolute value and let the formula
        # own the sign. Sign conventions belong in one place, not two.
        fee=abs(amount("fee", 0)),
        tax=abs(amount("tax", 0)),
        refund_amount=abs(amount("refund_amount", 0)),
        adjustment=amount("adjustment", 0),
        currency=currency,
        settlement_date=settlement_date,
        utr=normalize_id(ctx.raw("utr")),
        status=normalize_text(ctx.raw("status")),
        source_row=ctx.line,
    )


def _build_bank(ctx: _RowContext) -> BankRecord:
    bank_transaction_id = _require_id(ctx, "bank_transaction_id")
    settlement_id = normalize_id(ctx.raw("settlement_id"))
    utr = normalize_id(ctx.raw("utr"))
    if not settlement_id and not utr:
        raise _RowRejected(
            ctx.issue(
                ErrorCode.MISSING_IDENTIFIER,
                "Bank row has neither a settlement_id nor a UTR, so it cannot be joined.",
                "utr",
                bank_transaction_id,
            )
        )
    currency = normalize_currency(ctx.raw("currency"))
    try:
        credit = normalize_amount(ctx.raw("credit_amount"), currency)
    except MoneyParseError as exc:
        raise _RowRejected(
            ctx.issue(
                ErrorCode.INVALID_AMOUNT, f"credit_amount: {exc.reason}", "credit_amount",
                bank_transaction_id,
            )
        ) from exc
    try:
        transaction_date = normalize_date(ctx.raw("transaction_date"))
    except DateParseError as exc:
        raise _RowRejected(
            ctx.issue(ErrorCode.INVALID_DATE, str(exc), "transaction_date", bank_transaction_id)
        ) from exc

    return BankRecord(
        bank_transaction_id=bank_transaction_id,
        settlement_id=settlement_id,
        utr=utr,
        credit_amount=credit,
        currency=currency,
        transaction_date=transaction_date,
        description=normalize_text(ctx.raw("description")),
        source_row=ctx.line,
    )


_BUILDERS: dict[DatasetKind, Callable[[_RowContext], Any]] = {
    DatasetKind.ORDERS: _build_order,
    DatasetKind.SETTLEMENTS: _build_settlement,
    DatasetKind.BANK: _build_bank,
}

#: Field whose uniqueness defines a duplicate, per dataset.
_PRIMARY_KEY: dict[DatasetKind, str] = {
    DatasetKind.ORDERS: "order_id",
    DatasetKind.SETTLEMENTS: "settlement_id",
    DatasetKind.BANK: "bank_transaction_id",
}


# --------------------------------------------------------------------------
# Loader
# --------------------------------------------------------------------------

def iter_records(
    reader: ChunkReader,
    kind: DatasetKind,
    collector: IssueCollector,
) -> Iterator[list[Any]]:
    """Stream canonical records batch-by-batch.

    Yields one list per source chunk, so a caller can process 100k rows without
    ever materialising the whole file.  ``collector`` accumulates rejections.
    """
    mapping = resolve_columns(kind, reader.headers)
    builder = _BUILDERS[kind]
    key_field = _PRIMARY_KEY[kind]
    seen: set[str] = set()

    for chunk in reader.chunks():
        batch: list[Any] = []
        for index, row in enumerate(chunk.rows):
            ctx = _RowContext(row, mapping, chunk.start_row + index, kind.value)
            try:
                record = builder(ctx)
            except _RowRejected as rejected:
                collector.add(rejected.issue)
                continue
            except _ROW_ERRORS as exc:  # defensive: unexpected shape in one cell
                collector.add(
                    RecordIssue(
                        code=ErrorCode.INVALID_AMOUNT,
                        severity=Severity.ERROR,
                        message=f"Row could not be normalised: {exc}",
                        dataset=kind.value,
                        row_number=ctx.line,
                    )
                )
                continue

            key = getattr(record, key_field)
            if key in seen:
                # Duplicates are reported and skipped: counting a settlement
                # twice would corrupt the totals, which is worse than a gap.
                collector.add(
                    RecordIssue(
                        code=ErrorCode.DUPLICATE_IDENTIFIER,
                        severity=Severity.WARNING,
                        message=f"Duplicate {key_field} '{key}' -- first occurrence kept.",
                        dataset=kind.value,
                        row_number=ctx.line,
                        column=key_field,
                        record_id=key,
                    )
                )
                continue
            seen.add(key)
            batch.append(record)
        if batch:
            yield batch

    _ = mapping  # kept for clarity; mapping is reported by load_dataset


def load_dataset(
    source: Path,
    kind: DatasetKind,
    *,
    chunk_size: int = 10_000,
    compute_checksum: bool = True,
    max_issue_samples: int = 200,
) -> NormalizedDataset:
    """Fully materialise one dataset.

    Used by the MVP engine, which holds the three datasets in memory.  For a
    streaming future, call :func:`iter_records` directly instead -- the record
    shapes are identical.
    """
    reader = reader_for(source, kind, chunk_size)
    collector = IssueCollector(max_samples=max_issue_samples)
    mapping = resolve_columns(kind, reader.headers)

    records: list[Any] = []
    for batch in iter_records(reader, kind, collector):
        records.extend(batch)

    if not records:
        raise ValidationFailure(
            f"No usable rows found in the {kind.value} file "
            f"({collector.total} row(s) rejected).",
            code=ErrorCode.EMPTY_FILE,
            issues=collector.samples[:20],
            context={"kind": kind.value, "issues": collector.to_dict()},
        )

    return NormalizedDataset(
        kind=kind.value,
        records=records,
        row_count=len(records),
        rejected_count=collector.total,
        column_mapping=dict(mapping.mapping),
        issues=collector.to_dict(),
        checksum=checksum_file(source) if compute_checksum else None,
        source_name=source.name,
    )
