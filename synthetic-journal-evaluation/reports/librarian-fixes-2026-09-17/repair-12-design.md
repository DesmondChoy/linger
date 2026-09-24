# Repairs after full iteration12

The full eleven-suite set plus mapping controls completed with unchanged source hashes. Strict results are19/29 native Scenes,10/12 release cases,11/12 direct cases,2/4 mapping controls and a failed outside-essay smoke. Semantic review also found an Animal Farm wrong-record approval and a missed Roses past-cause claim. Passing subsets do not authorize commit/push.

## Mechanical Muse repairs

The Pigeon release revision introduces a new quote whose declaration omits its terminal period. Since this new text was absent from the previous review's source-quotation inventory, retained-text checking cannot catch it. Add a conservative first-draft and revision check only for an explicitly declared, canonically valid exact_quote: if its only uses are within balanced double quotes with identical words/interior characters but different edge punctuation/whitespace, require the complete displayed source span. Suppress the heuristic when the declaration already binds a full quoted occurrence or has a literal unquoted occurrence; larger proposed wording and changed words remain semantic review. Do not assign sources, rewrite strings or waive exact source matching. The red regression accepts the malformed quote before this fix.

Restore the previous exact-membership behavior for punctuation-only retained quotations before attempting nonempty-core punctuation equivalence. The new regression demonstrates the lost obligation for an unchanged question mark. Different punctuation-only spans remain unrelated.

Alice's explicit draft repeatedly copies an extra leading space into supported_claims. Offer an optional exact reply-span repair hint when removing only outer whitespace yields a bounded match. Preserve the invalid-candidate rejection until the model explicitly corrects its declaration. Keep word and numeric boundaries, do not normalize actual claims or source quotations. The red regression lacks the suggested literal span before the change.

## Overlapping claim declarations

The smoke exposes a separate projection defect: exact-string grouping omits sources that explicitly cover part or all of a group at a different mapping granularity. A web declaration covers S+T, and a book declaration covers S. The reviewer is incorrectly told that S has only book support. Preserve original whole-claim groups, derive source membership and limited coverage from actual response occurrences, and expose that coverage explicitly. A book mapping of S must not gain authority over T. Do not split meaningful causal/comparative claims into isolated fragments or silently accept their conclusions. The independent implementation design records the occurrence and audit rules before source edits.

All changes retain existing role boundaries, current model/settings, repair budgets and frozen expectations. Further semantic failures remain failures; no approval is inferred from mechanical validity.
