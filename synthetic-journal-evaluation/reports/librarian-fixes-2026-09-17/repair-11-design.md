# Repairs after iteration 11

Iteration11 used medium reasoning and completed with unchanged source hashes. Mapping4/4 and the outside-essay smoke pass credibly. Native3/6 and release9/12 still fail; no all-pass claim is justified.

## Preserve reviewed quote obligations through punctuation edits

Giant-puppy's first review correctly identified an incomplete source quotation. Its revision changed terminal punctuation but still omitted that punctuation from exact_quote. The existing retained-quotation guard compared the old and new quoted interiors literally, so it missed this repair failure.

Extend only that existing guard: previously reviewed source-quote interiors remain obligations if the current interior differs only in outer whitespace or terminal sentence punctuation. Keep words, case, internal whitespace, markup and other punctuation exact. Require a nonempty core. Matching establishes an obligation, never source authorization: current canonical exact_quote and occurrence binding still use the unchanged strict checks. No first-draft source classification heuristic, automatic rewriting, authority carryover or extra retries. The focused regression fails before the fix because the malformed revision is accepted.

This does not repair Pigeon's false rejection: both current quote declarations in that case already bind fully. Semantic attribution and request completeness stay with the reviewer.

## Supply the real reader message to release review

The release harness supplied the reader message to Muse but omitted capture_source_text when calling reflection_reply. As a result Provenance received an empty current_line. Pass the existing request.message unchanged; exercise the actual draft-to-review pipeline in a FunctionModel regression. This corrects the test harness context without changing ground truth or runtime release rules. Native replay already supplies the reader message, so its remaining failures have separate causes.
