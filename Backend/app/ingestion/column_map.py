"""Flexible column resolution.

Real exports never agree on header names.  ``Order ID``, ``order_id``,
``orderId`` and ``ORDER_NO`` all mean the same thing.  Rather than hard-coding
one spelling, each canonical field declares a set of aliases; headers are
slugified and matched against them.

Nothing here guesses semantically: a header either matches a declared alias or
it does not.  If a *required* field has no match we raise with the list of
headers we actually saw, so the operator can fix the file or add an alias.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.enums import DatasetKind
from app.core.errors import ErrorCode, RecordIssue, Severity, ValidationFailure

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(header: str) -> str:
    """``"Settlement Amount (INR)"`` -> ``"settlement_amount_inr"``."""
    return _SLUG_RE.sub("_", str(header).strip().lower()).strip("_")


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    aliases: tuple[str, ...]
    required: bool = False
    description: str = ""

    def matches(self, slug: str) -> bool:
        return slug == self.name or slug in self.aliases


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    kind: DatasetKind
    fields: tuple[FieldSpec, ...]
    #: Groups where at least one member must be present, e.g. a bank row must
    #: carry either a settlement_id or a utr to be joinable.
    one_of: tuple[tuple[str, ...], ...] = ()

    @property
    def by_name(self) -> dict[str, FieldSpec]:
        return {f.name: f for f in self.fields}


ORDERS_SPEC = DatasetSpec(
    kind=DatasetKind.ORDERS,
    fields=(
        FieldSpec(
            "order_id",
            ("order", "order_no", "order_number", "merchant_order_id", "orderid",
             "order_ref", "receipt"),
            required=True,
            description="Merchant order identifier",
        ),
        FieldSpec(
            "payment_id",
            ("payment", "payment_ref", "razorpay_payment_id", "paymentid", "txn_id",
             "transaction_id", "pg_payment_id"),
            required=True,
            description="Payment gateway transaction identifier",
        ),
        FieldSpec(
            "order_amount",
            ("amount", "order_value", "gross_amount", "total_amount", "amount_inr",
             "order_amount_inr", "value"),
            required=True,
            description="Gross order value",
        ),
        FieldSpec("currency", ("ccy", "currency_code", "order_currency")),
        FieldSpec(
            "order_date",
            ("created_at", "order_created_at", "date", "captured_at", "order_datetime",
             "timestamp"),
        ),
        FieldSpec("status", ("order_status", "payment_status", "state")),
        FieldSpec("method", ("payment_method", "mode", "channel", "instrument")),
    ),
)

SETTLEMENTS_SPEC = DatasetSpec(
    kind=DatasetKind.SETTLEMENTS,
    fields=(
        FieldSpec(
            "settlement_id",
            ("settlement", "settlement_ref", "razorpay_settlement_id", "settlementid",
             "payout_id", "settlement_no"),
            required=True,
        ),
        FieldSpec(
            "payment_id",
            ("payment", "payment_ref", "razorpay_payment_id", "paymentid", "txn_id",
             "transaction_id", "pg_payment_id"),
            required=True,
        ),
        FieldSpec(
            "settlement_amount",
            ("net_amount", "settled_amount", "amount", "net_settlement", "payout_amount",
             "credit_amount"),
            required=True,
        ),
        FieldSpec(
            "gross_amount",
            ("gross", "captured_amount", "transaction_amount", "gross_settlement",
             "order_amount"),
        ),
        FieldSpec(
            "fee",
            ("fees", "commission", "mdr", "razorpay_fee", "processing_fee", "charge", "charges"),
        ),
        FieldSpec("tax", ("gst", "tax_amount", "service_tax", "fee_tax", "gst_amount")),
        FieldSpec("refund_amount", ("refund", "refunds", "refunded_amount", "reversal_amount")),
        FieldSpec(
            "adjustment",
            ("adjustments", "other_adjustments", "dispute_adjustment", "manual_adjustment"),
        ),
        FieldSpec("currency", ("ccy", "currency_code")),
        FieldSpec(
            "settlement_date",
            ("settled_at", "date", "settlement_datetime", "payout_date", "created_at",
             "timestamp"),
        ),
        FieldSpec("utr", ("bank_utr", "reference_number", "rrn", "bank_reference", "utr_number")),
        FieldSpec("status", ("settlement_status", "state")),
    ),
)

BANK_SPEC = DatasetSpec(
    kind=DatasetKind.BANK,
    fields=(
        FieldSpec(
            "bank_transaction_id",
            ("bank_txn_id", "transaction_id", "txn_id", "statement_id", "bank_ref_id",
             "id", "entry_id"),
            required=True,
        ),
        FieldSpec("settlement_id", ("settlement", "settlement_ref", "payout_id", "settlementid")),
        FieldSpec(
            "utr",
            ("bank_utr", "reference_number", "rrn", "bank_reference", "utr_number", "ref_no",
             "cheque_ref_no"),
        ),
        FieldSpec(
            "credit_amount",
            ("credit", "amount", "deposit", "credit_amt", "cr_amount", "amount_credited"),
        ),
        FieldSpec("currency", ("ccy", "currency_code")),
        FieldSpec(
            "transaction_date",
            ("value_date", "date", "posted_at", "txn_date", "transaction_datetime", "timestamp"),
        ),
        FieldSpec("description", ("narration", "particulars", "remarks", "details", "memo")),
    ),
    one_of=(("settlement_id", "utr"),),
)

SPECS: dict[DatasetKind, DatasetSpec] = {
    DatasetKind.ORDERS: ORDERS_SPEC,
    DatasetKind.SETTLEMENTS: SETTLEMENTS_SPEC,
    DatasetKind.BANK: BANK_SPEC,
}

#: Fields that are required but get a clearer error than "missing column" --
#: e.g. a statement that uses debit/credit column pairs.
_ALSO_REQUIRED: dict[DatasetKind, tuple[str, ...]] = {
    DatasetKind.BANK: ("credit_amount",),
}


@dataclass(slots=True)
class ColumnMapping:
    """Resolved canonical-field -> actual-header map for one file."""

    kind: DatasetKind
    mapping: dict[str, str] = field(default_factory=dict)
    unmapped_headers: list[str] = field(default_factory=list)

    def header_for(self, field_name: str) -> str | None:
        return self.mapping.get(field_name)

    def has(self, field_name: str) -> bool:
        return field_name in self.mapping


def resolve_columns(kind: DatasetKind, headers: list[str]) -> ColumnMapping:
    """Map a file's headers onto the canonical field names for ``kind``.

    Raises :class:`ValidationFailure` listing *every* problem at once -- an
    operator fixing a CSV should not have to re-upload six times to discover
    six missing columns.
    """
    spec = SPECS[kind]
    slugs: dict[str, str] = {}
    for header in headers:
        slugs.setdefault(slugify(header), header)

    mapping: dict[str, str] = {}
    claimed: set[str] = set()
    issues: list[RecordIssue] = []

    for fs in spec.fields:
        hits = [slug for slug in slugs if fs.matches(slug) and slug not in claimed]
        if not hits:
            continue
        if len(hits) > 1:
            exact = [h for h in hits if h == fs.name]
            if exact:
                hits = exact
            else:
                names = ", ".join(slugs[h] for h in hits)
                issues.append(
                    RecordIssue(
                        code=ErrorCode.AMBIGUOUS_COLUMN,
                        severity=Severity.ERROR,
                        message=f"'{fs.name}' matches multiple columns: {names}. Rename one.",
                        dataset=kind.value,
                        column=fs.name,
                    )
                )
                continue
        claimed.add(hits[0])
        mapping[fs.name] = slugs[hits[0]]

    missing = [f.name for f in spec.fields if f.required and f.name not in mapping]
    missing += [f for f in _ALSO_REQUIRED.get(kind, ()) if f not in mapping]
    by_name = spec.by_name
    for name in missing:
        fs = by_name.get(name)
        aliases = ", ".join(fs.aliases[:5]) if fs else ""
        issues.append(
            RecordIssue(
                code=ErrorCode.MISSING_REQUIRED_COLUMNS,
                severity=Severity.ERROR,
                message=(
                    f"Required column '{name}' not found in the {kind.value} file. "
                    f"Accepted aliases: {name}, {aliases}."
                ),
                dataset=kind.value,
                column=name,
            )
        )

    for group in spec.one_of:
        if not any(g in mapping for g in group):
            issues.append(
                RecordIssue(
                    code=ErrorCode.MISSING_REQUIRED_COLUMNS,
                    severity=Severity.ERROR,
                    message=(
                        f"The {kind.value} file must contain at least one of: "
                        f"{', '.join(group)} -- otherwise its rows cannot be joined."
                    ),
                    dataset=kind.value,
                )
            )

    if issues:
        raise ValidationFailure(
            f"The {kind.value} file failed column validation.",
            code=ErrorCode.MISSING_REQUIRED_COLUMNS,
            issues=issues,
            context={"kind": kind.value, "headersSeen": [str(h) for h in headers][:60]},
        )

    return ColumnMapping(
        kind=kind,
        mapping=mapping,
        unmapped_headers=[slugs[s] for s in slugs if s not in claimed],
    )
