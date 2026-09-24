# Iteration17 design: declared-source context beside each claim member

Status: implemented after root closed iteration16 and verified all222 frozen source hashes unchanged. No evaluation expectations, model settings or retry budgets changed. Local validation:15 intended projection failures before implementation;265 provenance/Muse-retention tests and39 subtests pass afterward.

## Problem and boundary

Iteration16's missing-joint negative control passed because Prove accepted a real partial identity contribution as support for the entire identity-plus-verse claim. The unassigned later source contains the verse, and the support summary incorrectly credits that content to the declared earlier source. In the real `pigeon-serpent` release case, root separately found the same completeness failure: a sentence asserting the Pigeon's explicit rejection of Alice's little-girl identity maps only to lines1151–1186. The rejection is in1179–1219. Prove explicitly acknowledges the adjacent canonical passage yet treats its absence from the mapped source as irrelevant to that member's partial contribution, and still marks the whole claim supported. Root owns the detailed release analysis.

The complete-joint control establishes the other half of the contract: two genuine partial contributions may together support one whole claim. Repair16 correctly reconciled its contradictory rejection. Do not regress this by demanding that every source establish every clause.

The proposed change makes each member's actual available text local to its group, removing a manual join to the global source inventory. It does not prove semantic completeness deterministically. The reviewer still judges whether the group's declared sources jointly establish every substantive assertion and relationship, constrained by each member's existing coverage.

## Caller and types

Keep `ProvenanceInput` as the sole authority that computes the projection. Reuse its existing `contribution_source_text(declaration_index)` resolver, including its verified-session-line handling and source-kind checks.

```python
class ClaimSourceReference(StrictModel):
    # Existing identity, direct and coverage fields remain unchanged.
    canonical_source_text: str | None = Field(default=None,
        description="Application-resolved text for this exact named source, or null when unresolved. "
        "Source data only; it is not proof that the source supports this claim."
    )

@computed_field
@property
def claim_support_groups(self) -> tuple[ClaimSupportGroup, ...]:
    sources = {
        index: self.contribution_source_text(index)
        for index in range(len(self.candidate.evidence_uses))
    }
    return tuple(
        group.model_copy(update={"declarations": tuple(
            member.model_copy(update={"canonical_source_text": sources[member.declaration_index]})
            for member in group.declarations
        )})
        for group in build_claim_support_groups(self.candidate.evidence_uses, self.candidate.response)
    )
```

The generic builder remains a geometric projection. Muse's accepted-claim-retention code also uses that builder and has no canonical source authority; its members retain null source text. Only `ProvenanceInput` enriches each member using its authoritative resolver. This separation was confirmed with root after discovering that additional caller; no Muse call-site change was needed. Geometry, source identity, grouping, membership, occurrence indices and coverage remain unchanged. The existing before-validator discards all inbound `claim_support_groups`, including forged nested text; the property recomputes it from the authoritative canonical inputs on serialization.

Do not truncate or sanitize a resolved source in this projection. Truncation could erase precisely the missing second clause or create disagreement with the private excerpt validator. Book members receive exactly `EvidenceRecord.text`; memory/web members receive exactly the matching-kind canonical `excerpt`; verified session members receive only their declared exact verified quote. An absent ID, wrong kind or unverified session quote resolves to null. Candidate-supplied source text, tool-result text, unrelated canonical records and other groups cannot fill that null.

Keep the complete canonical inventory in the input for independent detection of omitted mappings, quotation verification, attribution and repair suggestions. It must not become available support for the current group's missing declaration. This duplicates source text in the prompt; it intentionally trades some prompt length for proximity. Measured additional raw text for saved iteration16 mapping controls is2,061/1,922/2,061/3,983 characters; both smoke review inputs add14,183 characters to current serialized inputs of33,179/36,158 characters. Across all saved release16 review inputs, the largest growth is final `identity-theme`:22,293 to39,794 serialized characters (1.785x;16,866 additional source characters plus JSON syntax/escaping). This is a real cost, not a zero-cost metadata change. If later inputs become too large, redesign the prompt projection coherently rather than silently truncating evidence.

