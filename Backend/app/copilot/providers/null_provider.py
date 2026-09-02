"""Deterministic, offline Copilot.

Same role as :class:`app.ai.providers.null_provider.NullAIService`: not a
mock, but the default provider. It makes the Copilot demonstrable with no API
key, no network and no cost, and gives the test suite a provider whose answers
are byte-for-byte predictable.

It routes on keywords rather than reasoning, then renders its answer directly
from whatever a real tool call returned -- so, unlike the Gemini provider, its
output cannot help but be grounded: every sentence is built from the same dict
the grounding validator would check it against.
"""

from __future__ import annotations

import re
from typing import Any

from app.copilot.provider_base import ChatMessage, CopilotProvider, ProviderTurn, ToolRunner
from app.copilot.tools import ToolSpec

_ORDER_ID_RE = re.compile(r"\b([A-Za-z]{1,8}-\d{1,12}|[A-Za-z]{1,3}\d{4,12})\b")

_SCOPE_HINTS = (
    "reconcil", "exception", "match", "settle", "payment", "order", "transaction",
    "variance", "audit", "refund", "fee", "tax", "unresolved", "review", "amount",
    "batch", "job", "summary", "categor", "investigat", "unexplained", "difference",
)


def _extract_order_id(text: str) -> str | None:
    match = _ORDER_ID_RE.search(text)
    return match.group(1).upper() if match else None


def _looks_in_scope(lowered: str) -> bool:
    return any(hint in lowered for hint in _SCOPE_HINTS) or bool(_extract_order_id(lowered))


def _fmt(currency: str, amount: float) -> str:
    symbol = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency.upper(), "")
    return f"{symbol}{amount:,.2f}"


def _render_summary(d: dict[str, Any]) -> str:
    if "error" in d:
        return f"I don't have enough verified information in this reconciliation to determine that. ({d['error']})"
    cur = d["currency"]
    lines = [
        "**Summary**",
        f"ReconIQ has processed {d['recordsProcessed']:,} record(s) for this job at a "
        f"{d['matchRatePercent']:.2f}% match rate.",
        "",
        "**What ReconIQ found**",
        f"- Matched: {d['matched']:,}  ·  Exceptions: {d['exceptions']:,}  ·  Unresolved: {d['unresolved']:,}",
        f"- Gross value: {_fmt(cur, d['grossValue'])}  ·  Settled: {_fmt(cur, d['settledValue'])}  ·  "
        f"Variance: {_fmt(cur, d['varianceValue'])}",
        f"- AI analysis status: {d['aiStatus']} ({d['aiAnalysedCount']} exception(s) analysed)",
    ]
    return "\n".join(lines)


def _render_categories(d: dict[str, Any]) -> str:
    if "error" in d:
        return f"I don't have enough verified information in this reconciliation to determine that. ({d['error']})"
    cur = d["currency"]
    bullets = "\n".join(
        f"- {c['label']}: {c['count']:,} record(s), {_fmt(cur, c['amount'])}"
        + (" (auto-explained by the engine)" if c["autoExplainedByEngine"] else "")
        for c in d["categories"]
    )
    return (
        "**Summary**\n"
        f"This job has {d['totalExceptions']:,} exception(s), of which {d['totalUnresolved']:,} are unresolved.\n\n"
        "**What ReconIQ found**\n" + bullets
    )


def _render_variances(d: dict[str, Any]) -> str:
    rows = d.get("variances", [])
    if not rows:
        return "ReconIQ shows no exceptions with an unexplained variance for this job."
    cur_lines = "\n".join(
        f"- `{r['orderId']}` — unexplained {r['unexplained']:,.2f} ({r['exceptionType'] or 'unresolved'}, {r['status']})"
        for r in rows
    )
    return "**What ReconIQ found**\nLargest unexplained variances, largest first:\n" + cur_lines


def _render_review(d: dict[str, Any]) -> str:
    rows = d.get("items", [])
    if not rows:
        return "ReconIQ shows no exceptions currently flagged for human review in this job."
    lines = "\n".join(
        f"- `{r['orderId']}` — unexplained {r['unexplained']:,.2f} ({r['exceptionType']}, AI status: {r['aiStatus']})"
        for r in rows
    )
    return (
        "**What ReconIQ found**\nExceptions requiring human review, largest unexplained amount first:\n"
        + lines
        + "\n\n**Recommended next step**\nStart with the first item above -- it carries the largest unexplained amount."
    )


def _render_audit(d: dict[str, Any]) -> str:
    rows = d.get("events", [])
    if not rows:
        return "ReconIQ's audit trail has no events matching that for this job."
    lines = "\n".join(f"- [{r['at']}] {r['type']}: {r['message']}" for r in rows)
    return "**What ReconIQ found**\nAudit trail (most recent last):\n" + lines


