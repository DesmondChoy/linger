# Iteration 16 mapping and smoke review

Both reviews are complete. Mapping is 2/4. Smoke passes all six hard stages but has a plausible incomplete comparative mapping, so semantic acceptance remains qualified. No provider calls or source changes were made for this analysis.

## Mapping: 2/4, with one accepted unsafe judgment

Inspected all four original inputs, all model outputs and retry messages, final reviews, grades and recorded usage in `suite-mapping.json`. All four input values are identical to iteration15, including their application-computed projections. Trace: `01a0b413d5bb89b8e972de680788565a`.

| Control | Requests | Result and semantic assessment |
| --- | ---: | --- |
| Wrong record | 3 | Safe gate failure, not a successful review. Two attempts borrowed the undeclared later passage. The final attempt correctly rejected the mapping but emitted an invalid structural finding with `quote:null`. |
| Correct record | 1 | Credible pass. Its declared later Chapter5 passage contains both memory difficulty and the verse coming out differently. |
| Missing joint contribution | 1 | Real false positive. It passed with an authentic identity excerpt, while claiming that the declared earlier passage also establishes the later verse event. |
| Complete joint contribution | 2 | Credible pass after repair. The new consistency check caught the same mistaken per-record completeness demand seen in iteration15; the next attempt used authentic excerpts and correctly recognized collective support. |

The successful three final reviews independently revalidate mechanically. That includes the missing-contribution false positive: literal proof checking is necessary but does not establish semantic completeness. No HTTP/provider failure is recorded. Wrong-record failure is `UnexpectedModelBehavior`, category `model_response_error`; its diagnostic marks `usage_complete=false`. The remaining usage records are complete. Do not interpret the wrong-record case as a correct final typed rejection or complete cost accounting.

### Missing-contribution false positive

The candidate says: “In Chapter 5, Alice struggles to explain who she is after changing size, and later reports that a familiar verse came out differently.” Only `pg11-v01b38ea4-ch05-ln0960-1016` is declared. Both that earlier record and the later `pg11-v01b38ea4-ch05-ln1004-1056` remain available in the canonical inventory.

The earlier record contains the Caterpillar's identity question, Alice's difficulty explaining herself, and her statement that many changes in size are confusing. It ends with Alice asking whether “Keep your temper” is all the Caterpillar has to say. The later record contains Alice's memory complaint and her report that “How doth the little busy bee” came out differently. This second record is available but undeclared in this negative control.

The first and only review copies the authentic earlier excerpt `I can’t explain _myself_, I’m afraid, sir,`, sets its contribution true and the whole group supported, then states in its summary that the declared record includes the changed verse. The first contribution is real; the complete-support judgment is wrong. The application correctly accepts the literal excerpt, but has no deterministic evidence that every factual clause has been checked. The new consistency rule does not apply because this output contains no contradictory finding.

The existing task instructions already prohibit borrowing available undeclared records, distinguish partial contribution from completeness, and explicitly illustrate a jointly supported claim with a missing second declaration. The failure therefore survives an explicit semantic instruction. The undeclared canonical inventory offers the exact missing material, making source contamination a plausible mechanism, although this trace cannot establish the model's internal cause.

For iteration17, the narrowest structural improvement worth testing is an application-computed projection of each group's declared members with each named source's canonical text immediately beside its declaration and coverage. This avoids asking the reviewer to manually join the complete inventory to group membership. Unknown sources must remain absent/null; session-line authority must use verified lines; overlap coverage must remain unchanged; inbound forged projections must be ignored. Keep the full canonical inventory for independent missing-mapping, quotation and attribution review, but make clear that it cannot fill a group's missing declaration. This reduces lookup ambiguity without changing the full-claim versus partial-member contract or claiming that availability grants mapping authority.

A stronger alternative is explicit source-specific accounting for each substantive component of a claim, permitting multiple sources to cover different components. It would require a new semantic decomposition contract and careful coverage rules; simple character coverage would confuse connective or reflective prose with factual support. It should not be bolted onto iteration17 merely to force this control to pass. Repeating a longer prose warning alone has weaker justification than bringing the declared canonical text into the existing typed group projection.

### Structural finding schema failure

Offline validation of the final wrong-record tool output fails exactly at `findings[0].location.structural.quote`: `extra_forbidden`, input `null`. Its final semantic assessment correctly identifies the missing declaration and asks to map to the later record or remove the unsupported claim. The two preceding attempts exhausted repair opportunities by borrowing literal proof from that later source.

