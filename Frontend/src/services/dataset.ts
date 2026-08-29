/**
 * Virtual 100,000-record settlement batch.
 *
 * The batch is held as a handful of typed arrays (~1 MB) rather than 100,000
 * objects, and a full `Transaction` is materialised only for the rows a page
 * actually renders. That keeps filtering/sorting over the whole batch honest
 * while never handing React more than `pageSize` objects.
 */

import { mulberry32 } from "@/lib/utils";
import type {
  Confidence,
  ExceptionType,
  Transaction,
  TxnStatus,
  TrendPoint,
} from "./types";

export const TOTAL_RECORDS = 100_000;

/** Fixed, internally consistent demo figures. Sum of buckets === exceptions. */
export const BUCKET_COUNTS: Record<Exclude<ExceptionType, never>, number> = {
  partial_payment: 1_020,
  refund: 640,
  fee_tax: 510,
  rounding: 320,
  unresolved: 270,
};

export const EXCEPTION_COUNT = Object.values(BUCKET_COUNTS).reduce((a, b) => a + b, 0); // 2,760
export const MATCHED_COUNT = TOTAL_RECORDS - EXCEPTION_COUNT; // 97,240
export const MATCH_RATE = (MATCHED_COUNT / TOTAL_RECORDS) * 100; // 97.24

export const CAT_ORDER: ExceptionType[] = [
  "partial_payment",
  "refund",
  "fee_tax",
  "rounding",
  "unresolved",
];

export const EXCEPTION_LABELS: Record<ExceptionType, string> = {
  partial_payment: "Partial Payment",
  refund: "Refund",
  fee_tax: "Fee / Tax",
  rounding: "Rounding",
  unresolved: "Unresolved",
};

/** Explained buckets get one hue; the unexplained bucket wears the status color. */
export const EXCEPTION_TONE: Record<ExceptionType, "explained" | "unexplained"> = {
  partial_payment: "explained",
  refund: "explained",
  fee_tax: "explained",
  rounding: "explained",
  unresolved: "unexplained",
};

const METHODS: Transaction["method"][] = ["UPI", "Card", "Netbanking", "Wallet"];

/** cat: 0 = matched, 1..5 = index into CAT_ORDER + 1 */
interface Store {
  cat: Uint8Array;
  expected: Int32Array;
  difference: Int32Array;
  day: Uint8Array;
  noise: Uint16Array;
}

/** Batch settlement window: the 14 days ending on the batch date. */
export const BATCH_DATE = new Date("2026-08-28T00:00:00+05:30");
const DAY_MS = 86_400_000;

export function dayToDate(day: number) {
  return new Date(BATCH_DATE.getTime() - (13 - day) * DAY_MS);
}

let store: Store | null = null;

function build(): Store {
  const rand = mulberry32(0x5e77);
  const cat = new Uint8Array(TOTAL_RECORDS);
  const expected = new Int32Array(TOTAL_RECORDS);
  const difference = new Int32Array(TOTAL_RECORDS);
  const day = new Uint8Array(TOTAL_RECORDS);
  const noise = new Uint16Array(TOTAL_RECORDS);

  // 1. lay the exception categories down, then shuffle deterministically so
  //    exceptions are scattered through the batch the way real ones are.
  let cursor = 0;
  CAT_ORDER.forEach((type, i) => {
    for (let k = 0; k < BUCKET_COUNTS[type]; k++) cat[cursor++] = i + 1;
  });
  for (let i = TOTAL_RECORDS - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    const t = cat[i];
    cat[i] = cat[j];
    cat[j] = t;
  }

  // 2. amounts + variance per category (all integers, in paise)
  for (let i = 0; i < TOTAL_RECORDS; i++) {
    const gross = Math.round((249 + rand() * 24_750) * 100);
    expected[i] = gross;
    day[i] = Math.min(13, Math.floor(rand() * 14));
    noise[i] = Math.floor(rand() * 65_535);

    switch (cat[i]) {
      case 1: // partial payment — a meaningful slice missing
        difference[i] = Math.round(gross * (0.08 + rand() * 0.37));
        break;
      case 2: // refund — a whole or part refund landed inside the window
        difference[i] = Math.round(gross * (rand() < 0.45 ? 1 : 0.2 + rand() * 0.5));
        break;
      case 3: // fee / tax — platform fee + 18% GST not netted upstream
        difference[i] = Math.round(gross * (0.0177 + rand() * 0.006) * 1.18);
        break;
      case 4: // rounding — sub-rupee drift
        difference[i] = 1 + Math.floor(rand() * 99);
        break;
      case 5: // unresolved — nothing in the records accounts for it
        // Capped against the order value so a settlement never goes negative.
        difference[i] = Math.min(
          Math.round((50 + rand() * 900) * 100),
          Math.round(gross * 0.62),
        );
        break;
      default:
        difference[i] = 0;
    }
  }

  // 3. the scripted hero exception the demo walks a judge through.
  //    Swap categories so the bucket totals stay exact.
  const heroIndex = HERO_INDEX;
  if (cat[heroIndex] !== 5) {
    let donor = -1;
    for (let i = TOTAL_RECORDS - 1; i >= 0; i--) {
      if (cat[i] === 5) {
        donor = i;
        break;
      }
    }
    if (donor >= 0) {
      cat[donor] = cat[heroIndex];
      cat[heroIndex] = 5;
      // keep the donor's variance plausible for its new category
      difference[donor] = Math.round(expected[donor] * 0.14);
    }
  }
  expected[heroIndex] = 200_000; // ₹2,000.00
  difference[heroIndex] = 15_000; // ₹150.00 short
  day[heroIndex] = 12;

  return { cat, expected, difference, day, noise };
}

