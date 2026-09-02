# ReconIQ — AI-Powered Settlement Reconciliation Agent (Backend)

A deterministic three-way settlement reconciliation engine (Orders ↔ Razorpay
Settlements ↔ Bank Statement) with an advisory AI layer for exception
classification. Built for a Razorpay AI hackathon; designed to scale from
hundreds of records to millions without rewriting the core logic.

**The one rule everything else follows:** Python computes every financial
figure — matching, joins, fees, tax, refunds, variance, all metrics. The LLM
only classifies and explains exceptions that the deterministic engine already
computed. It never does arithmetic, never matches records, and a failure in it
can never fail a job or change a number.

---

## Architecture

```
Upload (CSV / XLSX / XLS / JSON)
   │
   ▼
FORMAT + DATASET-TYPE DETECTION   app/ingestion/readers.py, column_map.py
   │                              format from the reader factory; dataset kind
   │                              (orders/settlements/bank) cross-checked from
   │                              headers against the kind the caller selected
   ▼
INGESTION        app/ingestion/     flexible column mapping, chunked reads,
   │                                 per-row validation, never silently drops a row
   ▼
NORMALIZATION    app/ingestion/normalizer.py
   │                                 ₹1,000 / 1,000 / 1000.00 -> integer paise,
   │                                 dates, currencies, IDs (123456.0 -> "123456")
   ▼
RECONCILIATION   app/reconciliation/  hash-indexed joins (O(n), never O(n²)),
   ENGINE                            configurable settlement equation,
   │                                 deterministic exception rules
   ▼
MATCHED /        MATCHED | EXCEPTION | UNRESOLVED, each with evidence + checks
EXCEPTIONS
   │
   ▼
EXCEPTION        app/ai/             structured facts in, validated JSON out;
ANALYSIS                             fails soft — never fails the job
   │
   ▼
RESULT           app/reconciliation/metrics.py   streaming accumulator, O(1) memory
AGGREGATION
   │
   ▼
AUDIT TRAIL      app/models/entities.py::AuditEvent   append-only narrative
   │
   ▼
REST API         app/api/            FastAPI, camelCase + paise, paginated
```

Money is **integer minor units (paise)** end to end — `Decimal` only at the CSV
parse boundary, quantised immediately. Floats never touch a balance.

### Why these layers are separate

* **`app/reconciliation/`** has no idea FastAPI, SQLAlchemy or an LLM exist. You
  can `import` it in a notebook and reconcile three lists of records. This is
  what the tests and the benchmark actually exercise.
* **`app/ingestion/`** turns any vaguely-tabular file (CSV, XLSX, XLS or JSON)
  into canonical dataclasses (`OrderRecord`, `SettlementRecord`,
  `BankRecord`). Swapping a reader for a database cursor later means changing
  one file (`app/ingestion/readers.py`), not the engine.
* **`app/ai/`** is a provider abstraction (`AIService`). `LLM_PROVIDER=null`
  (the default) runs a deterministic rule-based explainer — the whole system
  works end-to-end with **no API key and no network call**.
* **`app/services/job_service.py`** is the only place that knows jobs run in a
  background thread pool today. Swap it for Celery/RQ/SQS later without
  touching the API contract — `POST /run` already returns `{jobId}` and the
  frontend already polls `/status`.

---

## Folder structure

```
backend/
  app/
    api/routes/        reconciliation.py, health.py — thin, no business logic
    core/               config, money (Decimal/paise), enums, error taxonomy, logging
    schemas/            domain.py (engine's internal dataclasses)
                        api.py (public response models — mirrors the frontend's types.ts)
    ingestion/          column_map.py, normalizer.py, readers.py, loader.py
    reconciliation/      config.py, matcher.py, rules.py, metrics.py, engine.py  <- the core
    ai/                  base.py, schemas.py, prompts.py, analyzer.py, factory.py
                        providers/ null_provider.py, gemini_provider.py, anthropic_provider.py, openai_provider.py
    services/            job_service.py (orchestration), results_service.py (ORM -> API)
    storage/             db.py, files.py, repository.py (all SQL lives here)
    models/              base.py, entities.py (SQLAlchemy ORM)
  scripts/              generate_data.py, benchmark.py
  tests/                test_reconciliation_scenarios.py, test_ingestion.py,
                        test_ai_layer.py, test_api_e2e.py
  data/                 demo/ (generated CSVs), uploads/ (runtime), recon.db (SQLite)
```