`StructuralLocation` in `src/linger/agents/provenance/models.py` intentionally contains only `kind`, `source_field` and `path`. `StrictModel` forbids extra fields. The locally installed OpenAI schema transformer preserves that shape and `additionalProperties=false`; it does not add a nullable quote property. With the current default `strict=None`, the full review schema is not strict-compatible, so the tool schema is not automatically strict. There is no evidence that `quote:null` was required by the provider format.

Do not silently strip this field or weaken extra-field validation. A narrow immediate correction is to make the structural-location example explicitly omit `quote`. A systematic option is to investigate strict tool output for this role while retaining all application validation. That would need deliberate integration: `RuntimeSkill.fingerprint` currently treats `output_type` as a Pydantic type and does not support a `ToolOutput` wrapper directly. This is an option to evaluate, not an implemented fix or a proven cause of general review unreliability.

### Evidence that repair16 was exercised

The complete-joint first output marked both contributions and collective support true, yet issued two whole-claim unsupported findings because each record did not independently establish both clauses. The new validator returned a contradiction error for both findings. It also rejected excerpt alterations, including missing Markdown emphasis. The next output removed the spurious findings, copied authentic excerpts and retained the correct collective-support judgment. This supports the intended repair mechanism in this case, although simultaneous excerpt feedback prevents attributing the result to only one error message.

## Smoke: hard pass, qualified semantic acceptance

Reviewed `suite-smoke.json`, `suite-smoke.status.json` and all eight recorded agent exchanges, every output and retry, and the selected canonical book/web sources in `suite-smoke.diagnostics.json`. Run `a34906022804404f82b08cfaa32a36d4`; trace `01a0b413d52ac7bb0ff227589b4d4938`. All exchanges succeeded without recorded provider failures. Both saved Provenance reviews independently revalidate against their exact inputs. These are mechanical facts, not proof of semantic completeness.

The reader explicitly finishes Chapter5 and asks for an outside philosophical connection. Librarian selects the relevant opening Caterpillar exchange, `pg11-v01b38ea4-ch05-ln0960-1016`. Serendipity opens three web results and selects the Stanford Encyclopedia of Philosophy's Socrates entry, `https://plato.stanford.edu/eNtRIeS/socrates/index.html`. The canonical selected excerpt is bounded to 8,000 characters. It describes Socrates unsettling conversation partners into recognition of ignorance, sometimes followed by intellectual curiosity. No personal memory is used.

The draft genuinely maps its comparative sentence to both book and web. Its first local retry repairs terminal punctuation in two claim mappings separated from the final period by a Markdown citation. Initial Provenance review accepts the book interpretation, the complete literal `“Who are _you?_”`, and the relevance of both sources, but rejects the stronger web characterization “usually a sustained examination.” The selected excerpt supports recognition of ignorance and curiosity but does not establish that stronger frequency/duration characterization. This is a reasonable narrowing request rather than the per-source completeness error seen in the mapping control.

Muse revises to a directly supported SEP summary. The final review's first attempt includes an artificial ellipsis between two pieces of a private book excerpt; source-literal validation rejects that splice. Its retry copies a continuous authentic source span and passes. The new complete-support contradiction check does not trigger in smoke, and no `reply_quote_repair` diagnostic is used here. This run does not isolate the new Muse copy feedback's effectiveness.

The released book quotation is character-exact and correctly bound. The surrounding book interpretation is grounded in the identity exchange; the SEP summary is faithful and visibly cites the exact opened URL. The ending offers a possible interpretation and an open question, without asserting proven authorial intent, inventing personal history, or exceeding Chapter5.

One declaration concern remains. The released synthesis says:

> The Caterpillar’s calm, cryptic version of questioning gives that process a more test-like quality: Alice is left to examine the instability of her identity without being given a clear answer.

Its sole declared source is the book (`evidence_uses[0].supported_claims[2]`, final group2). The web declaration ends with the preceding SEP summary and has no overlap with this sentence. In context, “that process” refers to Socratic recognition of ignorance and possible intellectual curiosity. This is a plausible cross-source comparison whose SEP contribution lacks a mapping for this occurrence. The final reviewer treats it entirely as book interpretation and passes.

This is a **potential false positive / incomplete comparative mapping**, not a fabricated book event or a demonstrated false statement about the source. The wording is closer to reflective framing than iteration13's more explicit “that argument” synthesis, but its implicit source-dependent antecedent prevents unqualified semantic acceptance. Root independently reviewed the exact sentence and agreed with this qualified assessment. The distinction supports improving general group/source clarity; it does not justify a phrase-specific guard or changing this saved hard grade.

The hard result remains six stages passed and `release_source=muse_candidate`; semantic qualification is recorded separately. A future repair should either map both actual contributions to the comparative sentence or clearly separate the supported source accounts from a reflection that adds no source proposition. No saved output, expected result or historical grade was modified.
