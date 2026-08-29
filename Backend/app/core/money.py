"""Money primitives.

Every monetary value in this system is an ``int`` count of **minor units**
(paise for INR).  Floats never touch a balance: ``Decimal`` is used only at the
parse boundary, and is quantised to minor units immediately afterwards.

Rationale: reconciliation is an equality test.  ``0.1 + 0.2 != 0.3`` in binary
floating point, which would manufacture phantom exceptions on perfectly good
settlements.  Integers make the equality test exact and make the whole engine
trivially serialisable to JSON for the frontend.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Final

#: Minor units per major unit, keyed by ISO-4217 code. Extend as needed.
MINOR_UNITS: Final[dict[str, int]] = {
    "INR": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "AED": 2,
    "JPY": 0,
}

DEFAULT_CURRENCY: Final[str] = "INR"

#: Currency symbols and stray glyphs that legitimately appear in exported CSVs.
_SYMBOLS: Final[str] = "₹$€£¥\u00a0"
_CLEAN_RE: Final[re.Pattern[str]] = re.compile(rf"[{re.escape(_SYMBOLS)},_'\s]")
_PAREN_NEGATIVE_RE: Final[re.Pattern[str]] = re.compile(r"^\((.*)\)$")
#: "1 234" -- a space between digits is a thousands separator in some locales.
_DIGIT_SPACE_RE: Final[re.Pattern[str]] = re.compile(r"\d[\s ]\d")
#: ",56" at the end -- a comma with 1-2 trailing digits is a decimal comma;
#: a comma with exactly 3 is a thousands separator ("1,000").
_DECIMAL_COMMA_RE: Final[re.Pattern[str]] = re.compile(r",\d{1,2}$")


class MoneyParseError(ValueError):
    """Raised when a cell cannot be interpreted as a monetary amount."""

    def __init__(self, raw: Any, reason: str) -> None:
        self.raw = raw
        self.reason = reason
        super().__init__(f"cannot parse amount {raw!r}: {reason}")


def exponent(currency: str) -> int:
    return MINOR_UNITS.get((currency or DEFAULT_CURRENCY).upper(), 2)


def parse_decimal(raw: Any) -> Decimal:
    """Coerce a spreadsheet cell into a :class:`Decimal`.

    Handles ``"₹1,000"``, ``"1,000"``, ``"1000.00"``, ``"(250.00)"`` (accounting
    negative), ``"1 000,00"`` is *not* handled -- European decimal commas are
    ambiguous against thousands separators, so we reject rather than guess.
    """
    if raw is None:
        raise MoneyParseError(raw, "value is null")
    if isinstance(raw, bool):
        raise MoneyParseError(raw, "boolean is not an amount")
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, float):
        # str() of a float gives the shortest repr that round-trips, which is
        # the closest thing to the author's intent that we can recover.
        return Decimal(str(raw))

    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none", "null", "-", "n/a", "na"}:
        raise MoneyParseError(raw, "value is empty")

    negative = False
    paren = _PAREN_NEGATIVE_RE.match(text)
    if paren:
        negative = True
        text = paren.group(1)

    # Reject European-style notation before cleaning, rather than mangling it.
    # "1 234,56" and "1234,56" mean 1234.56, but stripping separators would
    # turn them into 123456 -- a silent 100x error on a money value. We refuse
    # rather than guess, because either guess is wrong half the time.
    if _DIGIT_SPACE_RE.search(text):
        raise MoneyParseError(raw, "space-separated digit groups -- ambiguous separator")
    if "." not in text and _DECIMAL_COMMA_RE.search(text):
        raise MoneyParseError(raw, "comma used as a decimal separator -- ambiguous")

    text = _CLEAN_RE.sub("", text)
    if text.startswith("+"):
        text = text[1:]
    if text.startswith("-"):
        negative = not negative
        text = text[1:]

    if not text:
        raise MoneyParseError(raw, "value is empty after cleaning")
    if text.count(".") > 1:
        raise MoneyParseError(raw, "multiple decimal points -- ambiguous separator")
    if not re.fullmatch(r"\d*\.?\d*", text):
        raise MoneyParseError(raw, "contains non-numeric characters")

    try:
        value = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - guarded by regex above
        raise MoneyParseError(raw, "not a valid decimal") from exc
    return -value if negative else value


def to_minor(raw: Any, currency: str = DEFAULT_CURRENCY) -> int:
    """Parse ``raw`` and quantise it to integer minor units (banker-safe)."""
    value = parse_decimal(raw)
    scale = Decimal(10) ** exponent(currency)
    quantised = (value * scale).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(quantised)


def to_major(minor: int, currency: str = DEFAULT_CURRENCY) -> Decimal:
    """Inverse of :func:`to_minor`, for display and CSV export only."""
    scale = Decimal(10) ** exponent(currency)
    return (Decimal(minor) / scale).quantize(
        Decimal(1).scaleb(-exponent(currency)), rounding=ROUND_HALF_UP
    )


def format_money(minor: int, currency: str = DEFAULT_CURRENCY) -> str:
    symbol = {"INR": "\u20b9", "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3"}.get(
        currency.upper(), ""
    )
    return f"{symbol}{to_major(minor, currency):,}"
