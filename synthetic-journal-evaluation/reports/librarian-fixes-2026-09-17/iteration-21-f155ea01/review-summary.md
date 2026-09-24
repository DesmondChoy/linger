# Live rerun 21

The newly authorized full batch completed all 12 suites with three concurrent workers. No HTTP 429 appears in the saved exchanges or diagnostics. This is consistent with restored API availability after the suspected credit issue; it does not establish the billing cause of earlier failures.

| Evaluation | Iteration 18 | Iteration 20 | Iteration 21 |
| --- | --- | --- | --- |
| Native scenario Scenes | 26/29 | 2/29 | 23/29 |
| Native judgments | 28/32 | 2/32 | 25/32 |
| Direct retrieval | 12/12 | 4/12 | 12/12 |
| Strict answer release | 12/12 | 0/12 | 11/12 |
| Claim mapping | 4/4 | 1/4 | 4/4 |
| Cross-source smoke | Pass | Fail | Pass |

These are original automated grades. Iteration 18 remains the strongest recorded full batch, but runtime and expectation changes between 18 and 21 prevent treating that comparison as a controlled regression test. Runtime, model and adopted expectations were held fixed from 20 to 21; only the run-budget driver changed to permit the one additional authorized batch. The model remained openai:gpt-5.6-luna with medium reasoning.

## Remaining failures

- **Rabbit answer release:** the proof reviewer repeatedly exceeds its 800-character excerpt limit. The explicit boredom and watch clauses span 899 raw characters in the source; requiring a single short contiguous excerpt to cover this compound claim creates a contract conflict. The draft also contains a separate unsupported riverbank detail. See [independent diagnosis](rabbit-proof-representability.md).
- **Alice explicit grounding:** the reviewer repeatedly invents a member outside the supplied claim group. Repair never produces a valid review. The candidate also has an undeclared optional quotation with altered punctuation.
- **Douglass spoiler inference:** the proposed evidence inventory omits an earlier-memory anchor, then repair adds a later Chapter 10 passage while proposing Chapter 7. Validation blocks release before any grant.
- **Farm spoiler inference:** the Chapter 5 ceiling is correct, but the required passage recognizing the dogs as the earlier puppies is still missing from selected support.
- **Keller explicit grounding:** the correct exact answer is released, but an extra grounding call fails after two successful ones. A separate Serendipity discovery call also exhausts malformed-output repairs. These are workflow failures, not missing corpus evidence or credit errors.
- **Roses, two Scenes:** authentic corrective evidence contradicts the reader's premise, but the connection test's closed evidence allowlist rejects it. This remains a separate pending expectation proposal; no new Ground truth was adopted. One response also has an unmapped source-limit conclusion.

## Passing grades that need attention

The answer-release identity case attributes the Caterpillar's “Explain yourself!” command to Alice through its introductory wording. Farm's personal response turns the lead's reported claim about carrying the workload into an unqualified concession. Both pass automatically, so automated counts overstate semantic reliability. A private Pigeon retrieval explanation also adds a mushroom cause absent from its selected evidence, although the selected passages answer the requested neck/egg question.

Five specific-event cases obtain correct independently checked chapter ceilings. Six ambiguous controls safely clarify. Douglass stops before the independent gate. No unauthorized ceiling or evidence disclosure was found across the 23 book-flow Scenes; no negative independent event gate was exercised. Keller sec012 corresponds to Chapter 10, and sec011 to Chapter 9.

## Verification and disposition

All 222 launch source hashes match their completion snapshots and the independently checked files. All 24 scenario authority hashes are unchanged. All eight native analysis reports validate and render; the report index now contains 135 unique entries, preserving the previous 127. Every one of the 29 Scenes and all component cases received semantic review.

The cap-only driver change passed 10 tests plus 8 subtests. The earlier application checkpoint of 1,904 tests plus 670 subtests is historical and was not rerun for this verification-only batch. No runtime, prompt, model or Ground truth changes were made during this rerun. No additional provider calls were used for analysis. Remote Logfire traces were not independently read back.

The additional authorized batch is complete: 21 reservations are recorded, and no iteration 22 was launched. The all-pass condition remains unmet, so no commit or push was performed. Beads tracks the remaining defects, including the newly isolated excerpt contract issue in linger-9oqp.20.

Detailed reviews: [native scenarios](native-analysis.md), [direct retrieval](direct-analysis.md), [answer release](component-analysis.md), [mapping and smoke](component-mapping-smoke-analysis.md), [spoiler boundaries](boundary-analysis.md), [independent trail audit](independent-trail-audit.md).
