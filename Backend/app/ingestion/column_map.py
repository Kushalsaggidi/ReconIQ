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


#: Shared across every spec that carries a payment-gateway identifier, so the
#: three copies can never drift apart.
PAYMENT_ID_ALIASES: tuple[str, ...] = (
    "payment", "payment_ref", "payment_reference", "razorpay_payment_id",
    "paymentid", "txn_id", "transaction_id", "pg_payment_id", "pg_txn_id",
    "internal_payment_id", "gateway_payment_id", "gateway_transaction_id",
)

#: Shared across Orders and Settlements -- a processor may settle by merchant
#: order reference instead of (or as well as) a payment id.
ORDER_ID_ALIASES: tuple[str, ...] = (
    "order", "order_no", "order_number", "merchant_order_id", "orderid",
    "order_ref", "receipt", "razorpay_order_id", "customer_order_id",
    "merchant_order_number",
)

#: Shared UTR aliases -- the reference both settlements and bank statements
#: use to join without a shared settlement id. Includes batch-style
#: references (`settlement_batch_id`) some processors use in place of a
#: per-transaction UTR: several settlement rows legitimately share one batch
#: reference, exactly like several settlements can share one UTR.
#:
#: Deliberately excludes generic terms like "bank_reference" -- a bank
#: statement can carry its *own* internal reference column alongside the true
#: cross-file join key (as `bank_settlements.csv` does: `bank_reference` is
#: descriptive, `settlement_batch_id` is what actually joins back to
#: settlements). Aliasing both to the same canonical field would collide.
UTR_ALIASES: tuple[str, ...] = (
    "bank_utr", "reference_number", "reference_no", "rrn",
    "utr_number", "utr_no", "unique_transaction_reference", "utr_reference",
    "settlement_utr", "settlement_batch_id", "batch_id", "payout_batch_id",
)

CURRENCY_ALIASES: tuple[str, ...] = ("ccy", "currency_code", "order_currency", "txn_currency")

ORDERS_SPEC = DatasetSpec(
    kind=DatasetKind.ORDERS,
    fields=(
        FieldSpec(
            "order_id",
            ORDER_ID_ALIASES,
            required=True,
            description="Merchant order identifier",
        ),
        FieldSpec(
            "payment_id",
            PAYMENT_ID_ALIASES,
            required=True,
            description="Payment gateway transaction identifier",
        ),
        FieldSpec(
            "order_amount",
            ("amount", "order_value", "gross_amount", "total_amount", "amount_inr",
             "order_amount_inr", "value", "transaction_amount", "order_total",
             "amount_paid", "paid_amount"),
            required=True,
            description="Gross order value",
        ),
        FieldSpec("currency", CURRENCY_ALIASES),
        FieldSpec(
            "order_date",
            ("created_at", "order_created_at", "date", "captured_at", "order_datetime",
             "timestamp", "occurred_at", "order_placed_at", "payment_date",
             "transaction_date"),
        ),
        FieldSpec("status", ("order_status", "payment_status", "state", "txn_status")),
        FieldSpec("method", ("payment_method", "mode", "channel", "instrument")),
    ),
)

SETTLEMENTS_SPEC = DatasetSpec(
    kind=DatasetKind.SETTLEMENTS,
    fields=(
        FieldSpec(
            "settlement_id",
            ("settlement", "settlement_ref", "razorpay_settlement_id", "settlementid",
             "payout_id", "settlement_no", "settlement_reference", "processor_transaction_id",
             "processor_reference", "payout_reference"),
            required=True,
        ),
        FieldSpec(
            "payment_id",
            PAYMENT_ID_ALIASES,
            description="Payment gateway transaction identifier -- some "
                         "processors settle by order reference instead; see "
                         "`order_id` below and the one_of group.",
        ),
        FieldSpec(
            "order_id",
            ORDER_ID_ALIASES,
            description="Merchant order reference -- an alternate join key to "
                         "Orders when a processor's settlement export carries "
                         "no payment id at all.",
        ),
        FieldSpec(
            "settlement_amount",
            ("net_amount", "settled_amount", "amount", "net_settlement", "payout_amount",
             "credit_amount", "net_settlement_amount", "amount_settled"),
            required=True,
        ),
        FieldSpec(
            "gross_amount",
            ("gross", "captured_amount", "transaction_amount", "gross_settlement",
             "order_amount", "order_gross_amount"),
        ),
        FieldSpec(
            "fee",
            ("fees", "commission", "mdr", "razorpay_fee", "processing_fee", "charge",
             "charges", "processing_charges", "convenience_fee", "fee_amount"),
        ),
        FieldSpec("tax", ("gst", "tax_amount", "service_tax", "fee_tax", "gst_amount", "gst_tax")),
        FieldSpec("refund_amount", ("refund", "refunds", "refunded_amount", "reversal_amount")),
        FieldSpec(
            "adjustment",
            ("adjustments", "other_adjustments", "dispute_adjustment", "manual_adjustment"),
        ),
        FieldSpec("currency", CURRENCY_ALIASES),
        FieldSpec(
            "settlement_date",
            ("settled_at", "date", "settlement_datetime", "payout_date", "created_at",
             "timestamp", "settlement_created_at", "processor_event_time"),
        ),
        FieldSpec("utr", UTR_ALIASES),
        FieldSpec("status", ("settlement_status", "state", "processor_status")),
    ),
    # A settlement must be joinable to an order by *something* -- either the
    # payment id or the merchant order reference. Some processors' exports
    # carry only one of the two.
    one_of=(("payment_id", "order_id"),),
)

