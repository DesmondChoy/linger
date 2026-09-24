# Muse revision repair for iteration 15

The iteration 14 identity reply repaired its literary interpretation but introduced an unbound, altered quotation, `as [she] used`. The Pigeon revision introduced a new quoted `little girl` fragment. Existing Muse checks validate declared quotations and retain quotation obligations already classified by Provenance. They correctly do not infer that every new quoted phrase is source text: titles, proposed wording and scare quotes need semantic judgment.

Keep the same reusable Muse Agent, output contract, three output-repair budget, one reviewed rewrite and final Provenance/release gates. Do not duplicate Provenance's quotation inventory in Muse or classify quotations by lexical similarity. No source or expectation changes belong to this repair.

## Chosen change

Replace the existing revision guidance with a concise repair discipline: preserve the requested answer and complete required quotations; when rewriting an optional source fragment, prefer a supported paraphrase rather than introducing another quotation; any retained or new source quotation still needs its own complete canonical binding. This is not a ban on fresh quotations or on titles, suggested wording or scare quotes. Keep whole substantive claim mappings aligned with the final response. Keep a source's findings separate from open reader-facing possibilities; a current question about a cause is not confirmation of an actual past motive, and later self-explanation is not evidence of the earlier cause.

Extract the existing reviewed-quotation check into `quote_repair.retained_quotation_errors(response, evidence_uses, reviewed_quotes, source_texts, valid_quotes, verified_session_lines)`. It keeps exactly the current prior-review classification and occurrence-binding rules. Improve only its retry diagnostic: report the complete current quoted span and each currently declared source whose exact mapped claim covers that occurrence. Include that named source's canonical text and an optional literal quote suggestion using the existing conservative matcher. Unknown IDs or wrong source kinds supply no canonical text. The application never copies a suggestion, invents an assignment or treats a matching excerpt as semantic proof.

`validate_muse_output` consumes those errors together with its existing claim, identity, location and quotation checks. The model repairs within the existing retry budget and Provenance independently evaluates the resulting answer.

## Verification and limits

A cheap failing-before regression exercises a reviewed but unbound source quotation whose declared claim identifies its current source. The diagnostic must identify that source, provide a literal canonical suggestion and preserve the untouched requested quotation and other claims through a real FunctionModel output-repair round. Negative cases verify that an unrelated/unknown record is not offered as authority and that unreviewed fresh or proposed wording retains the existing semantic boundary.

Prompt wording cannot be proved semantically effective by asserting that its text exists. The paid iteration 15 review must inspect actual new quotation behavior and Roses' personal-cause framing. Existing quotation and claim-retention regressions remain authoritative; this change does not claim to mechanically detect the fresh identity or Pigeon fragments.

## Local evidence

All three new tests in `tests/test_muse_reviewed_quote_feedback.py` failed before the implementation: the old diagnostic lacked the complete quoted-response field and current declared source details, and the FunctionModel repair could not consume the literal suggestion. After the change, those tests and adjacent Muse, quotation, claim retention and revision suites pass: **119 tests and 9 subtests**. The actual Agent repair requires two model-function calls, preserves the requested first quotation and its declaration unchanged, and updates the second quotation and all its mapped claims. An unknown current source cannot borrow canonical text from an unused available record. Existing tests continue to permit genuinely unclassified new/proposed wording and preserve strict source, punctuation and claim checks.

The prompt change deliberately does not assert automatic prevention of iteration 14's fresh fragments. The next live review must establish semantic effectiveness; no provider was called during this implementation.
