# Iteration 19 mapping and smoke review

Mapping is **4/4 with credible first judgments**. Smoke **fails after revision**, with a real overextended essay attribution in the draft and a mixed final review judgment. Artifact-only review during source freeze; no provider calls or source/expectation changes.

## Mapping

Reviewed every case, original typed input, member source text, output, usage and saved model messages in `suite-mapping.json`. Trace `01a0b446ae7cacf675157269de1782dd`. All four inputs are identical to iteration 18; all final reviews independently revalidate against their exact inputs. Each case uses one request with complete usage and successful status. There are no retries or provider errors.

| Control | Semantic result |
| --- | --- |
| Wrong record | Correct revise: named earlier identity passage does not support later memory/verse claim. Member is noncontributing, group unsupported; remapping to the actual later record is requested. No undeclared-source borrowing occurs. |
| Correct record | Correct pass: one authentic continuous later-source excerpt establishes both difficulty remembering and the verse coming out differently. |
| Missing joint contribution | Correct revise: earlier identity/size source contributes, but the verse clause is missing. A precise finding identifies that clause and requests its actual later source or removal. |
| Complete joint contribution | Correct pass: both named sources contribute to the complete sentence. Identity/change and later memory/verse material collectively establish the claim. No source is incorrectly required to establish every clause independently. |

The positive complete-joint first output needs neither the whole-claim attribution guard nor relabeling repair. The wrong-record first response improves on iteration 18's initially borrowed-source approval, but one sample does not establish a durable model improvement or identify which prompt change caused it. Existing literal-source and review consistency validation remain necessary. Authentic private excerpts preserve the relevant contributions, with whitespace normalization only where permitted.

## Smoke

Run `58e249ce39a54a1ab15c6de63339a6b9`; trace `01a0b44663c3c77ab659e4b3cc194fa6`. Reviewed the result and all ten recorded exchanges, current candidates, mappings, selected page, book evidence, output repairs and reviews. All recorded exchanges succeed without provider errors; the application safely declines because the revised candidate receives another `revise`. Four initial stages pass, provenance fails, release is not reached. Both saved Provenance reviews independently validate against their exact original inputs.

Unlike iteration 18's SEP Socrates selection, Serendipity selects N. Gooding's opened essay at `https://ngooding.substack.com/p/self-knowledge-and-self-deception`, alongside the same Chapter 5 opening Caterpillar record `pg11-v01b38ea4-ch05-ln0960-1016`. The request permits an outside philosophical connection, and the selected page and book source are real and relevant. Serendipity's proposal already extends the essay into an account of self-knowledge being clarified through dialogue. That interpretation remains untrusted; its selection is not proof that the interpretation is supported.

Muse's initial mechanical repair fixes three nonliteral claim mappings. The accepted draft then attributes to Gooding the view that perplexity is evidence self-knowledge may have to be worked out through dialogue. First Prove review correctly requests a supported paraphrase: the available essay presents the Socratic dialogue's conceptual puzzles, but explicitly calls its arguments a dead end and proposes looking elsewhere. Its final available paragraphs describe personal self-deception and others sometimes seeing us clearly; the excerpt ends mid-quotation from the Magna Moralia. The supplied fragment does not establish everything asserted in the proposal or initial attribution.

Muse revises that attribution to a fair description of difficulty examining one's own beliefs. It also voluntarily adds the existing concluding sentence to **both** web and book declarations:

> Together, they make identity feel less like a fixed label than something tested—and perhaps clarified—in conversation.

The sentence is unchanged from the initial draft, where Prove classified its uncovered span as reader reflection and made no finding. On revision, Prove marks the web member noncontributing and the entire group unsupported, while accepting the book member's partial contribution. The explanation says the essay does not establish the **complete** comparison and suggests removing the web mapping or narrowing the claim. That wording risks the same mistaken per-member completeness demand seen earlier: the web plainly contributes perplexity and testing of self-knowledge, and a jointly declared member need not independently establish the entire comparison.

However, this is not a clean proven false negative. The essay's criticism of the Socratic arguments makes clarification through conversation a debatable extension even with tentative wording; an unsupported relation must not pass merely because both sources are relevant. A defensible reviewer could request a narrower joint synthesis limited to questioning exposing difficulties in self-understanding. If a real substantive defect remains, dropping the web declaration alone cannot repair the word “Together” or an unsupported comparison. The better diagnostic would identify the exact unsupported relationship while recognizing genuine partial contributions. The prior review should also have evaluated this same sentence independently of whether Muse had declared it.

The book descriptions and bounded examination interpretation are plausible: the source depicts a languid opening, repeated questions, stern demands and Alice's confusion. The sole actual source quotation is character-exact in the named source and reply. The two illustrative quoted formulations about giving an account are transparently hypothetical contrasts, not presented as additional literal book dialogue. Chapter title and essay citation are accurate. No memory, spoiler expansion, missing public citation, source borrowing, whole-claim attribution guard or relabeling repair occurs in the saved output.

Attention: retain the failed grade and safe decline. The changed selected essay prevents treating this as a controlled regression of the prior SEP example. The initial author attribution is overstrong; the final review mixes a plausible support concern with a questionable complete-source demand and belated scrutiny of an unchanged sentence. No live prompt improvement or automatic acceptance is justified by this one outcome.
