# Provenance mapping controls — iteration 9

The higher-effort run passes **3/4 controls**, regressing from iteration8's4/4. The missing-joint-contribution negative is incorrectly approved. Every current source/claim input is unchanged from iteration8; higher effort does not establish reliable collective entailment.

| Control | Result and semantic assessment |
| --- | --- |
| Wrong record | **Credible pass: revise.** Review correctly identifies that lines960–1016 omit the claimed memory and altered-verse statements, even though the correct later record is available. Group support and contribution are both false, with a grounded unsupported-claim finding. This time no application repair is needed. |
| Correct record | **Credible pass: pass.** The same memory/verse statement names lines1004–1056, which contains both details. Its authentic memory excerpt is a valid partial proof; the complete named record supplies the verse account. |
| Missing joint contribution | **Supported failure: incorrect pass.** The candidate says Alice struggles to explain identity after changing size **and later reports a verse coming out differently**, but declares only lines960–1016. Review copies the authentic “I can’t explain _myself_” passage, marks that contribution true, and incorrectly marks the whole group supported. The later verse clause remains unsupported by any declared source. |
| Complete joint contribution | **Credible pass: pass.** Both records are declared for the compound claim. Review accepts one collective group and authentic separate identity/verse excerpts. Neither member is required to contain the other's clause. |

The failed case shows the exact limit of source-local private proof. Its excerpt belongs to the correct declared source and supports part of the sentence, so the mechanical validator correctly accepts the audit shape and binding. The semantic error is `supported=true` for the entire group despite the missing verse contribution. Rejecting all partial excerpts would also break legitimate joint support; inventing another source declaration would change the candidate. There is no evidence that a duplicate-member, unknown-ID, whitespace or public-quotation defect caused this failure.

All four accepted reviews used one model request, with no recorded repair prompts. Iteration8 used2,2,1,1 requests: its wrong-record unsafe first approval was caught by the source-local proof guard, while its missing-contribution negative correctly distinguished a real partial contribution from incomplete collective support. Iteration9 handles wrong-record directly but loses the latter distinction. One run does not establish that higher reasoning inherently harms accuracy; it does demonstrate that this configuration is not an all-pass fix.

An offline read-only probe compared candidate, canonical book/connection evidence, current Line and policy/context to iteration8 and found exact equality for each control. All four accepted reviews pass `ProvenanceInput.validate_review`, including the semantically wrong approval. This is expected: the validator binds inventories and excerpts but does not prove natural-language entailment. The frozen expected negative decision and original recorded failure remain unchanged.

These controls contain no visible quotations, no uncovered substantive text, no Muse revision and no reader release. Their result does not settle the Roses/Hume full-conversation issues. Preserve this failed control for any next authorized experiment and require the missing-contribution case to reject for its actual unsupported second clause while the complete joint case still passes. No source, grader, prompt or retry budget was changed during analysis.

Evidence: [complete inputs, audits and raw messages](suite-mapping.json), [iteration8 comparison](../iteration-08-a0b8741f/mapping-analysis.md), and [high-effort reservation](reservation.json). No provider calls were made for this review.
