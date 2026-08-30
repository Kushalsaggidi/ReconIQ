# PayRecon — AI-Powered Settlement Reconciliation Agent

A deterministic three-way settlement reconciliation engine (Orders ↔ Razorpay
Settlements ↔ Bank Statement) with Google Gemini as an advisory AI layer for
exception classification. Built for a Razorpay AI hackathon; designed to scale
from hundreds of records to millions without rewriting the core logic.

**The one rule everything else follows:** Python computes every financial
figure — matching, joins, fees, tax, refunds, variance, all metrics. Gemini
only classifies and explains exceptions that the deterministic engine already
computed. It never does arithmetic, never matches records, and a failure in it
can never fail a job or change a number.

---

## 📊 Results at a glance

Real numbers from this repo — a demo batch run end to end on live Gemini,
and the benchmark script run at every scale from 100 to 1,000,000 records.

| Metric | Value |
|---|---|
| Records processed (demo batch) | 1,007 |
| Match rate | 90.86% |
| Exceptions / unresolved | 71 / 21 (92 sent for AI review) |
| AI coverage | 92 / 92 exceptions classified by Gemini (100%, 0 failures) |
| Throughput (deterministic engine) | 1.2k rows/s at 100 records → 10.6k rows/s at 100k |
| Largest verified run | 1,000,000 records in 97.25s (~10.3k rows/s) |
| Automated tests | 117, all passing |

