# Iteration17 mapping and smoke review

Both components are reviewed. Mapping is3/4, with a false rejection of valid joint support. Smoke fails safely after a Muse revision request receives provider HTTP429. This review changes only this analysis artifact; no source, expectation or provider changes were made.

## Mapping controls

Inspected all four original inputs, every output and retry, final reviews, grades, usage and source text in `suite-mapping.json`. Trace `01a0b4251524fdab82afd80c9387324e`. All four successful final reviews independently validate against their inputs. Each took two model requests, with complete recorded usage and no recorded provider failure.

| Control | Initial behavior and repair | Final semantic assessment |
| --- | --- | --- |
| Wrong record | Again borrowed the later undeclared memory/verse passage and duplicated declaration0. Literal source and member-inventory checks rejected it. | Credible revise. Identifies the earlier record ending before the claimed events, with a valid structural finding that omits `quote`. |
| Correct record | Correctly recognized support, but emitted the same member twice for two excerpts. Inventory repair consolidated them. | Credible pass with one continuous authentic excerpt supporting both memory and verse assertions. |
| Missing joint contribution | Already recognized that the earlier record supports identity/size but not the later verse event; emitted the same member both true and false. Inventory repair retained the true partial contribution and false group verdict. | Credible revise. A useful partial source is correctly separated from complete claim support. |
| Complete joint contribution | Recognized authentic contributions and collective support, but still issued per-record whole-claim unsupported findings. Repair16's contradiction check triggered. | False negative: the next output changed the findings to `misattribution` while retaining the same incorrect demand for each member to establish the entire sentence. |

### Projection effectiveness and limits

All four saved inputs exactly equal iteration16's original typed inputs after recomputing the new source-text projection. The only substantive input change is the derived named-source text beside each claim member. Wrong-record and missing-joint members contain the earlier source only, despite the later source remaining globally available. The complete joint group contains both exact sources with unchanged coverage.

The missing-joint case now correctly distinguishes partial contribution from completeness on its first semantic attempt. This is encouraging sample evidence, not an isolated causal result: instructions also changed, and model sampling varies. Wrong-record still borrows the later source on its first attempt, so proximity does not eliminate source contamination. All final private excerpts match their named canonical sources.

The four serialized input sizes are18,204 /18,062 /9,060 /11,749 characters. Each run completed in two requests; no input-size or context overflow was recorded. Their aggregate input-token counts are27,022 /25,453 /21,684 /25,689 respectively, including retry prompts. These are recorded total usage, not first-request token counts or a controlled token-cost comparison. Prompt duplication remains a cost, and successful execution does not establish that longer context cannot affect judgment.

### Complete-joint false rejection

The candidate is unchanged: “In Chapter 5, Alice struggles to explain who she is after changing size, and later reports that a familiar verse came out differently.” Its whole sentence is deliberately assigned to two records, one establishing identity/size difficulty and one establishing the verse report. This is the intended many-source collective-support contract.

The first review sets both contributions true and the complete group supported, then issues two `unsupported_claim` findings on the full direct claim leaves. The application returns the precise consistency errors added in repair16. The second review keeps both authentic excerpts, both positive contributions and the supported group. Its summary explicitly says that the records together establish the complete claim, but also says each declaration improperly attributes the entire claim to only one source.

The final findings are now `misattribution`, with the same leaf targets and substantive complaint. They ask Muse to narrow each source to its own clause or make the full sentence jointly mapped, although it is already jointly mapped. No wrong speaker, wrong author, false quotation, source-identity mismatch or other independent attribution defect is identified. This is a semantic reclassification of the same mistaken per-source completeness rule, not a genuine new risk.

The current validator intentionally permits misattribution findings alongside supported claims because genuine attribution/quotation defects can coexist with sufficient factual support. Extending the contradiction check indiscriminately to every misattribution code would suppress valid risks and is not justified by this example. A subsequent repair must clarify or encode the distinction between an actual attribution defect and a demand for independent whole-claim support, without making the correct joint control automatically pass. No historical verdict has been altered.

### Proposed scope invariant and counterexamples for a later repair

The whole-claim audit already includes attribution: its schema explicitly instructs the reviewer to preserve attribution, causal direction and timing. A complete-support verdict plus every member contributing cannot simultaneously dispute the truth or attribution of that exact complete claim/mapping. The existing narrow complete-claim matching rule could therefore cover both unsupported content and misattribution **at those exact claim targets**, provided the repair explicitly allows locating an independent quote/source defect precisely or correcting the audit. It must not discard a finding or choose a passing verdict.

Concrete controls before changing that invariant:

