"""Value-level normalisation.

Turns whatever a CSV cell contains into a reliable Python value, or reports why
it could not.  Deterministic and dependency-light on purpose -- the LLM is
never involved in normalisation.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Final

from app.core.money import DEFAULT_CURRENCY, MINOR_UNITS, MoneyParseError, to_minor

_NULLS: Final[frozenset[str]] = frozenset(
    {"", "nan", "none", "null", "n/a", "na", "-", "--", "nil", "<na>", "nat"}
)

_ID_CLEAN_RE: Final[re.Pattern[str]] = re.compile(r"[\s ]+")

#: Tried in order.  ISO first because that is what well-behaved exports emit.
_DATE_FORMATS: Final[tuple[str, ...]] = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%b %d, %Y",
    "%Y/%m/%d",
)


class DateParseError(ValueError):
    def __init__(self, raw: Any) -> None:
        self.raw = raw
        super().__init__(f"cannot parse date {raw!r}: no known format matched")


def is_null(raw: Any) -> bool:
    """True for the many spellings of 'nothing here'."""
    if raw is None:
        return True
    # NaN is the only value not equal to itself; catches numpy/pandas NaN too.
    if isinstance(raw, float) and raw != raw:
        return True
    return str(raw).strip().lower() in _NULLS


def normalize_id(raw: Any) -> str | None:
    """Trim, collapse internal whitespace, and drop a trailing float artefact.

    Pandas will happily read an all-numeric ID column as float64 and hand back
    ``123456.0``.  Left alone, that silently fails to join against ``"123456"``
    from another file -- the single most common cause of a false 'unresolved'.
    """
    if is_null(raw):
        return None
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    text = _ID_CLEAN_RE.sub(" ", str(raw).strip())
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def normalize_currency(raw: Any, default: str = DEFAULT_CURRENCY) -> str:
    if is_null(raw):
        return default
    code = str(raw).strip().upper()
    symbol_map = {"₹": "INR", "RS": "INR", "RS.": "INR", "$": "USD", "€": "EUR", "£": "GBP"}
    code = symbol_map.get(code, code)
    return code if code in MINOR_UNITS else default


def normalize_amount(raw: Any, currency: str = DEFAULT_CURRENCY, *, default: int | None = None) -> int:
    """Parse an amount to integer minor units.

    ``default`` is used when the cell is empty -- appropriate for optional
    components such as ``fee`` where blank genuinely means zero.  When
    ``default`` is ``None`` an empty cell is an error.
    """
    if is_null(raw):
        if default is None:
            raise MoneyParseError(raw, "required amount is empty")
        return default
    return to_minor(raw, currency)


def normalize_date(raw: Any) -> datetime | None:
    """Parse a timestamp into a naive UTC-normalised ``datetime``.

    Returns ``None`` for genuinely empty cells; raises for cells that hold
    something we cannot interpret, so the caller can report the bad row rather
    than pretend the date was absent.
    """
    if is_null(raw):
        return None
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc).replace(tzinfo=None) if raw.tzinfo else raw
    # pandas.Timestamp and date both expose to_pydatetime()/isoformat().
    to_py = getattr(raw, "to_pydatetime", None)
    if callable(to_py):
        value = to_py()
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1]
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise DateParseError(raw)


def normalize_text(raw: Any, *, max_length: int = 512) -> str | None:
    if is_null(raw):
        return None
    return str(raw).strip()[:max_length] or None