BANK_SPEC = DatasetSpec(
    kind=DatasetKind.BANK,
    fields=(
        FieldSpec(
            "bank_transaction_id",
            ("bank_txn_id", "transaction_id", "txn_id", "statement_id", "bank_ref_id",
             "id", "entry_id", "bank_reference_id", "bank_entry_id"),
            required=True,
        ),
        FieldSpec("settlement_id", ("settlement", "settlement_ref", "payout_id", "settlementid")),
        FieldSpec("utr", UTR_ALIASES + ("cheque_ref_no",)),
        FieldSpec(
            "credit_amount",
            ("credit", "amount", "deposit", "credit_amt", "cr_amount", "amount_credited",
             "credited_amount"),
        ),
        FieldSpec(
            "debit_amount",
            ("debit", "dr_amount", "withdrawal", "amount_debited", "debit_amt"),
            description="Outgoing amount -- not used in reconciliation, kept for evidence",
        ),
        FieldSpec(
            "balance",
            ("closing_balance", "running_balance", "available_balance", "balance_after",
             "balance_amount"),
            description="Running account balance -- informational only",
        ),
        FieldSpec("currency", CURRENCY_ALIASES),
        FieldSpec(
            "transaction_date",
            ("value_date", "date", "posted_at", "txn_date", "transaction_datetime", "timestamp",
             "booked_at"),
        ),
        FieldSpec("description", ("narration", "particulars", "remarks", "remark", "details", "memo")),
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


@dataclass(frozen=True, slots=True)
class DatasetTypeDetection:
    """Which of the three dataset kinds a file's headers most resemble.

    Used only as a *cross-check* against the kind the operator explicitly
    selected on upload -- it never chooses the kind on its own. ``confidence``
    is in [0, 1]; ``ambiguous`` means the top two kinds scored too close to
    trust the ranking.
    """

    best: DatasetKind
    confidence: float
    scores: dict[DatasetKind, float]
    ambiguous: bool


#: Bare, single-word vocabulary that says almost nothing about dataset type on
#: its own -- every one of these appears verbatim in real exports of all three
#: kinds ("amount", "date", "status" ...). A header that matches a field only
#: through one of these generic slugs earns a fraction of that field's normal
#: weight; the same header matched through a specific, compound alias (e.g.
#: "settlement_amount", "gross_amount", "payment_status") earns full weight.
#: This is what stops "order_id + payment_id + amount" -- a shape settlements
#: legitimately share with orders, since a settlement is naturally linked to
#: an order/payment -- from being read as strong evidence for Orders.
_GENERIC_SLUGS: frozenset[str] = frozenset(
    {"amount", "date", "status", "state", "currency", "value", "id",
     "reference", "ref", "description", "details", "remarks"}
)

#: A required field is one of the *strong* signals for its kind -- without it
#: the file cannot even be parsed as that kind. An optional field is
#: *supporting* evidence: useful, but not on its own decisive.
_STRONG_WEIGHT = 3.0
_SUPPORTING_WEIGHT = 1.5
#: How much a generic-slug match is discounted relative to a specific one.
_GENERIC_DISCOUNT = 0.15


def _spec_score(spec: DatasetSpec, slugs: set[str]) -> float:
    """Weighted, normalised [0, 1] resemblance of ``slugs`` to ``spec``.

    Each field contributes at most its own base weight (strong if required,
    supporting otherwise), scaled down when the *only* evidence for it is a
    bare, shared word rather than a specific, kind-appropriate name. A file
    only scores highly here by matching several *specific* fields, not by
    reusing a handful of generic ones -- which is what lets a settlements file
    that happens to carry an `order_id` foreign key still lose decisively to
    Orders on that field alone.
    """
    matched = 0.0
    possible = 0.0
    for fs in spec.fields:
        base = _STRONG_WEIGHT if fs.required else _SUPPORTING_WEIGHT
        possible += base
        best = 0.0
        for slug in slugs:
            if not fs.matches(slug):
                continue
            weight = base * _GENERIC_DISCOUNT if slug in _GENERIC_SLUGS else base
            if weight > best:
                best = weight
        matched += best
    return matched / possible if possible else 0.0


def detect_dataset_kind(headers: list[str]) -> DatasetTypeDetection:
    """Score a file's headers against every known dataset shape.

    Pure header evidence, no fuzzy string matching and no row sampling -- the
    same alias table :func:`resolve_columns` uses, so "detected as orders"
    and "resolves as orders" can never disagree. Scoring is relative: a kind
    wins by having more *specific* matching fields than its rivals, not by
    hitting an arbitrary threshold, so genuinely overlapping schemas (a
    settlement file naturally carrying `order_id`/`payment_id`) are resolved
    by which kind's *distinguishing* fields (settlement_id, utr, fee, tax vs.
    order_date, payment_status, payment_method) actually showed up.
    """
    slugs = {slugify(h) for h in headers}
    scores = {kind: _spec_score(spec, slugs) for kind, spec in SPECS.items()}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_kind, best_score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0
    ambiguous = best_score > 0 and (best_score - runner_up_score) < 0.15
    return DatasetTypeDetection(
        best=best_kind, confidence=best_score, scores=scores, ambiguous=ambiguous
    )


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
