# Iteration 17 direct retrieval review

**11/12 cases produce correct evidence outcomes; one fails before a usable evidence judgment.** Independently reading each successful selection and strength explanation supports the recorded sufficiency or abstention. The failed `exact-caucus-quote` case returns `evidence_judgement_unavailable`, not an incorrect claim that the passage is absent. Its underlying exception is not retained in the saved direct artifact or log, so this review cannot identify the cause.

| Case | Selected canonical source | Independent assessment |
| --- | --- | --- |
| rabbit-watch | Chapter1, lines62–92 | Watch/waistcoat-pocket surprise and curiosity directly explain pursuit. Credible sufficient selection. |
| drink-me | Chapter1, lines165–192 | Exact label DRINK ME is present. Credible sufficient selection. |
| pool-of-tears | Chapter2, lines375–401 | Narrator identifies Alice's tears from when she was nine feet high. Credible sufficient selection. |
| caucus-prizes | Chapter3, lines553–587 and578–617 | Everyone wins; comfits go around, and Alice receives her own thimble. Both passages contribute to the compound question. |
| giant-puppy | Chapter4, lines906–929 | Correct passage: Alice holds out the stick, dodges behind and runs around the thistle, and escapes while the puppy rests. **Private reason has a factual wording error:** it calls this throwing the stick; the selected text says she holds it out. Retrieval is sufficient, but that inaccurate detail must not be repeated in a released answer. |
| identity-change | Chapter5, lines960–1016 | Explicitly ties inability to explain herself to repeated changes and confusing sizes. Credible sufficient selection. |
| father-william | Chapter5, lines1004–1056 | Caterpillar commands the named poem and Alice begins it. Credible sufficient selection. |
| pigeon-serpent | Chapter5, lines1179–1219 | Neck and egg-eating explain the Pigeon's mistaken classification. Credible sufficient selection. |
| identity-theme | Chapter5, lines960–1016; Chapter2, lines327–360 | Direct self-explanation dialogue plus remembered knowledge/voice tests support the qualified literary relationship. This run uses the original required alternative; it does not exercise an alternative-only recall pass. |
| exact-caucus-quote | No usable result | `kind=failure`, `error_code=evidence_judgement_unavailable`, `retryable=true`. Strength and evidence metrics are null. Genuine execution failure; do not classify as retrieval insufficiency without the missing underlying trace. |
| future-cheshire | No selected evidence | Correctly withholds road advice absent from supplied bounded evidence, without confirming a later location. |
| absent-spaceship | No selected evidence | Correctly declines to invent a location for an unsupported event. |

The successful results have recall1, precision1, resolving citations and no evidence beyond their chapter ceilings. Summary means exclude the failed row's unavailable evidence metrics; their value1 does not mean all12 executions succeeded. Strength accuracy is11/12. All claims here concern the direct retrieval workflow, not Muse release or final quotation fidelity.

Evidence: `suite-direct.json`, `suite-direct.status.json`, `suite-direct.log`. No provider calls or historical changes were made for this review.