---

## Setup

```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
copy .env.example .env          # Windows: copy; macOS/Linux: cp
```

`.env` defaults to SQLite and `LLM_PROVIDER=null` — nothing else is required to
run the whole system.

### Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

* Docs: http://localhost:8000/docs
* Health: http://localhost:8000/api/health

### Generate demo data

```bash
python scripts/generate_data.py --records 1000 --out data/demo
# also supports: --records 100 | 10000 | 100000 | 1000000
```

Produces `orders.csv`, `settlements.csv`, `bank_statement.csv` — internally
consistent, with a deliberate mix of clean matches, fee/tax double-deductions,
refund double-deductions, rounding residuals, partial payments, a missing
settlement, a duplicate settlement (ambiguous — refused rather than guessed),
an orphan settlement, and a handful of malformed cells to exercise validation.

### Try it end to end

```bash
curl -F "kind=orders"       -F "file=@data/demo/orders.csv"            http://localhost:8000/api/reconciliation/upload
curl -F "kind=settlements"  -F "file=@data/demo/settlements.csv"        http://localhost:8000/api/reconciliation/upload
curl -F "kind=bank"         -F "file=@data/demo/bank_statement.csv"     http://localhost:8000/api/reconciliation/upload

curl -X POST http://localhost:8000/api/reconciliation/run \
  -H "Content-Type: application/json" \
  -d '{"ordersDatasetId":"ds_...","settlementsDatasetId":"ds_...","bankDatasetId":"ds_..."}'

curl http://localhost:8000/api/reconciliation/RCN-.../status
curl http://localhost:8000/api/reconciliation/RCN-.../results
curl http://localhost:8000/api/reconciliation/RCN-.../transactions?page=1&page_size=50
curl http://localhost:8000/api/reconciliation/RCN-.../exceptions
curl http://localhost:8000/api/reconciliation/RCN-.../audit
```

### Run tests

```bash
pytest                    # 117 tests: scenarios, ingestion, AI layer, full API flow
pytest -v tests/test_reconciliation_scenarios.py   # the 7 required scenarios + matching rules
```

### Run the benchmark

```bash
python scripts/benchmark.py                          # 100 / 1k / 10k / 100k
python scripts/benchmark.py --sizes 1000000 --keep   # 1M, keep the generated CSVs
```

Measures ingest + reconcile time, throughput and memory at each size. Confirms
the join is O(n) — measured on this machine:

| Records | Throughput | Total time | Memory |
|---:|---:|---:|---:|
| 100 | 1,203 rows/s | 0.08s | 1.7 MB |
| 1,000 | 5,802 rows/s | 0.17s | 5.1 MB |
| 10,000 | 10,122 rows/s | 0.99s | 17.5 MB |
| 100,000 | 10,598 rows/s | 9.50s | 156.8 MB |
| 1,000,000 | 10,354 rows/s | 97.25s | 1,548.4 MB |

Throughput *increases* from ~1.2k rows/s at 100 records to ~10.6k rows/s at
100k (fixed engine setup cost amortises) and holds at ~10.3k rows/s even at
one million records — no quadratic blow-up as volume grows.

---

## API reference

All responses are camelCase with amounts in **integer paise**, matching
`Frontend/src/services/types.ts` exactly — the frontend's `mockApi` can be
replaced with real `fetch` calls with no component changes.

| Method | Path                                          | Purpose                          |
|--------|-----------------------------------------------|-----------------------------------|
| POST   | `/api/reconciliation/upload`                  | Upload one file — CSV/XLSX/XLS/JSON (orders/settlements/bank) |
| GET    | `/api/reconciliation/datasets`                | List uploaded datasets |
| POST   | `/api/reconciliation/run`                     | Queue a job → `{jobId, status}` (202) |
| GET    | `/api/reconciliation/jobs`                    | Job history |
| GET    | `/api/reconciliation/{job_id}/status`         | Poll progress + stage list |
| GET    | `/api/reconciliation/{job_id}/results`        | Summary + exception breakdown |
| GET    | `/api/reconciliation/{job_id}/trend`          | Daily trend points |
| GET    | `/api/reconciliation/{job_id}/transactions`   | Paginated, filterable, sortable |
| GET    | `/api/reconciliation/{job_id}/exceptions`     | Same, exceptions only |
| GET    | `/api/reconciliation/{job_id}/exceptions/{order_id}` | Full detail + evidence + AI |
| GET    | `/api/reconciliation/{job_id}/audit`          | Paginated audit timeline |
| GET    | `/api/reconciliation/{job_id}/export`         | CSV export (capped) |
| GET    | `/api/health`                                 | Liveness + AI provider status |

