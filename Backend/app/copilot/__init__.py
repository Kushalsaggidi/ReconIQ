"""ReconIQ Reconciliation Copilot.

A read-only, grounded Q&A layer over an already-completed reconciliation job.

    DETERMINISTIC ENGINE -> VERIFIED RESULTS -> READ-ONLY TOOLS -> COPILOT -> HUMAN

Nothing in this package can write to a job, a transaction or an exception. It
only ever reads through :mod:`app.storage.repository` and
:mod:`app.services.results_service`, the same modules the REST API already
uses -- there is no separate, parallel data-access path and no raw SQL access
for the model.

The engine establishes the truth. The Copilot explains the truth. The Copilot
never changes the truth.
"""