/** O-10482 — the deliberately unresolved record used in the walkthrough. */
export const HERO_INDEX = 482;
export const HERO_ORDER_ID = `O-${10_000 + HERO_INDEX}`;

export function getStore(): Store {
  if (!store) store = build();
  return store;
}

export function indexOfOrderId(orderId: string): number | null {
  const m = /^O-?(\d{5})$/i.exec(orderId.trim());
  if (!m) return null;
  const i = Number(m[1]) - 10_000;
  return i >= 0 && i < TOTAL_RECORDS ? i : null;
}

function pad(n: number, len: number) {
  return String(n).padStart(len, "0");
}

const REASONS: Record<ExceptionType, string> = {
  partial_payment: "Settled amount below captured amount",
  refund: "Refund issued within settlement window",
  fee_tax: "Platform fee and GST deducted at settlement",
  rounding: "Sub-rupee rounding difference",
  unresolved: "Variance not explained by available records",
};

export function confidenceFor(type: ExceptionType | null, noise: number): Confidence {
  if (!type) return "high";
  if (type === "unresolved") return "low";
  if (type === "rounding") return noise % 5 === 0 ? "medium" : "high";
  if (type === "partial_payment") return noise % 7 === 0 ? "medium" : "high";
  return "high";
}

/** Materialise one row. Cheap enough to call per visible cell-row. */
export function getTransaction(i: number): Transaction {
  const s = getStore();
  const catIdx = s.cat[i];
  const type: ExceptionType | null = catIdx === 0 ? null : CAT_ORDER[catIdx - 1];
  const status: TxnStatus =
    catIdx === 0 ? "matched" : type === "unresolved" ? "unresolved" : "exception";

  const expected = s.expected[i];
  const difference = s.difference[i];
  const settled = expected - difference;
  const noise = s.noise[i];

  const feeBase = Math.round(expected * 0.0177);
  const fee = type === "fee_tax" ? Math.round(difference / 1.18) : feeBase;
  const tax = Math.round(fee * 0.18);
  const refund = type === "refund" ? difference : 0;

  const settlementDate = dayToDate(s.day[i]);
  const captured = new Date(settlementDate.getTime() - (1 + (noise % 2)) * DAY_MS);
  const hasSettlement = !(type === "unresolved" && noise % 3 === 0);

  return {
    orderId: `O-${10_000 + i}`,
    paymentId: `pay_${pad(noise, 5)}${pad(i % 100_000, 5)}Rz`,
    settlementId: hasSettlement ? `setl_Q${pad(1000 + (i % 9000), 4)}${pad(noise % 1000, 3)}` : null,
    bankRef: hasSettlement ? `UTR${pad(80_000_000 + i * 7 + (noise % 7), 9)}` : null,
    expected,
    settled,
    difference,
    fee,
    tax,
    refund,
    status,
    exceptionType: type,
    reason: type ? REASONS[type] : "Exact match on amount, UTR and settlement ID",
    settlementDate: settlementDate.toISOString(),
    capturedAt: captured.toISOString(),
    method: METHODS[noise % 4],
  };
}

/* ------------------------------------------------------------------ */
/* Indexes used for filtering — built lazily, once per predicate set.   */
/* ------------------------------------------------------------------ */

let exceptionIndex: Int32Array | null = null;

/** Every non-matched record, ascending. */
export function getExceptionIndex(): Int32Array {
  if (exceptionIndex) return exceptionIndex;
  const s = getStore();
  const out = new Int32Array(EXCEPTION_COUNT);
  let n = 0;
  for (let i = 0; i < TOTAL_RECORDS; i++) if (s.cat[i] !== 0) out[n++] = i;
  exceptionIndex = out;
  return out;
}

export function bucketTotals() {
  const s = getStore();
  const amount: Record<ExceptionType, number> = {
    partial_payment: 0,
    refund: 0,
    fee_tax: 0,
    rounding: 0,
    unresolved: 0,
  };
  const idx = getExceptionIndex();
  for (let k = 0; k < idx.length; k++) {
    const i = idx[k];
    amount[CAT_ORDER[s.cat[i] - 1]] += s.difference[i];
  }
  return amount;
}

export function valueTotals() {
  const s = getStore();
  let gross = 0;
  let variance = 0;
  for (let i = 0; i < TOTAL_RECORDS; i++) {
    gross += s.expected[i];
    variance += s.difference[i];
  }
  return { gross, variance, settled: gross - variance };
}

/* ------------------------------------------------------------------ */
/* Trend series — 14 days of prior batches, deterministic.             */
/* ------------------------------------------------------------------ */

export function buildTrend(): TrendPoint[] {
  const rand = mulberry32(0x2ad1);
  const points: TrendPoint[] = [];
  for (let d = 0; d < 14; d++) {
    const date = dayToDate(d);
    const isLast = d === 13;
    const processed = isLast
      ? TOTAL_RECORDS
      : Math.round(62_000 + rand() * 48_000);
    const rate = isLast
      ? MATCH_RATE
      : 94.2 + rand() * 3.6 + (d / 13) * 0.9 - (d === 6 ? 2.4 : 0);
    const matched = Math.round((processed * rate) / 100);
    points.push({
      date: date.toISOString(),
      label: date.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }),
      processed,
      matched,
      exceptions: processed - matched,
      matchRate: Number(rate.toFixed(2)),
    });
  }
  return points;
}