Query params on `/transactions` and `/exceptions`: `page`, `page_size` (≤500),
`status`, `exception_type`, `search`, `sort_by`, `sort_dir`.

Every error is `{"error": {"code", "message", "context", "issues": [...]}}` —
`issues` carries row-level detail (dataset, row number, column, raw value)
whenever the failure traces to specific rows.

---

## Flexible file ingestion

Real-world exports never agree on file format or column names. Ingestion
handles both without touching the reconciliation engine, which still only
ever sees the same canonical `OrderRecord` / `SettlementRecord` / `BankRecord`
dataclasses.

### Supported formats

`.csv`, `.xlsx`, `.xls`, `.json` — enforced by `Settings.allowed_upload_suffixes`
in `app/core/config.py`, the single source of truth the frontend also reads
(via `GET /api/health` → `upload.allowedFormats`). Anything else is rejected
with `INVALID_FILE_TYPE` before it is ever parsed.

JSON accepts a bare array of row-objects, or one wrapped in `records` / `data`
/ `rows` / `items`:

```json
[{ "order_id": "O-1", "payment_id": "P-1", "order_amount": "1999.00" }]
```

The upload size limit is `Settings.max_upload_bytes` (**512 MiB** by default),
also surfaced through `GET /api/health` → `upload.maxBytes`, and enforced both
client-side (`Frontend/src/services/api.ts::validateFileBeforeUpload`) and
server-side (`app/ingestion/readers.py::validate_upload`) so the two can never
disagree.

CSV streams in `chunk_size`-row batches via `pandas.read_csv(chunksize=...)`.
Excel and JSON have no streaming reader in their respective libraries, so the
file is parsed once into memory and then processed downstream in the same
bounded batches — the upload size gate is what keeps that one parse bounded.

### Dataset-type detection

Every upload still names its slot explicitly (`kind=orders|settlements|bank`
on `POST /upload`) — that does not change. What is new is a cross-check:
`app/ingestion/column_map.py::detect_dataset_kind` scores the file's headers
against all three dataset shapes using the exact same alias table
`resolve_columns` uses, so "detected as X" and "resolves as X" can never
disagree.

**Why a naive score is wrong.** Settlement and bank exports are naturally
linked to an order and a payment, so they legitimately carry `order_id` /
`payment_id` / a bare `amount` column too — those are *shared* vocabulary, not
evidence of being an Orders file. An earlier version of this scoring counted
"required-field coverage" without regard to how generic the matched header
was, so a settlements file with `order_id + payment_id + amount` scored a
perfect 100% required-coverage for *Orders* (all three of its required fields
technically matched) while its own real signals — `settlement_id`, `fee`,
`tax`, `utr`, `settlement_date` — were still being counted separately for
*Settlements* under a different, lower-weighted bucket. Orders won on a
technicality despite the file having none of what actually makes it an
order (`order_date`, `payment_status`, `payment_method`).

**The fix** scores each matched field by how *specific* the header that
matched it is, not just whether the field is required:

* A header that matches a field through a specific, compound alias
  (`settlement_amount`, `processor_transaction_id`, `payment_status`,
  `closing_balance`, `narration`) counts at full weight — required fields at
  `3.0`, optional fields at `1.5`.
* A header that matches a field only through a bare, single-word alias shared
  by every kind (`amount`, `date`, `status`, `currency`, `id`, `value`, ...)
  is discounted to 15% of that weight — enough to break a tie, nowhere near
  enough to decide one.
* The final score per kind is `matched weight / total possible weight`, so a
  kind only wins by matching several of its *own distinguishing* fields, not
  by reusing a handful of words every export shares.