def _render_list(d: dict[str, Any]) -> str:
    rows = d.get("exceptions", [])
    if not rows:
        return "ReconIQ shows no exceptions matching that filter for this job."
    lines = "\n".join(
        f"- `{r['orderId']}` — {r['exceptionType'] or 'unresolved'}, unexplained {r['unexplained']:,.2f}: {r['reason']}"
        for r in rows
    )
    return f"**What ReconIQ found**\n{d['returned']} of {d['totalMatchingFilter']} matching exception(s):\n" + lines


def _render_exception(d: dict[str, Any]) -> str:
    if not d.get("found"):
        return f"I don't have enough verified information in this reconciliation to determine that. {d.get('message', '')}"
    cur = d["currency"]
    ai = d.get("aiAnalysis") or {}
    lines = [
        "**Summary**",
        f"`{d['orderId']}` is currently **{d['status']}**"
        + (f" ({d['exceptionType']})" if d.get("exceptionType") else "") + ".",
        "",
        "**What ReconIQ found**",
        f"- Expected: {_fmt(cur, d['expected'])}  ·  Settled: {_fmt(cur, d['settled'])}  ·  "
        f"Unexplained: {_fmt(cur, d['unexplained'])}",
        f"- Deterministic reason: {d['deterministicReason']}",
        f"- Requires human review: {'yes' if d['requiresHumanReview'] else 'no'}",
    ]
    if ai.get("explanation"):
        lines += ["", "**Interpretation**", ai["explanation"]]
    if ai.get("recommendedAction"):
        lines += ["", "**Recommended next step**", ai["recommendedAction"]]
    return "\n".join(lines)


def _render_transaction(d: dict[str, Any]) -> str:
    if not d.get("found"):
        return f"I don't have enough verified information in this reconciliation to determine that. {d.get('message', '')}"
    cur = d["currency"]
    return (
        "**What ReconIQ found**\n"
        f"`{d['orderId']}` is **{d['status']}**. Expected {_fmt(cur, d['expected'])}, "
        f"settled {_fmt(cur, d['settled'])}. {d['reason']}"
    )


class NullCopilotProvider(CopilotProvider):
    name = "null"

    @property
    def model(self) -> str:
        return "deterministic-copilot-v1"

    def converse(
        self,
        *,
        system_prompt: str,
        history: list[ChatMessage],
        message: str,
        tools: list[ToolSpec],
        tool_runner: ToolRunner,
    ) -> ProviderTurn:
        text = message.strip()
        lowered = text.lower()

        order_id = _extract_order_id(text)
        if order_id:
            exc = tool_runner("get_exception", {"orderId": order_id})
            if exc.ok and exc.data.get("found"):
                return ProviderTurn(answer=_render_exception(exc.data), tool_calls=[exc])
            txn = tool_runner("get_transaction", {"orderId": order_id})
            if txn.ok and txn.data.get("found"):
                return ProviderTurn(answer=_render_transaction(txn.data), tool_calls=[exc, txn])
            return ProviderTurn(
                answer=(
                    "I don't have enough verified information in this reconciliation to determine "
                    f"that. ReconIQ has no record for order '{order_id}' in this job."
                ),
                tool_calls=[exc, txn],
            )

        if any(k in lowered for k in ("largest", "biggest", "top variance", "top exception")):
            result = tool_runner("get_largest_variances", {"limit": 5})
            return ProviderTurn(answer=_render_variances(result.data), tool_calls=[result])

        if any(k in lowered for k in ("human review", "investigate first", "review required", "needs review", "what should i")):
            result = tool_runner("get_human_review_items", {"limit": 10})
            return ProviderTurn(answer=_render_review(result.data), tool_calls=[result])

        if any(k in lowered for k in ("categor", "breakdown", "types of exception", "why are there")):
            result = tool_runner("get_exception_categories", {})
            return ProviderTurn(answer=_render_categories(result.data), tool_calls=[result])

        if "audit" in lowered:
            result = tool_runner("get_audit_events", {"limit": 10})
            return ProviderTurn(answer=_render_audit(result.data), tool_calls=[result])

        if any(k in lowered for k in ("unresolved", "list exception", "show me the exception", "show exceptions")):
            status = "unresolved" if "unresolved" in lowered else None
            result = tool_runner("list_exceptions", {"status": status, "limit": 10})
            return ProviderTurn(answer=_render_list(result.data), tool_calls=[result])

        if not _looks_in_scope(lowered):
            return ProviderTurn(answer="That's outside the data and scope of this reconciliation.", tool_calls=[])

        result = tool_runner("get_reconciliation_summary", {})
        return ProviderTurn(answer=_render_summary(result.data), tool_calls=[result])


__all__ = ["NullCopilotProvider"]