See [Performance & scalability](#performance--scalability) and
[Validation & proof](#validation--proof) for how these were measured.

---

## Why PayRecon is different

* **Numbers are never AI-generated.** Every rupee on screen comes from
  deterministic Python. Gemini's explanations are structurally incapable of
  citing a figure that wasn't handed to it — `AiVerdict.assert_grounded()`
  rejects any number not present in the supplied facts, in code, not just by
  prompt instruction.
* **Built for scale, not a demo.** Hash-indexed O(n) joins, chunked streaming
  ingestion, O(1)-memory metrics — measured end to end from 100 to 1,000,000
  records (see [Performance & Scalability](#performance--scalability)).
* **Human review is a first-class outcome, not a bug.** When no record
  explains a variance, PayRecon says so honestly, flags it, and stops —
  instead of guessing a plausible-sounding cause.
* **Audit-ready by default.** Every step is logged and attributed to the
  layer that performed it — Engine or AI Analyst — and sealed once a report
  is generated. That's a compliance requirement most reconciliation demos
  bolt on later; here it's a byproduct of how the pipeline is built.

---

## Product tour

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
pipeline typically completes in under 15 seconds.

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
computed by the engine, labelled as such.

<img src="docs/screenshots/06-exception-detail-financial.png" width="420" alt="Exception detail: financial comparison">
</td>
</tr>
<tr>
<td width="50%" valign="top">

**Exception detail — AI analysis**
Gemini's classification, confidence, and plain-English explanation — visibly
separated from the engine's numbers, never blended with them.

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

## Business impact

Settlement reconciliation today is usually a spreadsheet exercise: an analyst
manually diffs orders against gateway settlements against bank credits,
row by row. It's slow, error-prone, and it doesn't scale past a few thousand
rows a day without adding headcount.

* **The deterministic 90% is instant and exact.** Matching, variance
  computation, and exception bucketing happen in milliseconds — a treasury
  team's time goes only to the genuinely ambiguous cases, not the clean
  matches.
* **AI removes the write-up bottleneck, not the judgment.** Instead of an
  analyst reading each exception and typing a note from scratch, Gemini
  drafts the explanation and recommended action in plain English. A human
  still makes the call — they start from a first draft, not a blank cell.
* **Every batch is audit-ready the moment it finishes.** The sealed,
  append-only audit trail means there's no separate reporting step before a
  compliance review — it already exists.
* **It's exactly as scalable as the ledger it's watching.** The same code
  path that reconciles 100 records is benchmarked at 1,000,000 — there's no
  "the demo works, production needs a rewrite" gap.

---

## Why AI?

The deterministic engine already computes the correct number for every
transaction — so why involve a model at all? Two things a rules engine is
structurally bad at, which is exactly where Gemini is used and nowhere else:

1. **Writing a clear, varied explanation for a human, at volume.** A real
   batch can have dozens or hundreds of exceptions. Having an analyst read
   each one and write a note doesn't scale; having a model draft that note —
   grounded in the same facts, never inventing a number — does.
2. **Judgment calls where the deterministic signal is inconclusive.**
   "Does this look like a delayed refund or a duplicate settlement" is a
   pattern-matching question, not an arithmetic one. Gemini classifies and
   suggests; a human still decides.

What AI is **never** used for: matching records, computing a figure, or
deciding whether something is reconciled. Those stay 100% deterministic, so
every number in this system is defensible in an audit without reference to a
model at all.

---

## AI grounding & trust

PayRecon runs on **Google Gemini** (`gemini-3.5-flash-lite`). Google's free
tier needs no credit card and comfortably covers demo-scale traffic like
this (Google no longer publishes fixed quotas — check current limits for
your key in AI Studio); beyond that, the model is priced at $0.30 / 1M input
tokens and $2.50 / 1M output tokens, cheap enough to explain every exception
in a batch rather than sampling a few.

1. **Never fails a job.** Timeout, bad JSON, missing key, provider outage —
   all caught in `app/ai/analyzer.py`; affected exceptions are marked
   `ai_status: failed` and the deterministic result is untouched.
2. **Cannot cite an invented number.** `AiVerdict.assert_grounded()` rejects
   any explanation containing a figure not present in the supplied facts —
   enforced in code, not requested in a prompt.
3. **Never marks anything resolved.** Gemini only sets
   `requiresHumanReview`; it can add the flag, never clear it — the union of
   the engine's judgement and the model's, not a replacement for either.
4. **Bounded cost.** Only `ExceptionRecord` rows are sent, capped at
   `AI_MAX_EXCEPTIONS_PER_JOB` (default 500, largest-`unexplained`-first),
   batched `AI_BATCH_SIZE` (default 20) per request. A whole dataset is never
   sent to a model.

The AI layer sits behind a single `AIService` interface, so this isn't
Gemini-specific by accident — Anthropic and OpenAI implementations exist in
`app/ai/providers/` behind the same contract, and a deterministic rule-based
explainer (`LLM_PROVIDER=null`) lets the whole pipeline run with no network
call at all, for offline development. Gemini is what this deployment
actually runs on.

---

## Architecture

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

Money is **integer minor units (paise)** end to end — `Decimal` only at the CSV
parse boundary, quantised immediately. Floats never touch a balance.

---

## Key engineering decisions

* **Money as integer paise, everywhere.** Eliminates float rounding bugs at
  the source; `Decimal` exists only momentarily, at the CSV parse boundary.
* **Hash-indexed matching, not nested loops.** `MatchIndex`
  (`app/reconciliation/matcher.py`) builds the join index once; every lookup
  is O(1) from the start — not a later optimization.
* **The engine has zero framework dependencies.** `app/reconciliation/`
  doesn't know FastAPI, SQLAlchemy, or an LLM exist. It's directly testable
  and importable in a notebook to reconcile three lists of records — this is
  exactly what the test suite and benchmark exercise.
* **AI is a swappable interface, not a hardcoded call.** One `AIService`
  contract; each provider (Gemini, Anthropic, OpenAI, or the deterministic
  fallback) is a single file. Switching models is a config change, not a
  code change.
* **Async by contract from day one.** `POST /run` returns `202` immediately;
  a `ThreadPoolExecutor`-backed worker runs the pipeline today, but the
  `JobRunner` seam is exactly where Celery/RQ/SQS slots in without touching
  the API contract.
* **Pagination is not optional.** Every collection endpoint caps at
  `MAX_PAGE_SIZE = 500` — there is no route that can return a million-row
  response.
* **Ingestion never silently drops a row.** Every rejected row is surfaced
  with its dataset, row number, column, and raw value — a bad file fails
  loudly, not quietly.

---

## Performance & scalability

* **Matching is O(n).** `MatchIndex` builds hash maps once; every lookup is
  O(1). Never a nested loop over datasets.
* **Chunked, not one-shot.** CSVs stream via `pandas.read_csv(chunksize=...)`;
  the engine's `process_batch` operates on one batch against a prebuilt
  index, so a worker-pool future is a change to the *loop*, not the
  arithmetic.
* **Streaming persistence.** `engine.run(..., collect_outcomes=False,
  on_batch=persist)` writes each batch to the DB via `bulk_insert_mappings`
  and never holds the full result set in memory — verified in
  `test_on_batch_sink_receives_every_record_without_collecting`.
* **Metrics are an O(1)-memory accumulator**, folded one outcome at a time.

Measured with `scripts/benchmark.py` on this machine:

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

## Validation & proof

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

---

## Hackathon demo

A three-minute walkthrough that shows the full story:

1. **Overview →** click *Try Demo Dataset*. Results land in under 15
   seconds — point at the KPIs and note none of them came from the AI.
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
                        providers/ gemini_provider.py, null_provider.py, anthropic_provider.py, openai_provider.py
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

Set `LLM_PROVIDER=gemini` and `LLM_API_KEY` (a free key from
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
| `CORS_ORIGINS` | localhost:3000,5173,8080 | Add your frontend's origin here |

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