- This saved valid joint claim with `misattribution` on `/0/supported_claims/0` or `/1/supported_claims/0`, while complete support and all contributions remain true, should request reconciliation. So should an exact whole-claim response location. Authentic partial excerpts alone must not automatically turn it into a pass.
- If a claim says the wrong speaker performed an action, the complete claim's attribution is unsupported: `supported=false` plus a whole-claim misattribution finding stays valid. The model can repair a contradiction by correcting the audit and retaining rejection.
- A factual paraphrase may be supported while a separate quoted fragment is altered or attributed to the wrong speaker. A misattribution finding on `/0/exact_quote`, `/0/quote`, `/0/evidence_id`, or a narrower offending response quotation remains valid alongside a positive factual-support audit. Source-location errors should likewise target the relevant source-location field rather than redefining a complete claim's support.
- A finding on an enclosing declaration/list can concern an independent structural defect and remains outside the exact-leaf consistency rule. A partial response or claim-leaf span is also outside it because the validator does not infer what narrower defect it describes.
- If any member is noncontributing, supported collective content may still carry a wrong-source mapping; the existing all-members-contribute prerequisite prevents suppression of that legitimate finding. Capture, spoiler, emotional-policy and injection findings remain independently valid even when a factual statement is supported.

This proposed change would be a consistency rule about the semantic meaning of whole-claim targets, not an assumption that the two risk labels mean the same thing everywhere. It should ship only with these negative controls and unchanged strict quote/source validation. It cannot prove that the reviewer's support verdict itself is correct; the source-contamination negative controls remain necessary.

## Smoke

Smoke fails safely: `suite-smoke.json` records an application-safe-decline reply after the revision request receives provider HTTP429. Run `a3107c48bfc344958171f7777dd0aa99`; trace `01a0b42515610d85796a8ea5b7f61196`. Reviewed all seven agent exchanges and their exact inputs, outputs and diagnostic history in `suite-smoke.diagnostics.json`. Invocation, retrieval and selection hard stages pass; presentation fails. The later stages are graded `not_reached` because of this stage cascade, although an initial Provenance review did execute successfully.

The reader again asks for a philosophical connection after Chapter5. Book evidence is the same relevant opening Caterpillar exchange. The selected opened outside text is Plato's *Meno*, page80, via Perseus. Its actual excerpt includes Meno's perplexity and Socrates' willingness to examine the matter together. The selected source is therefore relevant; this is not a retrieval or outside-source availability failure.

The draft first needs a mechanical claim-span repair and a quotation-punctuation repair: `utter perplexity,` does not match the source's terminal period. The accepted draft uses the exact `utter perplexity.` and exact book question. Its citation has an unmatched outer parenthesis, a minor draft presentation defect. The new quote-copy diagnostic is not exercised because this two-word quote is below its existing suggestion threshold; the source and precise edge mismatch remain in the normal feedback. No evidence was released.

Initial Provenance review correctly rejects a separately mapped sentence that says the Caterpillar offers little shared inquiry “unlike Socrates,” but declares only the book. Group1's projected member text contains no Socratic text. The reviewer recognizes the genuine partial book contribution and marks the complete comparison unsupported, asking for the missing *Meno* mapping. It correctly accepts a different concluding synthesis that already declares both book and web, with authentic excerpts and positive partial contributions. This is useful evidence that the reviewer can distinguish complete and incomplete joint support within an actual reply, despite the remaining mapping-control false negative.

The same review also calls the introduction, “Your reading has a strong philosophical parallel in Plato’s *Meno*:”, an uncovered source-dependent assertion. That objection may be overstrict because an introductory proposed lens need not create a separate source proposition when the underlying accounts and synthesis are mapped. It is not necessary to justify revision here: the explicit book-only comparison supplies a real remaining defect. Keep this possible false-negative finding separate from the credible mapping correction.

The saved review mechanically revalidates against its exact input. No final revised candidate or final Provenance verdict exists. Muse revision exchange7 has `status=failure`, `failure_code=muse_revision_model_failed`, `failure_category=provider_error`, `provider_status_code=429`, `provider_error_kind=http`, and no usage result. Its `model_messages_include_history=true`: seven earlier draft messages precede one new revision request. The repeated draft outputs and retry in that history are **not** new revision attempts. The artifact does not preserve a more specific provider explanation, so this review cannot distinguish request-rate, token-rate or another429 condition, nor attribute it to source projection or concurrency.

The review input carries the new full source projection; no explicit context-length rejection is recorded. A429 during Muse revision does not establish that the larger Prove prompt caused the failure. Final repair quality and release semantics remain unobserved. Preserve this as a counted failed live smoke run, with provider interruption distinguished from an application semantic rejection.