This is what lets the real `processor_transactions.csv` — headers
`processor_transaction_id, merchant_order_id, processor_event_type,
processor_event_time, gross_amount, fee_amount, net_amount, currency,
settlement_batch_id, processor_status` — score **Settlements 0.68** against
**Orders 0.42** even though it carries a `merchant_order_id` column and *no
payment id at all*: the settlement-specific fields
(`processor_transaction_id → settlement_id`, `fee_amount`, `net_amount`,
`settlement_batch_id → utr`, `processor_status`) tip it decisively, and the
shared `order_id`/`amount`-shaped columns only ever contribute their
full-strength weight to *Orders* — plain generic overlap can't manufacture a
false win by itself.

* A **confident mismatch** (e.g. a settlements-shaped file uploaded as
  `orders`) is rejected with a clear message naming the kind it actually looks
  like — the operator re-uploads it to the right slot rather than getting a
  silently-wrong reconciliation.
* A **genuinely ambiguous** file (top two kinds scored within 15% of each
  other) is not blocked — it uploads with a `warnings[]` entry naming the
  candidate kinds and their scores, which the frontend surfaces, since the
  operator already made an explicit choice and a second forced decision would
  be noise.

### Flexible column mapping

`app/ingestion/column_map.py` declares every canonical field's aliases once
(shared across specs via `PAYMENT_ID_ALIASES`, `UTR_ALIASES`,
`CURRENCY_ALIASES`, etc.), covering order/payment/settlement ids, UTR,
amounts, fees, tax, refunds, adjustments, dates, currency, status, method,
debit/credit and running balance. Headers are normalised (`slugify`) before
matching, so case, whitespace, hyphens and punctuation never create a false
mismatch — `"Order ID"`, `"order_id"`, `"ORDER-ID"` and `"Order_Id"` are the
same field.

Matching is alias-exact, never fuzzy: a header either matches a declared
alias or it doesn't. Priority is exact name → declared alias → nothing — there
is no "looks similar" fallback, because a wrong guess on a money column is
worse than an error asking the operator to rename one header. If two headers
in the same file both plausibly satisfy one canonical field (e.g. both
`amount` and `gross_amount` present for `order_amount`), that is reported as
`AMBIGUOUS_COLUMN` rather than guessed.

**Example** — the previously-failing `internal_transactions.csv`
(`internal_payment_id`, `merchant_order_id`, `occurred_at`, `gross_amount`,
`currency`, `payment_status`, `payment_method`, `synthetic_customer_reference`)
now resolves as:

| Source column          | Canonical field |
|-------------------------|-----------------|
| `internal_payment_id`   | `payment_id`    |
| `merchant_order_id`     | `order_id`      |
| `occurred_at`           | `order_date`    |
| `gross_amount`          | `order_amount`  |
| `currency`              | `currency`      |
| `payment_status`        | `status`        |
| `payment_method`        | `method`        |
| `synthetic_customer_reference` | *(unmapped — not required, left out of the report as an unknown column, never forced in)* |

1,000 rows parse and map cleanly, and 10 duplicate `order_id` rows are
reported as `DUPLICATE_IDENTIFIER` warnings (first occurrence kept) rather
than silently dropped
(`Backend/tests/test_flexible_ingestion.py::test_internal_transactions_csv_passes_through_the_real_upload_endpoint`
drives this through the real `/upload` endpoint, not a synthetic fixture).

The other two files from the same synthetic dataset resolve the same way, as
Settlements and a Bank Statement respectively — none of the three filenames
are special-cased anywhere in the code; classification and mapping run purely
off headers. Their real schemas turned out to need more than aliases,
though — see the two sub-sections below.

`processor_transactions.csv` → **Settlements**:

| Source column              | Canonical field    |
|-----------------------------|--------------------|
| `processor_transaction_id`  | `settlement_id`    |
| `merchant_order_id`         | `order_id`         |
| `gross_amount`              | `gross_amount`     |
| `fee_amount`                | `fee`              |
| `net_amount`                | `settlement_amount`|
| `settlement_batch_id`       | `utr`              |
| `processor_status`          | `status`           |
| `processor_event_time`      | `settlement_date`  |
| `processor_event_type`      | *(unmapped — not a canonical field, left out, never forced in)* |

This file carries **no payment id column at all** — only the merchant order
reference. That's a real, not just cosmetic, gap: `SettlementRecord.payment_id`
was a required field the matcher always joined on, so this file would parse
its columns fine and then match *zero* orders. The fix, scoped narrowly to
the join key itself:

* `SettlementRecord` gained an optional `order_id` field alongside
  `payment_id` (`app/schemas/domain.py`).
