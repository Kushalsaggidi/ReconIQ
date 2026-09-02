# Security & Reliability

ReconIQ is a hackathon-scope prototype that touches financial data, so the
controls that do exist are documented here — plainly, without overstating
scope.

## What's in place today

- **Upload validation.** Every upload is checked against an explicit
  extension allowlist (`.csv`, `.xlsx`, `.xls`, `.json`) and a hard size cap
  (`MAX_UPLOAD_BYTES`, 512 MiB default) before it touches the filesystem —
  see `app/core/config.py` and `validate_upload()` in
  `app/api/routes/reconciliation.py`.
- **No raw file paths from client input.** Uploaded files are written under
  a server-controlled `data/uploads/<kind>/` directory with a
  server-generated filename prefix; the client-supplied filename is never
  used to construct a filesystem path.
- **Malformed data never fails silently.** Every rejected row — bad type,
  missing column, corrupt cell — is surfaced with its dataset, row number,
  column, and raw value instead of being dropped or crashing the job. See
  `tests/test_ingestion.py` and `tests/test_flexible_ingestion.py`.
- **Money is never a float.** All monetary values are integer minor units
  end to end, eliminating an entire class of rounding/precision bugs that
  can silently corrupt financial output.
- **Secrets stay server-side.** `LLM_API_KEY` and `DATABASE_URL` are read
  from the environment only (`.env`, gitignored); the frontend never
  receives or stores a provider key. `.env.example` documents every
  variable with no real secret committed.
- **AI failure is isolated by design.** A timeout, malformed JSON, missing
  key, or provider outage in `app/ai/analyzer.py` marks the affected
  exception `ai_status: failed` — it does not fail the reconciliation job
  or corrupt the deterministic result. Covered by `tests/test_ai_layer.py`.
- **AI cannot forge a financial figure.** `AiVerdict.assert_grounded()`
  rejects any AI-generated explanation that cites a number outside the
  facts the deterministic engine supplied — enforced in code, unit-tested,
  not just prompted for.
- **CORS is explicit, not wildcarded.** Allowed origins are a configured
  allowlist (`CORS_ORIGINS`), not `*`.
- **Reconciliation is read-only.** The API never posts, adjusts, or
  reverses a transaction anywhere — it only reads uploaded data and writes
  its own results/audit trail.
- **Pagination everywhere.** Every collection endpoint caps at
  `MAX_PAGE_SIZE = 500`; there is no route that can be forced to return an
  unbounded response.

## What's explicitly out of scope for this MVP

- **No authentication or authorization.** Every endpoint is open. This is
  the single biggest gap before this could run anywhere but a local demo or
  a judged environment with a private URL — see `app/api/routes/`, which is
  the layer a `Depends(get_current_user)`-style check would slot into.
- **No rate limiting.** A public deployment would need it in front of
  `/api/reconciliation/upload` and `/run` at minimum.
- **No encryption-at-rest for uploaded files or the SQLite database.**
  Uploaded CSVs and `recon.db` are plain files on local disk.
- **No dependency/SAST scanning in CI.** `requirements.txt` and
  `package.json` pin exact versions but are not currently scanned by a tool
  like `pip-audit` or `npm audit` in the CI workflow.
- **No prompt-injection hardening beyond output validation.** The AI layer
  never sees free-text user input (only structured exception facts), and
  its *output* is grounding-checked, but adversarial content embedded in an
  uploaded file's text columns (e.g. a memo field forwarded to the model)
  has not been specifically fuzz-tested.

## Reporting

This is a hackathon submission repository, not a maintained service. If you
find an issue, open a GitHub issue on this repository describing it.
