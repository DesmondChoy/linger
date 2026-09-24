> Historical handoff after iteration 20. The user subsequently authorized one additional live batch. See the [current iteration 21 review](iteration-21-f155ea01/review-summary.md) for its completed results. The original findings below are preserved.

# Librarian evaluation repairs: final handoff

Stopped after the 20th authorized live iteration. The complete strict and semantic goal was not achieved, so changes remain uncommitted on `librarian-all`; nothing was pushed. The final local checkpoint passes1,904 tests and670 subtests.

## Last three complete batches

| Iteration | Native Scenes | Native judgments | Direct | Release | Mapping | Smoke |
|---|---:|---:|---:|---:|---:|---|
|18|26/29|28/32|12/12|12/12|4/4|Passed|
|19|23/29|25/32|12/12|6/12|4/4|Failed|
|20|2/29|2/32|4/12|0/12|1/4|Failed|

These are separate observed outcomes, not a combined best-case pass. All final iteration 20 suites completed. HTTP 429 dominates20; code improvements cannot be claimed live-validated by paths that never ran. All 222 frozen source hashes match within each of these batches. Model remains `openai:gpt-5.6-luna`, medium. Concurrency was 6 for 18/19 and 3 for 20; lower concurrency did not eliminate429, whose specific provider cause is absent from saved metadata.

## Completed changes in this continuation

- Boundary inventory accepts redundant repeats only in the non-selected inventory while still rejecting unknown/missing IDs and conflicting occurrence assignments. Saved Douglass failure validates after this narrow repair; its wrong-source first attempt still fails.
- Boundary guidance distinguishes final stopping occurrence from completed background, retains necessary continuity evidence and reconciles complete canonical IDs during repair. Required evidence and independent event checks remain intact.
- Muse and Prove guidance clarify contained quotations, explicit mappings for interpretations and source-bearing introductions, correctly scoped evidence limits, and preservation of subjects/attitudes/modality in paraphrases.
- Direct evaluation saves actual per-case planning and judgment exchanges, including provider failures. The batch driver runs bounded parallel suites once per reservation with durable results.
- Existing approval2 now permits Douglass’s already-authored pit quotation as optional Chapter7 support. Both required anchors and the safe ceiling are unchanged. The exact originals and successor adoption receipt are archived; prior grades are preserved.

## What remains unresolved

Provider429 prevents final end-to-end validation. Source grounding and review reliability also remain imperfect independently of those provider failures: prior batches show wrong-subject paraphrases, unmapped interpretations, overstrict evidence-limit findings and invented or incomplete candidate inventories. Final iteration 20 still has a private caucus explanation that borrows an unseen thimble presentation and a possible Alice personal-reflection overreach. Automated passing grades are not uniformly semantically clean.

The final batch contains no successful book-scope grant; its ambiguous-path safe fallbacks are not evidence that normal boundary reasoning succeeded. The smoke test fails before retrieval. Some release reviews pass safe unavailable-search replies, which are correctly retained as failed book-answer cases. Full local test success does not settle these model judgments.

The separate Roses optional corrective-evidence proposal remains unadopted; its earlier human question has no recorded answer. Sol comparison was not approved or run. No new allowance for live iteration 21 exists.

## Evidence and follow-up

Final folder: `iteration-20-2f76d7ae/`. Start with its `review-summary.md`, then the component analyses and `summary.json`. Earlier final-run comparisons are in `iteration-18-c15a6da6/` and `iteration-19-c264f342/`. `report-index.json` links the native review artifacts; `live-budget.json` and `decisions.tsv` record reservations and decisions. Validation log: `local-tests-repair-20.log`.

Beads follow-ups: `linger-9oqp.17` tracks provider availability and the need for new run authority; `linger-9oqp.18` tracks unresolved semantic validation. `linger-9oqp` stays incomplete. Existing user changes were preserved; the index has no staged changes. Commit and push, including required Beads sync, remain conditional on an actual complete pass.

Attention: collaboration reviewers independently audited source/authority hashes, report accounting and semantic outputs. Inspect the misleading passes and the unexercised final repairs described above; do not interpret missing provider observations or precision on empty evidence as success. Final audit receipt is `iteration-20-2f76d7ae/independent-trail-audit.md`.
