# Razorpay Settlement Reconciler — Frontend

A financial reconciliation engine with **AI-assisted exception analysis**.

The product line to hold on to: Python computes, the model explains. Every
amount on screen is produced deterministically; the model only classifies and
writes the explanation. The UI is built to make that separation visible —
computed figures sit on neutral surfaces with an engine attribution, and every
AI element sits on the violet AI surface with an explicit guardrail note.

```
DATA  ->  DETERMINISTIC RECONCILIATION  ->  MATCHED / EXCEPTIONS  ->  AI EXPLANATION  ->  AUDITABLE RESULT
```

## Run it

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # typecheck + production build
npm run preview  # serve the build
```

## Demo path (for a judge, ~60 seconds)

1. Overview → **Try Demo Dataset**
2. Processing runs a simulated 100,000-record batch through six labelled stages
3. Auto-transitions to **Reconciliation Results** — 97,240 matched / 2,760
   exceptions / 97.24% match rate
4. Click any exception row → the investigation drawer
5. Search `O-10482` (⌘K works anywhere) → the deliberately **unresolved** case,
   where the product refuses to guess and returns `Confidence: Low`
6. **Audit Logs** → the sealed, append-only trail with per-step attribution

## Screens

| Route | Screen |
|---|---|
| `/` | Overview dashboard — KPIs, match-rate trend, exception breakdown, activity |
| `/new` | Guided upload (3 datasets, drag & drop, demo loader) |
| `/processing/:jobId` | Live pipeline stages, records/sec, ETA |
| `/results/:jobId` | KPIs, composition, breakdown, paged transaction table |
| `/exceptions` | Exception queue with category filters |
| `/exceptions/:orderId` | Full-page investigation workspace |
| `/audit` | Audit trail timeline, filterable by engine vs AI |
| `/history` | Previous batches |
| `/settings` | Matching rules, AI guardrails, backend connection |

## Connecting the Python backend

**All API logic lives in one file: [`src/services/api.ts`](src/services/api.ts).**
No presentation component talks to the data layer directly — they import from
`@/services/api` only. Replace the function bodies with `fetch` calls and the UI
needs no changes.

| Function in `api.ts` | Endpoint to call |
|---|---|
| `uploadDataset(kind, file, onProgress)` | `POST /reconciliation/upload` |
| `runReconciliation({ datasets })` | `POST /reconciliation/run` |
| `getJobStatus(jobId)` | `GET /reconciliation/:jobId/status` |
| `getResults(jobId)` | `GET /reconciliation/:jobId/results` |
| `getTransactions(jobId, query)` | `GET /reconciliation/:jobId/transactions` |
| `getExceptions(jobId, query)` | `GET /reconciliation/:jobId/exceptions` |
| `getExceptionDetail(jobId, orderId)` | `GET /reconciliation/:jobId/exceptions/:orderId` |
| `getAuditTrail(jobId)` | `GET /reconciliation/:jobId/audit` |

Notes for the backend contract:

- **Amounts are integers in paise** everywhere in `types.ts`. No floats cross the
  wire; formatting happens only at the render edge (`formatMoney`).
- `getJobStatus` is polled every 110 ms and is a pure function of elapsed time in
  the mock — the real one can return the same `JobProgress` shape unchanged.
- The table is **server-shaped**: `TableQuery` in, `TablePage` out (rows, total,
  totalPages, facet counts). The mock already pages a 100,000-record batch
  without ever handing React more than `pageSize` rows.
- `ExceptionDetail` deliberately splits `computed` (engine) from `ai`
  (classification, explanation, confidence, signals, recommended action). Keep
  that split — the UI's credibility rests on it.

## Structure

```
src/
  services/         mock service layer — the only place API logic lives
    api.ts          the eight endpoints above
    types.ts        wire types shared with the backend
    dataset.ts      virtual 100,000-record batch (typed arrays, ~1 MB)
    analysis.ts     exception detail assembly: computed vs AI
  store/            ReconProvider (job + dataset state), ThemeProvider
  components/
    ui/             Button, Card, Badge, StatTile, DataTable, Drawer, Field…
    charts/         hand-rolled SVG: TrendChart, CompositionBar, BreakdownBars
    recon/          UploadCard, TransactionTable, ExceptionWorkspace, AuditTimeline
    layout/         AppShell, Sidebar, Topbar
  pages/            one file per screen
```

## Mock data

Deterministic (seeded PRNG) so the demo is identical on every reload:

- 100,000 records · 97,240 matched · 2,760 exceptions · 97.24% match rate
- 1,020 partial payment · 640 refund · 510 fee/tax · 320 rounding · 270 unresolved
- `O-10482` is scripted: ₹2,000.00 expected, ₹1,850.00 settled, ₹150.00
  unexplained — the graceful-failure case

The batch is held as typed arrays and a full row object is materialised only for
the rows a page renders, so filtering and sorting run over all 100,000 records
while the DOM never sees more than 100.

## Design system

Tokens are CSS custom properties in `src/index.css` (`:root` and `.dark`),
exposed to Tailwind v4 via `@theme inline`. Dark mode is a **selected** set of
values, not an inversion.

Chart colors were validated with the data-viz palette validator against both
surfaces (`#ffffff` light, `#14161a` dark) — all checks pass: lightness band,
chroma floor, CVD separation, normal-vision floor and contrast. The scheme reads
consistently across both charts:

- **green** — closed by the engine, no variance
- **blue** — exception explained by a record in the batch
- **red** — no supporting record; held for human review

Status colors are reserved and always ship with an icon + label, never color
alone.
