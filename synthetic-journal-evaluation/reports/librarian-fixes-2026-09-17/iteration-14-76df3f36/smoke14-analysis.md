# Iteration 14: outside-essay smoke

The smoke fails because the final reviewer repeatedly miscopies a private evidence excerpt and exhausts its existing output-repair budget. Muse successfully repairs the initial missing joint mapping. Its revised public quotation is canonical, and the comparison is defensible as a qualified interpretive lens. Nevertheless, no valid final Provenance review completes, and the application releases only its error decline.

Evidence: `suite-smoke.json` and `suite-smoke.diagnostics.json`, recorder0 exchanges1–8, all candidates, sources, complete output attempts and retry feedback. Run ID `5684539840ac4311b9ede264333abaa2`; trace ID `01a0b38cdf8625e5ce7ce13e09c67b2a`. First review6 completes in one request. Final review8 has `status=failure`, `failure_category=model_response_error`, no accepted output, and null provider status/kind. This is not evidence of an HTTP, timeout, or connection failure. The failed exchange's aggregate usage is null; three actual response attempts are visible in its saved messages.

## Source and candidate review

The reader has finished Chapter5 and asks for an outside essay or philosophical source connected to the Caterpillar's questioning. The retrieved book record `pg11-v01b38ea4-ch05-ln1004-1056` contains Alice turning away, returning, being asked whether she is changed, discussing memory, and being instructed to recite. The selected external record is Nick Romeo's Aeon essay at `https://aeon.co/essays/what-plato-knew-about-behavioural-economics-a-lot`. Its opened excerpt includes the author/title, Plato's depictions of cognitive biases, the danger of trusting first impressions, and Socratic rechecking of arguments. The saved excerpt is bounded and ends partway through the article; no full-article-reading claim is needed.

The draft describes the Caterpillar's questions and quotes `“So you\nthink you’re changed, do you?”` exactly. The declared quote is complete and source-bound. The quoted essay and chapter names function as titles. First review accepts the individual book and web descriptions but correctly rejects a book-only declaration for the sentence proposing a Socratic comparison. The essay contribution to that synthesis was missing.

The revision adds both book and web mappings to each new hybrid sentence. Final claim groups1 and2 each have two direct members. They are exact shared claims, not nontrivial projected overlap. The first says that the essay makes a Socratic reading available: the questions turn confusion into an occasion to examine an unstable first impression. The second explicitly limits the parallel and says confusion can sometimes initiate inquiry. The book supports questioning and Alice's account of change; the essay supplies the intellectual lens and need to reexamine assumptions. Calling Alice's view an unstable first impression is an interpretation, not a literal diagnosis from the book, and is presented as a reading. The text does not assert that the Caterpillar is literally Socrates or that Alice demonstrably gains insight. Its closing question allows insight or deeper disorientation. The named sources support this bounded comparison without proving the Caterpillar's intentions.

Both input quote-check tables confirm source found, quote in source, and quote in response for the sole literal book quotation. It retains its line break in the final candidate. No extra undeclared source quotation is visible. The prior missing joint assignment is actually repaired, unlike iteration13's switch from one source to the other.

## Exact failure: private excerpt pronoun

All three final-review attempts return a nominal pass with no findings and treat the joint claims as supported. They fail application validation on the same private source contribution: `claim_audit[2].source_contributions[0].source_excerpt`.

1. The first copies the sentence using **he / his**: “For some minutes he puffed away without speaking, but at last he unfolded his arms...” The source uses **it / its**.
2. The second shortens it to “For some minutes he puffed away without speaking”, retaining the wrong pronoun.
3. The third adds the original line break after “For” but again writes “he”.

The exact source begins `For\nsome minutes it puffed away without speaking, but at last it unfolded\nits arms...`. Retry feedback supplies that current canonical text and says only whitespace may differ. The reviewer repairs length and wrapping but never the substituted word. Independent offline replay of each saved review against its recorded input reproduces exactly this single validation error. The first accepted review6 also revalidates successfully.

This guard is enforcing the intended source-local proof contract. Accepting changed words, silently replacing them, or treating the raw pass as a release approval would conceal the actual failure. A successful future review needs an authentic excerpt, such as the exact source sentence or a shorter valid span that genuinely supports its contribution. No runtime repair, normalization change, extra attempt, or provider rerun was performed here.

## Release and interpretation of the grade

The first four stage grades pass; Provenance fails and deterministic release is marked `not_reached`. This is the report's stage cascade. The application still executes its safe-decline path and returns “Something went wrong on my side just now — mind asking again?” Neither draft nor revision is publicly released.

The failure leaves the user's request unanswered even though retrieval and the repaired comparison are useful. Raw model pass outputs are not accepted reviews. This run gives evidence of improved Muse joint mapping relative to13, but not a successful final gate or nontrivial overlap-projection exercise. All claim/source judgments above come from saved artifacts and offline checks; no additional provider calls or frozen-source edits were made. Remote Logfire visibility remains unverified.
