# Private boundary source binding after iteration 5

Implemented after iteration 5 completed with unchanged source hashes. The change preserves authority, original Ground truth, provider stages and retry budgets. No live call was made for implementation.

## Observed failure

In `iteration-05-8f52910d/suite-9.json`, `douglass-spoiler-inference` binds the Auld teaching-prohibition memory to `pg23-vd3f08ac3-sec06-ln0971-0980`. The model calls it a Chapter 6 teaching passage, but the canonical record is Chapter 3 and concerns a man sold to Georgia after speaking frankly to Colonel Lloyd. The actual Auld passage, `sec09-ln1346-1385`, is present in the same input. The wrong reference appears in both boundary responses; the intervening inventory retry only removes an invented `sec03-ln?` ID. The correct current copybook event still produces the intended Chapter 7, concealing invalid prior-memory authorization behind a correct ceiling.

ID existence, exact copied reader spans and candidate inventory cannot establish that the model actually bound its reason to the selected record. This differs from earlier failures involving additional valid records.

## Smallest useful contract

Introduce a private typed `BoundaryEvidenceAnchor` with `evidence_id` and nonblank `exact_quote`. Replace candidate `supporting_evidence_ids` with `supporting_evidence: tuple[BoundaryEvidenceAnchor, ...]`. Each quote is a short contiguous excerpt copied from that exact supplied record, chosen to support the stated memory match, current occurrence or optional connecting evidence. The existing semantic explanation remains necessary: exact membership proves binding, not relevance or entailment.

Memory assessments and event occurrences retain their evidence-ID references. Candidate validation already requires all grounded-memory and selected-current-event IDs in the top-level support; migrate those checks to the typed anchors. Validate every top-level anchor, including optional bridge support. Do not derive support solely from memory plus selected occurrence: an independently useful connecting record is an intended third category and must remain expressible.

Uncertain output grants nothing and keeps its current private memory-assessment shape without required quotes. This repair concerns candidate authorization, not forcing another proof shape on a safe clarification. Preserve the separate `PassageInferenceDecision` contract. Unrelated inventory records and ruled-out occurrences need no top-level support quotes unless actually selected as authorization support. No old candidate support-ID compatibility field remains for controlled callers.

This top-level choice avoids repeated quotations in each memory and occurrence, preserves optional connecting evidence, and requires the fewest caller migrations while binding every actual permission anchor.

Candidate indices alone are insufficient. They reduce copied identifier length but a valid wrong index could still receive the teaching explanation. Exact quote binding is the material safeguard; adding indices as well would expand this repair without proving more.

## Validation and repair

Validate each anchor against the request's canonical `full_work_candidates` mapping: the ID must exist and `exact_quote` must be a literal substring of that record's text. Preserve line breaks and Unicode; do not normalize, trim, fuzzy-match or silently change IDs. Reject blank quotes. A quote from a different supplied record is still invalid under the cited ID.

Collect quote mismatches together with existing inventory, duplicate-reference, missing grounded-memory support and missing selected-event support errors before output validation, with exact field paths and the cited canonical ID. Keep the single existing bounded repair and the same Librarian Agent. Feedback asks the model to re-check the intended record and quote, not to copy an arbitrary phrase from the currently cited wrong record. A repeated mismatch still fails closed; uncertainty remains an allowed response. After typed validation, repeat the binding check at the application boundary so injected decisions cannot bypass it.

For the saved Douglass error, an authentic Auld excerpt attached to the Chapter 3 ID must fail. Rebinding that excerpt to the supplied Chapter 6 record must pass structural binding. Copying a real but irrelevant Chapter 3 sentence would pass substring validation but remain semantically wrong; the prompt and review must continue to assess whether the quote supports the memory. This change is not an independent semantic judge.

## Authority and caller migration

Quotes stay in the private boundary decision and evaluation trace. Resolve authorized records internally; expose only existing work/version, chapter and support-location metadata in the public route handoff. Do not add quote text to `librarian_route` or give private candidate access to Muse. Preserve confidence gates, prior-memory assessment, ambiguity comparison, identity checks and current inclusive chapter bounds.

Migrate controlled model constructors, capability validation, orchestration, boundary skill examples, evaluation boundary parsing and boundary fixtures together. The output schema changes its existing skill fingerprint automatically. Historical saved artifacts remain unchanged; do not add runtime compatibility solely to replay obsolete internal shapes. The independent session-passage contract remains unchanged: this failure was chapter authorization, and the present change must not accidentally widen passage grants.

## Cheap discriminating regressions

