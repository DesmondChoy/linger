# Iteration18: reconcile attribution with whole-claim support

Status: implemented after root closed iteration17 with222 matching source hashes and authorized the scoped repair. Beads `linger-9oqp.8` tracks this work. The saved iteration17 complete-joint result remains unchanged and failing; offline revalidation now requests reconciliation for its contradictory attribution findings.

## Invariant

`ClaimSupportAudit.supported=true` means that the group's declared sources, within each member's coverage, collectively establish the complete claim, including correct attribution. `SourceContributionAudit.contributes=true` for every member means none of those mappings is irrelevant. A finding that disputes the truth or attribution of that **same complete claim/direct claim leaf** contradicts those judgments. The reviewer must reconcile the audit and finding before returning a valid output.

Apply the existing exact-target contradiction check to both `unsupported_claim` and `misattribution`, with the existing prerequisites: valid complete member inventory, group supported, and all members contributing. Keep the matching rule limited to exact full-claim text or an exact direct `supported_claims/<index>` leaf. Keep all other risk classes and locations unchanged.

The repair may correct a mistaken support audit to unsupported, mark an actually irrelevant member noncontributing, refine the location of a distinct quotation/source defect, or withdraw a mistaken finding. It must not automatically delete findings or approve the candidate. Changing only a risk label does not reconcile an unchanged whole-claim contradiction.

## Counterexamples that must remain valid

The record may support a factual paraphrase while an accompanying quote has the wrong words, speaker, formatting or source assignment. A quotation/source finding at `exact_quote`, `quote`, `evidence_id`, `source_location` or a narrower quoted response span is an independent risk, not denial of the complete paraphrase. Preserve it while leaving factual support positive.

A claim that attributes an event to the wrong speaker is unsupported in its complete meaning: a negative group audit plus whole-claim misattribution remains valid. A genuinely irrelevant direct source can also require correction even when other sources collectively establish the claim; any noncontributing member keeps the existing exception. Broader declaration/list findings are not assumed to dispute a whole claim. Capture, spoiler, emotional-policy, injection and other independent risk checks remain unchanged.

## Ambiguous local contract language

`EvidenceClaimSupport.supported_claims` in `src/linger/agents/muse/models.py` currently says: “Exact substantive clauses or sentences from reply supported by this source.” Its class docstring similarly says one source declaration supports the spans. Read alone, this can imply independent full-span support, conflicting with the established joint-source contract. The proposed description is:

> Exact substantive reply spans to which this source contributes support. A complete claim may be repeated across declarations when several sources jointly support it; this source need only establish its relevant part, while the declared sources together must establish the whole claim. Include the factual description or interpretation itself, not just its introductory phrase. Map all claims that rely on this source and update them when revising the reply.

The first declaration paragraph in Prove's skill also says “Muse claims this source supports” before its later, clearer joint-support instructions. Replace that introductory formulation with source **contribution** and state that a repeated complete span requests collective assessment, not independent proof from each declaration. Maintain the existing statement that records cannot serve interchangeably and that quotes have a separate exact contract.

Exposure matters: the shared `supported_claims` description is part of Muse's output schema and the serialized-input schema/fingerprint. Prove receives the input as JSON values, so that field description is not itself directly supplied as a Prove output-tool description. It is a real contract ambiguity worth correcting, but the trace does not prove that this schema wording caused Prove's misclassification. The first Prove instruction paragraph is directly exposed. Do not claim a proven causal diagnosis from wording alone.

`ClaimMappingCases` and `RiskCodeEvalCase` describe evaluation packaging/expectations; those expected answers are not passed into the production reviewer. They should not be edited for this repair.

## Regression plan

Start from the exact iteration17 complete-joint input and final review, whose findings target `/0/supported_claims/0` and `/1/supported_claims/0`. Preserve the original as an offline fixture or use the equivalent existing bounded mapping fixture. Before production edits, demonstrate failure for the new attribution contradiction while retaining existing unsupported-claim checks.

| Variant | Intended validation result |
| --- | --- |
| Supported/all-contributing, `misattribution` exact text claim leaf | Request reconciliation |
| Same, structural direct claim leaf | Request reconciliation |
| Same, exact whole-claim response span | Request reconciliation |
| Same location and audit, `unsupported_claim` | Continue requesting reconciliation |
| Negative complete audit, whole-claim misattribution | Accept typed rejection |
| Positive complete audit but noncontributing direct member, its misattribution finding | Accept typed rejection |
| Positive audit, misattribution on exact_quote or source identity/location field | Accept independent finding |
| Positive audit, misattribution on a narrower response/claim-leaf span | Accept independent finding |
| Positive audit, structural enclosing declaration/list finding | Accept independent finding |
| Positive audit, unrelated response finding or capture finding | Accept independent finding |

Exercise the actual local FunctionModel repair path with two outcomes: one reviewer withdraws a mistaken whole-claim finding and passes; another corrects `supported=false` and retains a safe rejection. Neither outcome is selected by application code. A third repair can retain `supported=true` and relocate a genuine separate quotation defect to its exact quote field. Keep the existing full source-excerpt, quote, source-kind, occurrence and coverage tests unchanged.

Run the provenance suite, Muse schema/contracts checks and root's full suite. After iteration17 formally closes and root authorizes implementation, source ownership is Prove plus the single shared declaration description in Muse models; no other Muse behavior should change. No model, provider, retry, evaluation, ground-truth or source-corpus changes are proposed. Live improvement remains unverified until iteration18.

## Implemented verification

Five new attribution cases failed before the code change: three complete-claim locations were accepted without reconciliation, and two actual-agent checks skipped the expected output repair. Twenty-five surrounding controls passed in that red run. After implementation, all32 focused consistency tests pass, including both risk classes and three local repair outcomes: withdraw the mistaken finding, correct the audit and retain rejection, or locate an independent quote defect precisely and retain rejection. All389 provenance/Muse tests and58 subtests pass.

Offline validation of the four untouched iteration17 final mapping reviews leaves the first three valid and requests reconciliation for both whole-claim misattribution findings in the complete-joint control. No final verdict was rewritten and no live requests were made. Root's independent review, full-suite validation and iteration18 live behavior remain pending at this handoff.