* `SETTLEMENTS_SPEC` now declares `order_id` (optional) and relaxes
  `payment_id` to optional too, with `one_of=(("payment_id", "order_id"),)` —
  a settlement must carry *one* of the two to be joinable, mirroring the
  existing `settlement_id`/`utr` one_of on the bank side.
* `MatchIndex` (`app/reconciliation/matcher.py`) gained a second index,
  `settlements_by_order`, populated only for settlement rows with no
  `payment_id`; `match_order` tries `payment_id` first, then `order_id`. The
  join algorithm itself is unchanged — still one O(1) hash lookup, just on
  whichever key the file actually provided.

`bank_settlements.csv` → **Bank Statement**:

| Source column        | Canonical field        |
|-----------------------|------------------------|
| `bank_entry_id`       | `bank_transaction_id`  |
| `settlement_batch_id` | `utr`                  |
| `credited_amount`     | `credit_amount`        |
| `booked_at`           | `transaction_date`     |
| `description`         | `description`          |
| `bank_reference`      | *(unmapped — this file's own internal reference, not the cross-file join key; see below)* |

This file has **no per-transaction settlement id or UTR of its own** — only
`settlement_batch_id`, the same batch reference `processor_transactions.csv`
carries, and a separate `bank_reference` column that is purely descriptive
(it never repeats across files). Aliasing both to the same canonical field
would have made them collide as `AMBIGUOUS_COLUMN`. The fix was **not** a new
join path — `settlement_batch_id` maps to the *existing* `utr` field on both
the settlement and the bank side (`UTR_ALIASES` gained
`settlement_batch_id`/`batch_id`/`payout_batch_id`), which the matcher already
treats as a many-settlements-to-one-bank-row key. `bank_reference` was
deliberately kept out of `UTR_ALIASES` so it can't collide with it.

`test_processor_transactions_csv_is_classified_and_mapped_as_settlements`,
`test_bank_settlements_csv_is_classified_and_mapped_as_bank`,
`test_order_id_only_settlement_still_joins_to_its_order` and
`test_orders_settlements_bank_reconcile_together_end_to_end` cover all of the
above, the last one driving all three real files through the real `/upload`
and `/run` endpoints together end to end.

**Known limitation.** This dataset's settlements are batched: several
`processor_transactions.csv` rows can legitimately share one
`settlement_batch_id`, and the one matching bank row's `credited_amount` is
the sum credited for the *whole batch*, not any single settlement's share.
The engine's bank join (`settlement.utr == bank.utr`) correctly finds that
bank row for every settlement in the batch, but it compares each individual
order against the *whole batch total*, not an allocated portion — so match
rates on this specific file are not representative of reconciliation
accuracy. Splitting a batch credit across its settlements is a genuine
reconciliation-engine change (an aggregation step before the per-order
comparison), which is out of scope for an ingestion/mapping fix and was not
attempted here; flagging it rather than quietly shipping misleading match
rates.

---

## The reconciliation rules

```
expected  = settlement.gross_amount  or  order.order_amount
settled   = bank credit total,  else  settlement.settlement_amount
difference    = expected − settled
accounted_for = fee + tax + refund − adjustment      (declared, from the settlement)
unexplained   = difference − accounted_for            <- decides the status
```

`unexplained == 0` → **MATCHED**. A shortfall the declared fee/tax/refund fully
explains is matched, not flagged — that's what "reconciled" means to a
treasury team. Otherwise:

| Condition | Status | Type |
|---|---|---|
| No settlement record for the payment | UNRESOLVED | — |
| Multiple settlements for one payment | UNRESOLVED | — (ambiguous, refused) |
| `\|unexplained\| ≤` rounding tolerance (₹1 default) | EXCEPTION | rounding |
| Residual equals declared refund | EXCEPTION | refund |
| Residual equals declared fee (+tax) | EXCEPTION | fee_tax |
| Residual < 0 (more arrived than justified) | EXCEPTION | partial_payment (over-settlement) |
| Money arrived, gap unexplained | EXCEPTION | partial_payment |
| Settlement exists, nothing credited | UNRESOLVED | — |
| Settlement with no order | UNRESOLVED | (orphan, surfaced not dropped) |

All thresholds live in `app/reconciliation/config.py` (`ReconciliationConfig`) —
changing a business rule means editing data, not code.

---

## The AI layer's guarantees

ReconIQ runs on **Google Gemini** (`gemini-3.5-flash-lite`) — fast and cheap
enough to explain every exception in a batch, not just a sample, on Google's
free tier. Get a key at https://aistudio.google.com/apikey and set
`LLM_PROVIDER=gemini` + `LLM_API_KEY` (see [Configuration](#configuration)).

1. **Never fails a job.** Timeout, bad JSON, missing key, provider outage — all
   caught in `app/ai/analyzer.py`; affected exceptions are marked
   `ai_status: failed`, the deterministic result is untouched.
2. **Cannot cite an invented number.** `AiVerdict.assert_grounded()` rejects any
   explanation containing a figure not present in the supplied facts.
3. **Never marks anything resolved.** The AI only sets `requiresHumanReview`;
   it can add the flag, never clear it — the union of the engine's judgement
   and the model's.
4. **Bounded cost.** Only `ExceptionRecord` rows are sent, capped at
   `AI_MAX_EXCEPTIONS_PER_JOB` (default 500, largest-`unexplained`-first),
   batched `AI_BATCH_SIZE` (default 20) per request. A whole dataset is never
   sent to a model.

### Provider abstraction

The AI layer sits behind a single `AIService` interface, so Gemini isn't a
hardcoded dependency — Anthropic and OpenAI implementations exist in
`app/ai/providers/` behind the same contract, and `LLM_PROVIDER=null` runs a
deterministic rule-based explainer with no network call, for offline
development. Switching providers is a config change, not a code change; this
deployment runs on Gemini.

---

## Scalability notes

* **Matching is O(n).** `MatchIndex` (app/reconciliation/matcher.py) builds hash
  maps once; every lookup is O(1). Never a nested loop over datasets.
* **Chunked, not one-shot.** CSVs stream via `pandas.read_csv(chunksize=...)`;
  the engine's `process_batch` operates on one batch against a prebuilt index,
  so a worker-pool future is a change to the *loop*, not the arithmetic.
* **Streaming persistence.** `engine.run(..., collect_outcomes=False,
  on_batch=persist)` writes each batch to the DB via `bulk_insert_mappings` and
  never holds the full result set in memory — verified in
  `test_on_batch_sink_receives_every_record_without_collecting`.
* **Metrics are an O(1)-memory accumulator**, folded one outcome at a time.
* **Pagination is mandatory and capped** (`MAX_PAGE_SIZE = 500`) on every
  collection endpoint — there is no route that can return a million rows.
* **The job is async from the API's perspective** — `POST /run` returns 202
  immediately; a `ThreadPoolExecutor`-backed worker runs the pipeline. Swapping
  in Celery/RQ later changes `JobRunner.submit`, not the contract.

---

## Configuration

See `.env.example` for the full list. Key ones:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/recon.db` | Postgres-compatible; set to `postgresql+psycopg://...` for shared environments |
| `BATCH_SIZE` | `10000` | Engine + ingestion chunk size |
| `ROUNDING_TOLERANCE_MINOR` | `100` (₹1.00) | Sub-tolerance residuals classify as rounding, not partial payment |
| `LLM_PROVIDER` | `null` | Set to `gemini` for real AI explanations (`anthropic`/`openai` also implemented) |
| `LLM_API_KEY` | *(empty)* | Free Gemini key from https://aistudio.google.com/apikey |
| `MODEL_NAME` | `claude-sonnet-4-5` | Set to `gemini-3.5-flash-lite` when `LLM_PROVIDER=gemini` |
| `AI_MAX_EXCEPTIONS_PER_JOB` | `500` | Hard cap on exceptions sent to the model per job |
| `CORS_ORIGINS` | localhost:3000,5173,8080 | Add your Lovable/Next.js origin here |

Never commit `.env`. Secrets are read from the environment only; the frontend
never sees `LLM_API_KEY`.

---

## What's deliberately not built (MVP scope)

* No distributed task queue — a thread pool is enough for a hackathon; the
  `JobRunner` seam is where Celery/RQ would slot in.
* No Alembic migrations — `Base.metadata.create_all()` is fine until the schema
  needs to change against data someone else depends on.
* No auth — add it at the FastAPI dependency layer (`Depends(get_db)` is
  already the pattern to extend) before this goes anywhere but a demo.
* No object storage — `LocalFileStore` is one interface
  (`app/storage/files.py::FileStore`) away from S3/GCS.
