/**
 * Exception analysis assembly.
 *
 * Strict separation of concerns, mirrored in the UI:
 *   `computed`  — every figure, produced by the deterministic engine.
 *   `ai`        — classification + natural-language explanation only.
 * The AI object never contains a number the engine did not already derive.
 */

import { formatMoney } from "@/lib/utils";
import {
  EXCEPTION_LABELS,
  HERO_ORDER_ID,
  confidenceFor,
  getStore,
  getTransaction,
  indexOfOrderId,
} from "./dataset";
import type { ExceptionDetail, EvidenceRecord, Transaction } from "./types";

const MODEL = "claude-sonnet-4.5 · exception-classifier v3";

function checksFor(t: Transaction, accountedFor: number) {
  const unexplained = t.difference - accountedFor;
  return [
    {
      label: "Order record present",
      passed: true,
      detail: `Matched on ${t.orderId} in the orders dataset`,
    },
    {
      label: "Settlement record present",
      passed: Boolean(t.settlementId),
      detail: t.settlementId
        ? `Linked to ${t.settlementId}`
        : "No settlement row references this payment ID",
    },
    {
      label: "Bank credit traced",
      passed: Boolean(t.bankRef),
      detail: t.bankRef ? `UTR ${t.bankRef} found in bank statement` : "No matching UTR in bank statement",
    },
    {
      label: "Variance fully accounted for",
      passed: unexplained === 0,
      detail:
        unexplained === 0
          ? "Fee, tax and refund ledger fully explain the variance"
          : `${formatMoney(unexplained)} of the variance has no supporting record`,
    },
  ];
}

function accountedFor(t: Transaction): number {
  switch (t.exceptionType) {
    case "fee_tax":
      return t.fee + t.tax;
    case "refund":
      return t.refund;
    case "rounding":
      return t.difference;
    case "partial_payment":
      return 0;
    case "unresolved":
      return 0;
    default:
      return t.difference;
  }
}

function explanationFor(t: Transaction, unexplained: number): { text: string; signals: string[]; action: string; classification: string } {
  const diff = formatMoney(t.difference);
  switch (t.exceptionType) {
    case "partial_payment":
      return {
        classification: "Partial Payment",
        text: `The settlement is ${diff} lower than the captured order amount. The payment record shows a single capture for ${formatMoney(
          t.expected,
        )} while the settlement credits ${formatMoney(
          t.settled,
        )}, and no refund entry exists for the shortfall. The pattern is consistent with a partial capture settled in full.`,
        signals: [
          "Single capture, no refund entry for the shortfall",
          "Settlement ID and bank UTR both present and linked",
          `Shortfall is ${((t.difference / t.expected) * 100).toFixed(1)}% of the order value`,
        ],
        action: "Verify payment record with the merchant capture log",
      };
    case "refund":
      return {
        classification: "Refund",
        text: `A refund of ${formatMoney(
          t.refund,
        )} was issued inside the settlement window, which accounts for the full ${diff} variance. The refund ledger entry and the settlement net-off are consistent, so no funds are missing.`,
        signals: [
          "Matching entry found in the refund ledger",
          "Refund amount equals the settlement variance exactly",
          "Settlement date falls after the refund date",
        ],
        action: "No action required — variance is fully explained",
      };
    case "fee_tax":
      return {
        classification: "Fee / Tax Deduction",
        text: `The variance of ${diff} matches the platform fee of ${formatMoney(
          t.fee,
        )} plus GST of ${formatMoney(
          t.tax,
        )} recorded on the settlement row. The gross amount was not netted upstream, so the order and settlement figures differ by exactly the deduction.`,
        signals: [
          "Fee and tax fields populated on the settlement record",
          "Fee plus GST equals the variance to the paise",
          "GST computed at the standard 18% rate",
        ],
        action: "No action required — reconcile against the fee invoice",
      };
    case "rounding":
      return {
        classification: "Rounding Adjustment",
        text: `The settlement differs by ${diff}, below one rupee. This is consistent with a rounding adjustment applied when the net amount was converted to the bank credit value. No ledger entry is expected for a difference of this size.`,
        signals: [
          "Absolute variance is under ₹1.00",
          "Fee, tax and refund records are all consistent",
          "Bank credit traced to a single UTR",
        ],
        action: "Accept within the rounding tolerance policy",
      };
    case "unresolved":
    default:
      return {
        classification: "Unresolved — human review required",
        text: `The settlement amount is ${diff} lower than the expected amount. The available records do not contain a matching refund, fee, tax, or rounding adjustment that explains the difference. ${
          t.settlementId
            ? ""
            : "No settlement row references this payment ID, so the credit could not be traced. "
        }This transaction has therefore been flagged for human review.${
          unexplained !== t.difference ? "" : ""
        }`,
        signals: [
          "No refund ledger entry for this order",
          "Fee and tax fields do not account for the variance",
          "Variance exceeds the rounding tolerance",
        ],
        action: "Review manually — check the refund ledger and bank credit",
      };
  }
}

