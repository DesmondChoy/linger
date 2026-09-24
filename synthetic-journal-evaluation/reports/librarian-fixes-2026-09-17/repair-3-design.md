# Candidate fixes after iteration 3

Runtime stays frozen until the batch completes. No expectation changes are included in these proposals.

## Provenance audit identity

Hume’s revision review repeatedly copied a memory hash with one character missing, despite exact repair targets. Use an application-computed source reference table with a numeric index, source kind and canonical ID. The model returns `source_index` in each source audit; application validation requires every index exactly once and binds findings back to the canonical record. Keep independent missing-claim scanning and named-source contribution checking. Do not normalize IDs, auto-fill audits, accept missing sources, or increase retries. Controlled callers and fixtures migrate together.

This repairs transcription only. The saved Hume review also found unrepaired closing interpretations, so correct indices alone would not establish a successful response.

## Muse response repair

Roses and Hume both retain redundant, source-dependent closing interpretations after repairing the particular opening or middle sentence cited by review. Prefer short requested source accounts, the essential comparison, and one open question that does not retell source facts. During a mapping repair, simplify the whole answer first and regenerate its complete declarations; remove redundant closing interpretations instead of preserving unmapped summaries. Preserve requested exact quotations, source corrections, public citations, and useful reflection. A question containing a remembered factual premise still needs that premise mapped; a non-factual invitation to reflect does not.

Keep speaker assertions distinct from narrator facts, and identify who acts or loses a choice before interpreting the passage. Farm’s final response wrongly says “Napoleon’s loss of shared decision-making” where the animals lose their say; its surrounding account is otherwise correct. This is a response-quality observation separate from the strict adopted support-set failure.

## Verification

Run deterministic source-reference binding and complete audit coverage regressions, including supplied/stale reference tables, invalid or duplicate indices, missing sources, and wrong-source support. Run relevant Muse/Provenance integrations. Then use the next reserved live batch to check whether the repairs change observed behavior. Local schema checks do not establish semantic review accuracy.

Evidence: iteration-03-4715c97d/suite-6.json, suite-7.json, suite-8.json and their native analysis reports. No extra live calls were made for this design.
