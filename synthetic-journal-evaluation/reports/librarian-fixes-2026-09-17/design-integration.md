# Integration sketch

`librarian_search(work_id, book_version_id, max_final_evidence=5)` builds a request from the bound reader message. The application retrieves `confirmed_reading()` or the exact passage grant and uses that scope directly. The model no longer repeats chapter completion in its tool arguments. `LibrarianRequest` and `build_request` lose `reading_boundary`; all internal callers migrate. Explicit completed/started parsing remains application-owned; the notebook demonstration translates its human-entered chapter state before binding scope. No speculative model-controlled narrowing selector is introduced.

Boundary output separates uncertainty from candidate authority. A candidate must account for plausible event alternatives and point to exact reader details distinguishing the event. Memory support cannot transform the same ambiguous description into certainty. Existing one-role Librarian architecture and private full-work search remain.

Private retrieval retains candidates from independent signals and scores bounded token windows, preserving original canonical citation text and IDs. Query omission fallbacks remain. Public release still needs scope checks, evidence assessment, Muse declarations, Provenance approval, and deterministic validation.

Provenance gains input-aware output repair within its existing bounded run, plus explicit compact source-use/claim-support auditing. It cannot authorize a reply with invalid finding locations or unresolved unsupported mappings. Other Provenance tasks retain their own typed contracts.

Evaluation repairs preserve adopted scenario bytes. Support completeness and excess unsafe evidence become separate checks; exact identity, quotation, scope, and source integrity checks remain. Correct canonical text comparison replaces incompatible raw whitespace comparison. Changes to the standalone frozen benchmark's intended coverage require an explicit evidence-based rationale, not a score-only edit. Historical missing adoption is not fabricated.

The user permits at most twenty new live batches, including targeted batches. Before each batch record the source revision and selected suites; count failures and partial executions. A complete eleven-suite pass is required before the authorized commit/push. Local tests and cached retrieval probes do not consume live batches. Built-in model retries are counted as part of their suite, not hidden additional evaluations.
