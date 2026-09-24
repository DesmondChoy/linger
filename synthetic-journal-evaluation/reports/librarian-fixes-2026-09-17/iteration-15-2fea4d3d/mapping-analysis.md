# Iteration 15: mapping controls

The strict result is **3/4**. The complete joint-support positive control is falsely rejected: the reviewer correctly recognizes collective support, then incorrectly requires each contributing record to support the whole sentence. The other three final judgments are credible. No provider failure occurred.

Reviewed all four original typed inputs, every model output and retry, final reviews, grades and recorded usage in `suite-mapping.json` (trace `01a0b3aed3e54e7fbf9a2bc830300c50`). Each complete input is byte-value equivalent to its iteration14 JSON value, including computed projections. Independent offline revalidation accepts all four final reviews against their original inputs. Mechanical acceptance does not establish semantic correctness.

| Case | Requests | Assessment of all attempts |
| --- | ---: | --- |
| Wrong record | 2 | First review falsely passes by copying the memory/verse passage from the later available record into an audit for the earlier declared record. Named-source literal validation rejects this. The retry correctly marks the declaration noncontributing and the complete claim unsupported, asking to remap to the later record or remove the unsupported detail. Final rejection is credible. |
| Correct record | 1 | Pass cites an authentic continuous excerpt containing Alice's memory complaint and report that the verse came out differently. Both clauses are supported by the declared later Chapter5 record. |
| Missing joint contribution | 1 | The earlier declared record genuinely supports the identity/size clause; the review marks that contribution true but the complete claim false because the later verse clause lacks its declared source. Correct distinction between a useful partial contribution and complete support. |
| Complete joint contribution | 2 | First review correctly identifies two relevant records and collective support but emits declaration1 twice. The application rejects the duplicate membership. Retry fixes the duplicate, keeps both contributions true and the complete group supported, yet still issues an unsupported-claim finding solely because declaration0 does not independently support the verse clause. This is an overstrict false rejection, not a defective candidate. |

## Complete joint-support failure

The unchanged candidate says: “In Chapter 5, Alice struggles to explain who she is after changing size, and later reports that a familiar verse came out differently.” It maps the complete sentence to both `pg11-v01b38ea4-ch05-ln0960-1016` and `pg11-v01b38ea4-ch05-ln1004-1056`.

The first record contains Alice's difficulty explaining herself and her statement that being many different sizes is confusing. The second contains her inability to remember things as before and her report that the familiar verse came out differently. The application projects one complete group with two direct members, each covering the same sentence. This is the intended collective-support contract, not an accidental overlap projection.

The final review explicitly says the two records together support the complete claim, with `supported=true` and both `contributes=true`. Its sole finding nevertheless calls declaration0's full-span mapping overbroad and asks to narrow or remove it. It also claims declaration1 supports the complete claim, although that later record does not contain the earlier difficulty explaining who she is. The required repair follows a mistaken per-record completeness standard. The existing skill explicitly separates contribution from completeness, allows a member to support a relevant part, and says not to demand that every contributing source prove the entire claim (`src/linger/agents/provenance/skills/candidate-review/SKILL.md:198–239`). Expectations should remain unchanged.

The typed validator appropriately permits findings alongside a supported group because a genuinely irrelevant direct mapping, attribution defect or other independent problem can still warrant revision. Automatically discarding this finding solely because the group is supported would broaden authority. Any future repair must preserve that distinction; this run establishes a semantic consistency failure, not justification for auto-approval.

## Repair15 feedback observation

The wrong-record retry includes the new `literal_source_context` field, but its value is null. The failed excerpt has no appropriate unique same-record anchor for a short hint. The complete named canonical source and revised repair instructions are present; the second attempt correctly stops borrowing the later passage. This is evidence that rejection and repair still work, but it does not isolate the new short hint as the cause of improvement. There is no he/it substitution in these controls. The complete-joint retry concerns duplicate group membership rather than literal copying, so the new short excerpt hint is not exercised there either.

Usage is complete for all four cases; request counts are 2/1/1/2 within existing output-repair budgets. All failure-category and provider-status fields are null. No provider call, source or expectation edit, historical rewrite, or retry was performed for this analysis.
