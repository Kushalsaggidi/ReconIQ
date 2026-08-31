# PayRecon

[![CI](https://github.com/Kushalsaggidi/ReconPay/actions/workflows/ci.yml/badge.svg)](https://github.com/Kushalsaggidi/ReconPay/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![Node 20](https://img.shields.io/badge/node-20-339933)
![Tests](https://img.shields.io/badge/tests-117%20passing-brightgreen)

AI-powered settlement reconciliation built for finance teams.

Reconcile financial records. Surface exceptions. Explain what happened.
Know what needs a human.

> **AI can explain a discrepancy. It cannot create one.**

A deterministic three-way settlement reconciliation engine (Orders ↔ Payment
Gateway Settlements ↔ Bank Statement) with Google Gemini as an advisory AI
layer for exception classification — built to scale from hundreds of records
to millions without rewriting the core logic.

[Product Tour](#product-tour) · [Results](#results-at-a-glance) ·
[Architecture](#architecture) · [AI Trust](#ai-trust--grounding) ·
[Performance](#performance--scalability) ·
[Engineering](#key-engineering-decisions) ·
[Security](#security--reliability) ·
[Validation](#validation--proof) · [Setup](#setup) ·
[Benchmark](#performance--scalability)

---

## The Problem

One payment. Three separate financial records: an **Order**, a **Payment
Gateway Settlement**, and a **Bank Credit**. The reconciliation question is
always the same — do these three records agree?

Settlement reconciliation is often a spreadsheet-heavy process: analysts
manually compare orders against payment-gateway settlements and bank credits,
investigate discrepancies, and track exceptions row by row. This becomes
slow, error-prone, and increasingly difficult to scale as transaction volumes
grow.

<img src="docs/assets/the_problem.png" width="720" alt="Three records, one payment — manual reconciliation is slow, repetitive, and error-prone">

---

## What PayRecon Does

Give PayRecon three financial sources — Orders, Settlements, and a Bank
Statement — and it reconciles the numbers deterministically, using AI only
to explain the exceptions.

The pipeline produces:

* Matched records and exceptions, computed with no AI involvement
* Deterministic exception categories (rounding, refund, fee/tax, partial
  payment, orphan, unresolved)
* An AI-generated classification and plain-English explanation for each
  exception that needs one
* A `requiresHumanReview` signal for anything the engine or the AI can't
  confidently close
* An append-only audit trail of every step, attributed to the layer that
  performed it

<img src="docs/assets/we_built.png" width="720" alt="Three files in, deterministic engine, AI explanation, answers out">

---

## Why This Was Hard

Reconciliation is not a join between three CSVs. The engine has to handle:
inconsistent file formats (CSV/XLSX/XLS/JSON) and column layouts, monetary
precision (no floats near a balance), date and ID normalization (Excel
turning `123456` into `123456.0`), missing and duplicate settlements, orphan
settlements, refunds, fees, tax, partial payments, rounding residuals, and
malformed cells — at scale, from 100 rows to 1,000,000, and with an AI layer
in the loop that has to be constrained, validated, and allowed to fail
without taking the reconciliation down with it.

<img src="docs/assets/why_was_it_hard.png" width="720" alt="Scale, messy real-world data, and AI trust: the three engineering pressure points">

---

## Why PayRecon is Different

> **Python calculates. AI explains. Humans decide.**

* **Numbers are never AI-generated.** Every rupee on screen comes from
  deterministic Python. Gemini's explanations are structurally incapable of
  citing a figure that wasn't handed to it — `AiVerdict.assert_grounded()`
  rejects any number not present in the supplied facts, in code, not just by
  prompt instruction.
* **Built for scale, not a demo.** Hash-indexed O(n) joins, chunked streaming
  ingestion, an O(1)-memory metrics accumulator — measured end to end from
  100 to 1,000,000 records (see [Performance & Scalability](#performance--scalability)).
* **Human review is a first-class outcome, not a bug.** When no record
  explains a variance, PayRecon says so honestly, flags it, and stops —
  instead of guessing a plausible-sounding cause.
* **Audit-ready by construction.** Every step is logged and attributed to
  the layer that performed it — Engine or AI Analyst — and sealed once a
  report is generated.

> **AI can explain a discrepancy. It cannot create one.**

---

## Product Tour

<table>
<tr>
<td width="50%" valign="top">

**Overview**
Live KPIs — match rate, exceptions, variance — the moment a batch finishes,
with one click to load the bundled demo dataset.

<img src="docs/screenshots/01-overview.png" width="420" alt="Overview dashboard">
</td>
<td width="50%" valign="top">

**New Reconciliation**
Drop in Orders + Settlements (Bank Statement optional); the five-stage
pipeline processes the bundled demo dataset in seconds.

<img src="docs/screenshots/02-new-reconciliation.png" width="420" alt="New reconciliation upload screen">
</td>
</tr>
<tr>
<td width="50%" valign="top">

**Reconciliation History**
Every run is retained with its full result set, so a batch can be reopened
and inspected exactly as it was reported.

<img src="docs/screenshots/03-history.png" width="420" alt="Reconciliation history table">
</td>
<td width="50%" valign="top">

**Exceptions — breakdown**
Every record the engine couldn't close on its own, by category. The line
between "explained by a record" and "needs a human" is drawn by the engine —
the model never moves it.

<img src="docs/screenshots/04-exceptions.png" width="420" alt="Exception breakdown by category">
</td>
</tr>
<tr>
<td width="50%" valign="top">

**Exceptions — queue**
Every unresolved transaction, filterable and searchable, ready for a
treasury analyst to work through.

<img src="docs/screenshots/05-exceptions-table.png" width="420" alt="Exception queue table">
</td>
<td width="50%" valign="top">

**Exception detail — financial comparison**
Expected vs. actual vs. difference, and the full variance decomposition —
computed by the deterministic engine, labelled as such.

<img src="docs/screenshots/06-exception-detail-financial.png" width="420" alt="Exception detail: financial comparison">
</td>
</tr>
<tr>
<td width="50%" valign="top">

**Exception detail — AI analysis**
Gemini's classification and plain-English explanation — visibly separated
from the engine's numbers, never blended with them.

<img src="docs/screenshots/07-exception-detail-ai-analysis.png" width="420" alt="Exception detail: AI analysis">
</td>
<td width="50%" valign="top">

**Exception detail — recommended action**
What a human should do next, plus an explicit reminder that the app never
posts, adjusts, or reverses anything — reconciliation is read-only by design.

<img src="docs/screenshots/08-exception-detail-recommended-action.png" width="420" alt="Exception detail: recommended action">
</td>
</tr>
<tr>
<td width="50%" valign="top">

**Audit Logs**
An append-only trail of every step, tagged by the layer that performed it.

<img src="docs/screenshots/09-audit-logs.png" width="420" alt="Audit trail">
</td>
<td width="50%" valign="top">

**Audit Logs — event detail**
Engine events (matching, exception detection) interleaved with AI Analyst
events (classification), each with its own attribution.

<img src="docs/screenshots/10-audit-logs-events.png" width="420" alt="Audit trail event list">
</td>
</tr>
</table>

---

## Results at a Glance

Real numbers from this repo — a demo batch run end to end on live Gemini,
and the benchmark script run at every scale from 100 to 1,000,000 records.

<img src="docs/assets/results.png" width="720" alt="Results at a glance: 1,007 records, 90.86% match rate, 92/92 AI classifications, 117 tests passing">

| Metric | Value |
|---|---|
| Records processed (demo batch) | 1,007 |
| Match rate | 90.86% |
| Exceptions / unresolved | 71 / 21 (92 sent for AI review) |
| AI coverage | 92 / 92 exceptions classified by Gemini (100%, 0 failures) |
| Throughput (deterministic engine) | 1.2k rows/s at 100 records → 10.6k rows/s at 100k |
| Largest verified run | 1,000,000 records in 97.25s (~10.3k rows/s) |
| Automated tests | 117, all passing |

Throughput increases from ~1.2k rows/s at 100 records to ~10.6k rows/s at
100k as fixed engine setup cost amortises, then holds at ~10.3k rows/s even
at one million records — no quadratic blow-up as volume grows. See
[Performance & Scalability](#performance--scalability) and
[Validation & Proof](#validation--proof) for how these were measured.

---

## Architecture

<img src="docs/assets/arch.png" width="720" alt="PayRecon architecture: frontend, backend, ingestion, deterministic reconciliation engine, AI explanation, validation, audit">

```
Upload (CSV / XLSX / XLS / JSON)
   │
   ▼
INGESTION        app/ingestion/     format + dataset-type detection, flexible
   │                                 column mapping, chunked reads, per-row
   │                                 validation, never silently drops a row
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
ANALYSIS (Gemini)                    fails soft — never fails the job
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

**Deterministic Core** — matching, arithmetic, financial values,
reconciliation status, exception rules, metrics. **AI Layer** —
classification and natural-language explanation only, invoked after the
Deterministic Core finishes. **Validation** — checks the AI response against
the supplied facts, rejects unsupported figures. **Audit** — records both
Engine and AI events with attribution.

> **The AI never controls the financial computation.**

Money is **integer minor units (paise)** end to end — `Decimal` only at the
CSV parse boundary, quantised immediately. Floats never touch a balance.

---

## Business Impact

Settlement reconciliation is often a spreadsheet-heavy process: analysts
manually compare orders against payment-gateway settlements and bank credits,
investigate discrepancies, and track exceptions row by row. This becomes
slow, error-prone, and increasingly difficult to scale as transaction volumes
grow.

* **~90% of records can be resolved deterministically.** Matching, variance
  computation, and exception bucketing require no LLM involvement, allowing
  analyst attention to focus on genuinely ambiguous cases.
* **AI removes the write-up bottleneck, not the judgment.** Instead of an
  analyst reading each exception and typing a note from scratch, Gemini
  drafts the explanation and recommended action in plain English. A human
  still makes the call — they start from a first draft, not a blank cell.
* **Every batch produces an audit trail automatically.** The sealed,
  append-only audit trail captures reconciliation and AI events as part of
  processing, eliminating the need to reconstruct what happened later.
* **The reconciliation path scales with the dataset.** The same
  deterministic code path used for 100-record demos has been benchmarked on
  1,000,000 records, processing them in ~97 seconds (~10.3k records/sec).

---

## Why AI?

The deterministic engine already computes the correct number for every
transaction — so why involve a model at all? AI is deliberately restricted
to the exception layer, for two things a rules engine is structurally bad
at:

1. **Writing a clear, varied explanation for a human, at volume.** A real
   batch can have dozens or hundreds of exceptions. Having an analyst read
   each one and write a note doesn't scale; having a model draft that note —
   grounded in the same facts, never inventing a number — does.
2. **Classification where deterministic rules cannot confidently explain the
   exception.** "Does this look like a delayed refund or a duplicate
   settlement" is a pattern-matching question, not an arithmetic one. Gemini
   suggests a classification; a human still decides.

DETERMINISTIC ENGINE → financial source of truth. GEMINI → explanation and
classification assistant. HUMAN → final judgment where required.

What AI is **never** used for: matching records, computing a figure,
determining a financial reconciliation result, or independently resolving an
exception. Those stay 100% deterministic, so every number in this system is
defensible in an audit without reference to a model at all.

---

## AI Trust & Grounding

PayRecon uses Google Gemini for exception analysis. API availability,
quotas, and pricing vary by model and account tier, so deployment-specific
limits should be checked against Google's current documentation.

1. **Never fails a job.** Timeout, bad JSON, missing key, provider outage —
   all caught in `app/ai/analyzer.py`; affected exceptions are marked
   `ai_status: failed` and the deterministic result is untouched.
2. **Cannot cite an invented number.** The application validates AI output
   against the deterministic engine's supplied facts — `AiVerdict.assert_grounded()`
   rejects any explanation containing a figure not present in those facts,
   enforced in code, not requested in a prompt.
3. **Never marks anything resolved.** Gemini can set or add
   `requiresHumanReview`, but it cannot clear it — the AI cannot independently
   resolve a financial exception; a human remains the final authority.
4. **Bounded cost and scope.** Only `ExceptionRecord` rows are sent, capped
   at `AI_MAX_EXCEPTIONS_PER_JOB` (default 500, largest-`unexplained`-first),
   batched `AI_BATCH_SIZE` (default 20) per request. A whole dataset is
   never sent to a model.

The AI layer sits behind a single `AIService` interface, so this isn't
Gemini-specific by accident — Anthropic and OpenAI implementations exist in
`app/ai/providers/` behind the same contract, and a deterministic rule-based
explainer (`LLM_PROVIDER=null`) lets the whole pipeline run with no network
call at all, for offline development. Gemini is what this deployment
actually runs on. Provider capabilities are not identical across
implementations.

---

## Performance & Scalability

<img src="docs/assets/performance.png" width="720" alt="Performance and scalability: O(n) matching, chunked processing, streaming persistence, O(1)-memory metrics, benchmark table and charts">

* **Hash-indexed matching, not nested loops.** `MatchIndex` builds the join
  index once, making subsequent record lookups O(1) rather than repeatedly
  scanning the dataset. Overall matching is O(n).
* **Chunked, not one-shot.** CSVs stream via `pandas.read_csv(chunksize=...)`;
  the engine's `process_batch` operates on one batch against a prebuilt
  index, so a worker-pool future is a change to the *loop*, not the
  arithmetic.
* **Streaming persistence.** `engine.run(..., collect_outcomes=False,
  on_batch=persist)` writes each batch to the DB via `bulk_insert_mappings`
  and never holds the full result set in memory — verified in
  `test_on_batch_sink_receives_every_record_without_collecting`.
* **Metrics are an O(1)-memory accumulator**, folded one outcome at a time.
  This does not mean constant *total* memory: chunked ingestion and
  streaming persistence keep the resident working set small, but the
  measured peak memory below still grows with dataset size.

Measured with `scripts/benchmark.py` on this machine:

| Records | Throughput | Total time | Peak memory |
|---:|---:|---:|---:|
| 100 | 1,203 rows/s | 0.08s | 1.7 MB |
| 1,000 | 5,802 rows/s | 0.17s | 5.1 MB |
| 10,000 | 10,122 rows/s | 0.99s | 17.5 MB |
| 100,000 | 10,598 rows/s | 9.50s | 156.8 MB |
| 1,000,000 | 10,354 rows/s | 97.25s | 1,548.4 MB |

Throughput rises from ~1.2k rows/s at 100 records to ~10.6k rows/s at 100k as
fixed setup cost is amortized, then remains around ~10.3k rows/s at one
million records — without quadratic blow-up.

> **AI latency is separate from reconciliation throughput.** The
> ~97-second / 1,000,000-record benchmark above measures the deterministic
> reconciliation engine only. Gemini is invoked after reconciliation
> completes, and only for exceptions, so end-to-end runtime on a batch with
> AI enabled additionally depends on the number of exceptions, batching, and
> Gemini API response latency — none of which is included in the 97.25s
> figure.

---

## Key Engineering Decisions

* **Money as integer paise, everywhere.** Eliminates float rounding bugs at
  the source; `Decimal` exists only momentarily, at the CSV parse boundary.
* **Hash-indexed matching, not nested loops.** `MatchIndex`
  (`app/reconciliation/matcher.py`) builds the join index once; subsequent
  lookups are O(1) instead of repeatedly scanning the dataset.
* **The engine has zero framework dependencies.** `app/reconciliation/`
  doesn't know FastAPI, SQLAlchemy, or an LLM exist. It's directly testable
  and importable in a notebook to reconcile three lists of records — this is
  exactly what the test suite and benchmark exercise.
* **AI is a swappable interface, not a hardcoded call.** One `AIService`
  contract; each provider (Gemini, Anthropic, OpenAI, or the deterministic
  fallback) is a single file. Switching models is a config change, not a
  code change.
* **AI never sits on the financial critical path.** Reconciliation, matching,
  and monetary calculations complete deterministically before Gemini is
  invoked for exception analysis. AI latency or failure therefore cannot
  alter the financial result or block the core reconciliation engine.
* **Async by contract from day one.** `POST /run` returns `202` immediately;
  a `ThreadPoolExecutor`-backed worker runs the pipeline today. The
  `JobRunner` boundary provides a clean seam for replacing the current
  worker with Celery, RQ, SQS, or another queue without changing the API
  contract.
* **Pagination is not optional.** Every collection endpoint caps at
  `MAX_PAGE_SIZE = 500` — there is no route that can return a million-row
  response.
* **Ingestion never silently drops a row.** Every rejected row is surfaced
  with its dataset, row number, column, and raw value — a bad file fails
  loudly, not quietly.

---

## Security & Reliability

Full detail in [SECURITY.md](SECURITY.md). The short version:

* **Path-safe uploads.** Filenames are reduced to a safe stem and every
  resolved path is asserted to sit inside the upload root
  (`app/storage/files.py::LocalFileStore`), so a crafted `../../` filename
  cannot escape the upload directory.
* **Size- and type-checked at the door.** Every upload is checked against an
  extension allowlist and a 512 MiB cap before it's parsed.
* **AI failure is contained.** A provider timeout, outage, or bad response
  marks the affected exception `ai_status: failed` — it never fails the job
  or touches the deterministic result (`tests/test_ai_layer.py`).
* **No auth yet.** This is the single biggest gap before this runs anywhere
  but a local or judged demo — tracked honestly in [MVP Scope](#whats-deliberately-not-built-mvp-scope)
  rather than glossed over.

---

## Messy Real-World Data

The engine accepts CSV, XLSX, XLS, and JSON, with automatic format and
dataset-type detection and flexible column mapping. Ingestion normalizes
currency, date, and ID formats — including Excel-corrupted numeric IDs like
`123456.0` — and validates every row.

Unreadable data is flagged, not silently dropped: every rejected row is
surfaced with its dataset, row number, column, and raw value. Silent data
loss can produce a misleading reconciliation result, so a bad file fails
loudly instead.

---

## Validation & Proof

* **117 automated tests**, all passing, covering the 7 required
  reconciliation scenarios, ingestion edge cases, the AI grounding contract,
  and a full API end-to-end flow:
  ```bash
  pytest                                              # all 117
  pytest -v tests/test_reconciliation_scenarios.py    # the 7 required scenarios
  ```
* **The AI grounding guarantee is unit-tested, not just documented.** A
  verdict citing a figure outside the supplied facts is asserted to be
  rejected by `assert_grounded()` — see `tests/test_ai_layer.py`.
* **The scalability claim is unit-tested, not just benchmarked.**
  `test_on_batch_sink_receives_every_record_without_collecting` verifies the
  engine never buffers the full result set in memory.
* **The benchmark is reproducible on demand:**
  ```bash
  python scripts/benchmark.py                          # 100 / 1k / 10k / 100k
  python scripts/benchmark.py --sizes 1000000 --keep    # 1M, keep the generated CSVs
  ```
* **Live Gemini demo evidence.** The 92/92 AI classifications and 0 failures
  in [Results at a Glance](#results-at-a-glance) are from a demo batch run
  end to end against the live Gemini API, not prerecorded output.

---

## Hackathon Demo

A three-minute walkthrough that shows the full story:

1. **Overview →** click *Try Demo Dataset*. Point at the KPIs and note none
   of them came from the AI.
2. **New Reconciliation →** show the five-stage pipeline (Upload → Validate
   → Reconcile → Analyze exceptions → Generate report) so the audience sees
   where in the flow AI participates — one stage out of five.
3. **Exceptions →** open the category breakdown, then click into one
   exception. Show the *financial comparison* panel (labelled "computed by
   the deterministic engine") side by side with the *AI Analysis* panel
   (labelled "classification and explanation only") — this contrast is the
   core trust story.
4. **Audit Logs →** show the event timeline tagged Engine vs. AI Analyst,
   sealed once the report completes.
5. **If asked about scale:** cite the 100 → 1,000,000-record benchmark, or
   run `scripts/benchmark.py` live.

---

## Repository Structure

```
Backend/
  app/
    api/routes/        reconciliation.py, health.py — thin, no business logic
    core/               config, money (Decimal/paise), enums, error taxonomy, logging
    schemas/            domain.py (engine's internal dataclasses)
                        api.py (public response models — mirrors the frontend's types.ts)
    ingestion/          column_map.py, normalizer.py, readers.py, loader.py
    reconciliation/      config.py, matcher.py, rules.py, metrics.py, engine.py  <- the core
    ai/                  base.py, schemas.py, prompts.py, analyzer.py, factory.py
                        providers/ gemini_provider.py, null_provider.py, anthropic_provider.py, openai_provider.py
    services/            job_service.py (orchestration), results_service.py (ORM -> API)
    storage/             db.py, files.py, repository.py (all SQL lives here)
    models/              base.py, entities.py (SQLAlchemy ORM)
  scripts/              generate_data.py, benchmark.py
  tests/                test_reconciliation_scenarios.py, test_ingestion.py,
                        test_flexible_ingestion.py, test_ai_layer.py, test_api_e2e.py
  data/                 demo/ (generated CSVs), uploads/ (runtime), recon.db (SQLite)
Frontend/               React app — services/types.ts mirrors the backend's api.py schemas
docs/screenshots/       Product Tour screenshots
docs/assets/            README hero/section visuals
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

Set `LLM_PROVIDER=gemini` and `LLM_API_KEY` (a key from
https://aistudio.google.com/apikey) to run with real AI explanations — see
[Configuration](#configuration). Everything else defaults to SQLite and
needs no further setup.

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

---

## API Reference

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

## The Reconciliation Rules

```
expected  = settlement.gross_amount  or  order.order_amount
settled   = bank credit total,  else  settlement.settlement_amount
difference    = expected − settled
accounted_for = fee + tax + refund − adjustment      (declared, from the settlement)
unexplained   = difference − accounted_for            <- decides the status
```

`unexplained == 0` → **MATCHED**. A shortfall the declared fee/tax/refund
fully explains is matched, not flagged — that's what "reconciled" means to a
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

## Configuration

See `.env.example` for the full list. Key ones:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/recon.db` | Postgres-compatible; set to `postgresql+psycopg://...` for shared environments |
| `BATCH_SIZE` | `10000` | Engine + ingestion chunk size |
| `ROUNDING_TOLERANCE_MINOR` | `100` (₹1.00) | Sub-tolerance residuals classify as rounding, not partial payment |
| `LLM_PROVIDER` | `null` | Set to `gemini` for real AI explanations (`anthropic`/`openai` also implemented) |
| `LLM_API_KEY` | *(empty)* | API key for the configured provider — see https://aistudio.google.com/apikey for Gemini |
| `MODEL_NAME` | `gemini-3.5-flash-lite` | Override with an Anthropic/OpenAI model id if using those providers |
| `AI_MAX_EXCEPTIONS_PER_JOB` | `500` | Hard cap on exceptions sent to the model per job |
| `AI_BATCH_SIZE` | `20` | Exceptions sent to the model per request |
| `CORS_ORIGINS` | localhost:3000,5173,8080 | Add your frontend's origin here |

Never commit `.env`. Secrets are read from the environment only; the frontend
never sees `LLM_API_KEY`.

---

## What's Deliberately Not Built (MVP Scope)

* No distributed task queue — a thread pool is used today; the `JobRunner`
  seam is where Celery/RQ/SQS would slot in.
* No Alembic migrations — `Base.metadata.create_all()` is fine until the
  schema needs to change against data someone else depends on.
* No auth — add it at the FastAPI dependency layer (`Depends(get_db)` is
  already the pattern to extend) before this goes anywhere but a demo.
* No object storage — `LocalFileStore` is one interface
  (`app/storage/files.py::FileStore`) away from S3/GCS.

This is not a production-ready, enterprise-grade, or compliance-certified
system — it's a hackathon-scale implementation of a real reconciliation
problem, with the seams for those next steps left visible rather than
papered over.
