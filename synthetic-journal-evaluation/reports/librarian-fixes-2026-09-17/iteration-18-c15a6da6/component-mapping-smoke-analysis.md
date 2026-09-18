# Iteration18 mapping and smoke review

Both components pass: mapping4/4 has credible final judgments; smoke passes all six hard stages and is semantically credible with a minor presentation limitation. This analysis changes only its artifact; no source, expectation or provider changes were made.

## Mapping: all four final judgments credible

Reviewed all four original typed inputs, every output and retry, final reviews, grades, source texts and usage in `suite-mapping.json`. Trace `01a0b4380de7f926a61693fadde70510`. Every input is unchanged from iteration17, including the member-local canonical source projection. All final reviews independently revalidate against their exact original inputs. All cases have complete recorded usage and no recorded provider failure.

| Control | Requests | Evidence-backed assessment |
| --- | ---: | --- |
| Wrong record | 2 | Initially falsely passes by copying the later undeclared memory/verse passage into proof for the earlier source. Literal source validation rejects it. The final review correctly marks the member noncontributing and the group unsupported, with a valid structural finding requesting the actual later record. |
| Correct record | 1 | Credible pass. A continuous authentic excerpt from the named later source directly establishes both memory difficulty and the verse coming out differently. |
| Missing joint contribution | 1 | Credible revise on the first attempt. The earlier source genuinely contributes identity/size content, but the complete group is unsupported because the verse is absent. The reviewer asks to declare the available later record or remove that clause. |
| Complete joint contribution | 1 | Credible pass on the first attempt. Both genuine partial contributions are named, their union supports the complete sentence, and no spurious per-record completeness or attribution finding is emitted. |

The complete-joint result improves on iteration17's incorrect relabeled `misattribution` rejection. This run does not exercise the new attribution-consistency repair path: the first output is already consistent. Updated instruction/schema wording may have helped, but sampling and simultaneous changes prevent a causal claim. The new guard's exercised evidence remains the focused local red/green and actual-agent tests, not this successful live control.

The all-pass result does not mean the reviewer reliably gets every first judgment right. The wrong-record first output repeats the exact cross-record borrowing error despite member-local source text. Existing literal proof validation prevents that initial false approval from becoming a final accepted review. No broader source permissions or automatic approval were introduced to obtain4/4.

## Smoke

Reviewed `suite-smoke.json`, its status, and all eight saved exchanges, every output/repair and named book/web evidence in `suite-smoke.diagnostics.json`. Run `a4680a7f7d5d44a8ac2d13bc5606d07d`; trace `01a0b43755a28cd15401f4c82f2b1664`. All recorded exchanges succeeded without recorded provider errors. Both final typed Provenance reviews independently revalidate against their exact inputs. The output is released from `muse_candidate` and every hard stage passes.

The reader asks for a philosophical connection after finishing Chapter5. Librarian returns the relevant opening Caterpillar exchange, `pg11-v01b38ea4-ch05-ln0960-1016`. Serendipity selects the opened Stanford Encyclopedia of Philosophy's Socrates entry at `https://plato.stanford.edu/entries/socrates/`. Its selected canonical text explicitly describes making others think for themselves, recognizing ignorance and sometimes reaching intellectual curiosity. These are appropriate supports for the final comparison. No personal memory is used.

Serendipity needed one output repair because its initial rank-one candidate was not a clear rubric winner; the accepted selection remains the actually opened source. Muse's first draft declared the complete authentic `“Who are _you?_” said the Caterpillar.` but displayed only part of it, so literal reply binding rejected that declaration. The existing exact-copy hint prompted Muse to include the complete declared source span. The newer `reply_quote_repair` diagnostic is absent here; this does not live-exercise that specific helper.

The initial accepted draft's comparative purpose claim and concluding scene interpretation were assigned only to the web source. First Provenance review correctly recognizes the web's partial contribution while rejecting the whole hybrid claims for missing book support. It does not require the web to establish the whole comparison alone when another relevant source is genuinely declared; here it was absent. The feedback identifies both current defective spans.

Muse's revision separates the bounded book interpretation and evidence limitation, maps them to Chapter5, and maps its final substantive synthesis to **both** book and web:

> In that sense, the scene makes philosophical uncertainty feel unsettling: reaching an intellectually revealing impasse does not necessarily feel helpful while you are inside it.

Final group5 contains the actual book declaration0/claim5 and web declaration1/claim1 as direct members with full sentence coverage. The source excerpts are authentic: the book describes Alice's irritation; the SEP account describes eliciting recognition rather than passively transmitting information, with surrounding text explicitly describing unpleasant ignorance and possible curiosity. Their distinct contributions support this qualified comparative interpretation. The prior web-only mapping defect is repaired, not merely moved to book-only support.

The final response accurately summarizes the repeated identity question, Alice's confusion/irritation and the source's lack of an established benevolent motive. It describes testing as a possible reading and ends with an open question, avoiding a claim to know the Caterpillar's intention. The SEP factual summary and exact opened URL are present. The phrase introducing the SEP account, “That resembles the Socrates described by...”, serves as a connective lens on already mapped book material; the central substantive synthesis has its complete joint mapping. No additional factual source proposition or unresolved missing source was identified there.

Both public book quotation checks pass against the named canonical record and response. No source-quote content is borrowed, altered or left unbound. The sentence containing that quotation is awkwardly integrated: “the Caterpillar begins with the challenge, ‘Who are you?’ said the Caterpillar.” The actual output retains the source's curly punctuation and Markdown emphasis. This is a presentation limitation, not a false source attribution or unsupported plot claim. An implementation should not force every future draft to copy this awkward surrounding narration; the valid quote-interior contract remains available.

Final Provenance review resolves both earlier findings and passes in one request. Neither the new whole-claim attribution-consistency guard nor a relabeled equivalent finding appears in smoke. Successful release therefore shows this sample's source-mapping repair works, while the guard's specific action remains supported by local tests. Reduced suite concurrency coincides with no recorded provider error here, but this one run does not prove it caused that improvement or eliminated429 risk.

Attention: final mapping4/4 still depends on correcting an initial borrowed-source false approval. Smoke's final comparison is credible, but its awkward literal-quote insertion is a user-visible quality limitation. No historical grade, source, expectation or live-budget reservation was modified by this review.