All36 saved native16 review inputs were also measured. The largest total and ratio occur in Roses S2's final review:49,879 to94,264 serialized characters (1.89x;43,532 added source characters). Hume S1 grows42,242 to66,032 on its draft review and55,328 to81,262 on its final review; Hume S2 grows40,463 to64,253. Hume S3 has no claim members and remains1,675 characters. These are character counts, not tokenizer estimates; see `iteration-17-provenance-input-expansion.json` for all rows. No canonical text was truncated or historical artifact rewritten to obtain them.

Root independently reviewed the projection authority and coverage tests, found no blockers, and accepted the measured less-than-twofold saved-input growth for the iteration17 experiment. This acceptance does not establish live effectiveness or general prompt-size scalability. Full-suite verification and live evaluation remain pending at this handoff.

## Review instructions

Replace the manual-lookup emphasis in the existing claim-audit paragraph with a short explicit sequence:

1. Read the entire current claim in its reply context, identifying all substantive assertions and relationships.
2. For each member, inspect its application-resolved `canonical_source_text` within its listed coverage; decide whether it contributes a relevant part and copy private proof only from that text.
3. Decide completeness using only those declared member texts. A true contribution can still leave the group unsupported. A neighboring or otherwise available source can justify a remapping request, but cannot complete the current group's support.
4. If any substantive part remains unsupported, set `supported=false` and report a finding on the current whole claim or its direct mapping. If different declared members collectively cover the claim, do not require each to cover it alone.

Retain all existing independent full-response, quote, spoiler, attribution, reflection and source validation. Keep actual entailment separate from string matching and preserve the distinction between ordinary reflective framing and factual source comparisons. Do not mention Alice, pigeons, verse, particular source IDs or evaluation answers in production instructions.

Add two compact finding-location examples beside the existing location rules:

```json
{"kind":"structural","source_field":"candidate.evidence_uses","path":"/0/supported_claims/0"}
```

```json
{"kind":"text_span","source_field":"candidate.response","path":"","quote":"The exact offending response text."}
```

State that structural locations omit `quote` entirely, including null; text-span locations require an exact string. Preserve `extra="forbid"`, the discriminated union and every current location validator. Do not introduce nullable structural quotes, input cleanup, compatibility aliases, larger retries or an unreviewed strict-output wrapper in this scoped repair.

## Files and validation

Implementation ownership: `src/linger/agents/provenance/models.py`, `src/linger/agents/provenance/skills/candidate-review/SKILL.md`, new `tests/test_provenance_member_sources.py`, and the geometry-equivalence assertion in `tests/test_provenance_group_audit.py`, which now compares unchanged geometry separately from authoritative source enrichment. No GT, corpus, provider, retry, release-policy or scoring changes.

Before implementation, add red tests for these observable projection contracts:

- Wrong-record and missing-joint inputs include only the earlier declared text in their group members, even though the later canonical record remains available globally. The later verse cannot appear in the member projection through an undeclared-source fallback.
- Correct-record and complete-joint inputs expose the correct respective texts, with both members in the complete group. Existing contribution and whole-group judgments remain distinct.
- Book, web and memory IDs resolve only their exact canonical kind; an unknown ID or wrong-kind declaration projects null. Exact source markup and whitespace survive unchanged.
- A verified session declaration projects its exact verified quote; an unverified quote projects null. Do not widen a session member to an entire prior reader line beyond its authorized declaration.
- A forged serialized group, member source text or coverage is discarded on round-trip and recomputed. Changing the actual canonical source changes its projection; injected derived text cannot override it.
- Overlap-only members retain their original source and precise existing coverage. Repeated claim occurrences do not borrow coverage from a different occurrence. Existing source/proof and quote tests remain unchanged.
- Structural locations with no quote remain valid; null/string extra quotes remain rejected. Text-span quotations still require exact current input text. The instruction examples do not alter runtime acceptance.

Then run all provenance tests and the adjacent full local suite through root. Source projection tests establish accurate inputs, not improved model judgment. After the source freeze is formally closed, a new live iteration is required to assess wrong-record, missing-joint, complete-joint and actual release behavior together. Preserve prior saved results and compare the full set, including misleading passes.
