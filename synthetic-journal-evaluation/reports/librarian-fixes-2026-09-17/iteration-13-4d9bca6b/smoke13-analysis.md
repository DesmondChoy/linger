# Iteration 13: outside-essay smoke

The smoke **failed safely**: both Provenance reviews requested revision, so the application returned its generic reliability decline. The revised candidate remained a plausible book/essay comparison, but Muse mapped its central hybrid sentence only to the book, leaving the essay contribution undeclared. This is a real declaration-repair failure. It is not a recurrence of iteration 12's overlap projection defect: no overlapping declaration supplies the missing source here.

Evidence: `suite-smoke.json` and `suite-smoke.diagnostics.json`, recorder 0 exchanges 1–10, especially draft 2, selection 5, review 6, revision 7, and final review 10. Run ID `9e670b22d520412d9d555ce874dc4f4e`; trace ID `01a0b267d00b5bac93b03ef79b5efe17`. All ten recorded agent exchanges succeeded; failure category, provider status, and provider kind are null. No provider outage or content-filter failure is recorded. Both recorded Provenance outputs revalidate locally against their exact inputs without errors.

## Request, retrieval, and selected source

The current reader Line explicitly finishes Chapter 5 and asks to connect the Caterpillar's calm questioning and Alice's confusion to an outside essay or philosophical source. Both reviews receive that actual Line. Emotional preflight allows reflection.

Both Librarian judgments select `pg11-v01b38ea4-ch05-ln0960-1016`. The source contains the opening identity question, Alice's changing sense of self, the demands to explain herself, and the conversation's return to its beginning. Retrieval is relevant and bounded. Serendipity selects Douglas V. Porpora's *The Caterpillar's Question: Contesting Anti-Humanism's Contestations*, DOI `10.1111/1468-5914.00036`, over a broader Pendlebury philosophical-play source.

The canonical web record is bibliographic metadata plus an abstract, not the complete paper. It says Alice cannot answer the identity question; reports the anti-humanist explanation that there is no coherent subject; and contests that denial. It concedes difficulty identifying ourselves while defending the conceptual necessity of a person as a unified center of consciousness. The response's paraphrase—difficulty identifying oneself need not eliminate the person having the experience—is faithful to this abstract. Its philosophical comparison is relevant, although the abstract does not establish the Caterpillar's intentions.

## Draft and first review

The draft gives the exact canonical `“Who are _you?_”`, but also visibly quotes `“I’m not myself,”` while declaring only the first quotation. The second fragment is not covered by any complete exact-quote declaration and is not a faithful complete substring with that punctuation. First review correctly requires a declaration or paraphrase. The application-computed quotation audit detects it rather than relying on the existing quote-check result for the first quotation.

The draft's hybrid claim is:

> That gives your reading a useful tension: the Caterpillar may be testing Alice’s definition of herself, not simply asking her to report a fact.

It is declared only under the web record (`evidence_uses[1].supported_claims[2]`). The abstract supports the philosophical lens but not the entire scene interpretation. Review 6 requests the book mapping or a narrower reflection. Its first two output attempts needed structural-location and quotation-audit repairs; the third completed with these two substantive findings. This consumed three review-model requests within the existing output-repair budget, not three Muse revisions.

## Revised candidate and final review

The revision removes the undeclared second quotation. Its sole literal source quotation, `“Who are _you?_”`, is declared, present in the named canonical book record, and present in the response. The essay's quoted title is metadata, correctly classified as a title. No remaining visible quotation defect was found.

The replacement hybrid sentence is:

> Read alongside Chapter 5, that argument invites a tentative question: is the Caterpillar testing Alice’s answer, or testing the assumption that a person must already possess a complete definition of herself?

This sentence is declared only under book `evidence_uses[0].supported_claims[3]`. The web declarations cover the preceding essay introduction and argument summary, ending before this sentence. Final computed group 3 therefore has exactly one direct book member and no projected web member. The draft likewise had a single direct web member for its hybrid group. The new overlap-aware projection cannot legitimately add a source that covers no part of this occurrence.

Review 10 correctly identifies the missing joint mapping. It accepts the book description and web summary, recognizes the two prior findings as resolved against their old wording, but rejects the current hybrid claim's incomplete source assignment. It asks for both relevant records or removal of the source-dependent framing. This review completes in one request. The private audit marks the book contribution false even while its summary acknowledges a book contribution; that boolean is stricter than the partial-contribution interpretation warrants, but it does not make the release rejection false: the full sentence still needs the web source.

The sentence is reasonably tentative as interpretation. The evidence does not establish that the Caterpillar intends a philosophical test, and the candidate does not unequivocally assert that intention. Thus the concrete failure is incomplete declared support, not demonstrated fabrication of the comparison. Merely switching the hybrid sentence from web-only to book-only does not satisfy joint attribution. A future successful response must preserve both source assignments for the full synthesis or separate bounded claims; this report does not alter mappings, gold, or runtime behavior.

## Release and limits

Native stage grades pass invocation, retrieval, selection, and Muse presentation; fail Provenance review; and label deterministic release `not_reached`. That label describes the grading cascade after the first failure. The application did execute its safe-decline path and publicly returned: “I’m sorry, but I can’t provide a reliable response to that right now.” Neither candidate was released. This protects attribution but leaves the reader's requested connection unanswered.

The final ordinary reflective question is classified as reader reflection; it introduces no distinct new source fact beyond the already reviewed tentative alternatives. There is no evidence of spoiler overflow or a false emotional pause. This run demonstrates correct rejection of an omitted source, but does not live-exercise nontrivial overlapping claim coverage because all relevant groups have direct-only members. Iteration 12's specific overlapping S/S+T case still relies on local regression evidence for the repaired projection. No extra model calls or source changes were made for this analysis.