1. Wrong valid ID plus actual Auld quote fails; correct ID plus that same quote passes.
2. Correct selected-event ID plus quote copied from another occurrence fails, as does a fabricated or punctuation-altered quote.
3. Inventory faults and quote mismatches appear in one repair response; no second-stage retry is needed to discover another known structural fault.
4. Repeated wrong binding exhausts the existing repair and grants nothing; a corrected response can grant the same intended ceiling.
5. Typed uncertainty without grounded evidence still works; a harmless personal aside creates no mandatory quote or retrieval requirement.
6. Public handoff serialization remains content-free even when private anchors contain full canonical phrases.
7. A quote that is exact but irrelevant is explicitly documented as a semantic limitation; do not create a test implying substring membership proves relevance.

After local checks, the next authorized full live batch must show correct memory-source binding, valid specific-stop grants, genuine ambiguous controls and no exposed private quote. A mechanically corrected fixture cannot establish live semantic reliability.


## Implementation checkpoint

Candidate support now uses typed `BoundaryEvidenceAnchor` values at `supporting_evidence`; controlled callers and replay parsing migrated, and the candidate ID-only field was removed. Memory and event references retain their existing IDs. Exact named-record quotation binding, duplicate/unknown references, missing memory/current support and inventory faults use the existing aggregated repair. The application repeats binding checks before granting scope. Optional connecting evidence remains accepted. Uncertainty and session-passage outputs retain their distinct existing shapes.

The new wrong-valid-record and obsolete-interface regressions failed before implementation. Final focused verification passed **211 tests and 42 subtests**, including fifteen source-binding regressions, actual application denial of an injected mismatched quote, successful correct binding, and private-quote exclusion from handoff serialization. See [local-boundary-source-binding.log](local-boundary-source-binding.log). The owned diff passes whitespace checks. Full repository integration and live behavioral verification remain the root agent's responsibility; exact substring validation still does not independently prove semantic relevance.


## Proposed correction after iteration 6

Runtime remains frozen while the batch finishes. Pigeon and Douglass select semantically correct records but repeatedly flatten line breaks in the private anchor. Offline replay of the actual binding validator identifies the private excerpt as the remaining fault; folding whitespace with `" ".join(text.split())` makes every rejected saved excerpt match its own named record. Pigeon repairs two excerpts but repeats the main quotation's space/newline mismatch; Douglass switches excerpts and repeats the same formatting error. Both therefore fail closed before answer retrieval. Farm's separate positive failure never reaches boundary inference: Muse pauses despite emotional preflight returning `continue_reflection`.

The agreed correction is limited to private proof: rename `BoundaryEvidenceAnchor.exact_quote` to `source_excerpt` and test membership after folding whitespace in both strings. Preserve words, case, punctuation, Unicode characters and Markdown markup. The source ID remains required and the excerpt must match that specific canonical record; a phrase from another record still fails. Blank strings still fail. This does not change public exact-quotation verification, which remains character-exact. It also does not turn excerpt membership into proof of semantic relevance.

Migrate all controlled candidate fixtures and examples to `source_excerpt`, removing the obsolete private field rather than keeping compatibility. Add regressions for collapsed line wrapping and repeated spaces passing, with changed words/case/punctuation/markup and wrong named record still rejected. Preserve aggregate repair, optional bridge anchors, typed uncertainty, passage-only output, chapter bounds and content-free handoff. The output schema fingerprint changes automatically. No source implementation changed during this frozen-batch design review.

Evidence: `iteration-06-0b927fa3/suite-4.json` and `suite-9.json`, positive boundary exchanges and both tool attempts; native reviews explain the upstream failure and unexercised response path. The offline whitespace-membership check establishes these specific formatting differences only; it is not a new live evaluation result.

## Applied correction after iteration 6

After the root confirmed batch completion and unchanged sources, the private anchor field became `source_excerpt`; there is no compatibility field. Named-record membership folds whitespace runs on both sides and preserves all other characters. Both pre-validation repair and the application recheck use this same binding check. Existing identity, duplicate, memory, selected-occurrence, inventory and grant constraints remain. The schema, skill and repair message now request a concise contiguous excerpt and explicitly prohibit correcting original pronouns or paraphrasing. Public quotation code and expectations did not change.

Two whitespace acceptance tests failed before the implementation. The adjacent run passed 247 tests and 17 subtests; its sole failure was an instruction-resource snapshot mismatch caused by concurrent Muse skill editing. The isolated resource test passed in a fresh process. Logs: `local-boundary-source-excerpt.log` and `local-boundary-source-excerpt-resource-recheck.log`. The final source-binding suite, including unknown IDs and literal backslash-n rejection, is recorded separately in `local-boundary-source-excerpt-final.log`.

The reproducible offline probe `probe-private-source-excerpt.py` validates both retained iteration-6 candidate attempts from Pigeon, Douglass, Alice and Keller after renaming only the field. Pigeon, Douglass and Alice no longer have binding/inventory errors. Keller still fails: both attempts substitute “its element” for canonical “his element”; the second also introduces literal backslash-n characters. See `probe-private-source-excerpt.json`. These checks reuse saved outputs and do not constitute a new live result or establish semantic relevance independently.