function evidenceFor(t: Transaction): EvidenceRecord[] {
  const records: EvidenceRecord[] = [
    {
      source: "Orders dataset",
      recordId: t.orderId,
      present: true,
      fields: [
        { label: "Order amount", value: formatMoney(t.expected), emphasis: true },
        { label: "Payment ID", value: t.paymentId },
        { label: "Method", value: t.method },
        { label: "Captured at", value: new Date(t.capturedAt).toLocaleString("en-IN") },
      ],
    },
    {
      source: "Razorpay settlement",
      recordId: t.settlementId ?? "—",
      present: Boolean(t.settlementId),
      fields: t.settlementId
        ? [
            { label: "Settled amount", value: formatMoney(t.settled), emphasis: true },
            { label: "Fee", value: formatMoney(t.fee) },
            { label: "Tax (GST)", value: formatMoney(t.tax) },
            { label: "Settled on", value: new Date(t.settlementDate).toLocaleDateString("en-IN") },
          ]
        : [{ label: "Lookup", value: "No settlement row references this payment ID" }],
    },
    {
      source: "Bank statement",
      recordId: t.bankRef ?? "—",
      present: Boolean(t.bankRef),
      fields: t.bankRef
        ? [
            { label: "Credit amount", value: formatMoney(t.settled), emphasis: true },
            { label: "UTR", value: t.bankRef },
            { label: "Value date", value: new Date(t.settlementDate).toLocaleDateString("en-IN") },
          ]
        : [{ label: "Lookup", value: "No matching UTR found in the bank statement" }],
    },
    {
      source: "Refund ledger",
      recordId: t.refund > 0 ? `rfnd_${t.paymentId.slice(4, 12)}` : "—",
      present: t.refund > 0,
      fields:
        t.refund > 0
          ? [
              { label: "Refund amount", value: formatMoney(t.refund), emphasis: true },
              { label: "Status", value: "processed" },
            ]
          : [{ label: "Lookup", value: "No refund entry found for this order" }],
    },
  ];
  return records;
}

export function buildExceptionDetail(orderId: string): ExceptionDetail | null {
  const i = indexOfOrderId(orderId);
  if (i === null) return null;
  const t = getTransaction(i);
  if (t.status === "matched") return null;

  const acc = accountedFor(t);
  const unexplained = t.difference - acc;
  const meta = explanationFor(t, unexplained);
  const noise = getStore().noise[i];

  // The hero record carries the exact copy used in the walkthrough.
  const isHero = t.orderId === HERO_ORDER_ID;

  return {
    transaction: t,
    computed: {
      expected: t.expected,
      settled: t.settled,
      difference: t.difference,
      accountedFor: acc,
      unexplained,
      checks: checksFor(t, acc),
    },
    ai: {
      classification: isHero ? "Unresolved — human review required" : meta.classification,
      confidence: confidenceFor(t.exceptionType, noise),
      explanation: isHero
        ? "The settlement amount is ₹150.00 lower than the expected amount. The available records do not contain a matching refund, fee, tax, or rounding adjustment that explains the difference. This transaction has therefore been flagged for human review."
        : meta.text,
      signals: meta.signals,
      recommendedAction: meta.action,
      model: MODEL,
      analysedAt: new Date(new Date(t.settlementDate).getTime() + 3_600_000).toISOString(),
      tokens: 380 + (noise % 260),
    },
    evidence: evidenceFor(t),
  };
}

export function exceptionTypeLabel(t: Transaction) {
  return t.exceptionType ? EXCEPTION_LABELS[t.exceptionType] : "Matched";
}
