# Cross source connections and restraint

Final run. 2026-10-16T16:17:09.132286+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **2/3 Scenes passed**. LLM-review: **3/3 Scenes passed** (3 passed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/connection_and_restraint/compare?experiment=01a143c67c77fdbc03224b9ca6fd97f7-7194298079e38cc4>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| S1 | Tentative three-source connection (note, Alice Chapter 5, Hume) with the sources kept distinct and Hume cited. | 'Three different lenses, not as one explanation'; exact Chapter 5 quotation; cited Hume; the same-view detail; a closing question. | passed (1/1) | passed | A cross-source comparison stayed tentative and kept the evidence types apart. |
| S2 | Decline the 'work voice is an act' verdict, explain each source's limits, and keep helping. | Declined the verdict; noted the note covers one day, not a pattern; quoted Alice and cited Hume; asked what feels continuous. | passed (2/2) | passed | Restraint with substance: the reply qualified the claim and still offered a way forward. |
| S3 | One simple dinner sentence from the current Line alone, with no exploration, inviting adjustment. | Muse called serendipity_explore(find_connection), which declined with no retrieval; released 'Try: “I have a thought about that.”' | failed (0/1) | passed | An unnecessary exploration call fails the check even when the answer is fine. |

## Failures

### S3

**Failure type: Legitimate model failure** (cause suspected). Automated failed; LLM-review passed.

**What failed.** Muse's reflection draft called serendipity_explore with intent find_connection for a self-contained request for a sentence to say at dinner. The invocation stage failed with unexpected_exploration. The tool declined (no_permitted_evidence) with no retrieval, and the released reply was a single usable sentence.

**Ground truth.** Proposal-s3-personal-reflection: 'Work only from the current Line. No memory, book, public source, or factual corroboration is needed to help formulate a sentence.' Treat it as personal reflection, and invite Leena to adjust the sentence to her own voice.

**Root cause.** Policy allowed connection (allow_connection true, no book scopes), so the tool was offered. Its description says not to call it for 'a personal wording request without source comparison', which describes this Line. The same description also says find_connection fits 'an optional connection worth surfacing', and that broader clause competes with the exclusion. The model chose to explore. The exclusion is explicit, so the primary type is model failure. The competing clause is a suspected contributing prompt factor.

**Proposed solution.** Keep this result. If the sweep shows unnecessary exploration on other personal controls, scope the 'optional connection worth surfacing' clause so that it never applies to self-contained personal wording requests. Check cross-agent impact on Serendipity invocation in the connection Scenarios. Verify by replaying the S3 Muse draft input (no tool call) and the S1/S2 inputs (call still made).

## Report points

- Automated checks passed 2 of 3 Scenes, and LLM-review passed 3 of 3. S3 is the automated failure.
- S1 and S2 are strong cross-source results. Exact Chapter 5 quotations, a supported and cited Hume summary, and the only public query was the Hume URL. S2 declined the authenticity verdict while still helping.
- S3 failed because Muse called serendipity_explore for a plain request for a sentence to say. Its tool description excludes that case. The call declined without retrieval, and the released sentence was usable but brief, with no invitation to adjust it.

## Slide points

- Cross-source: 2/3 automated, 3/3 LLM-review.
- Strong tentative comparison and a clean refusal of a verdict.
- Over-eager tool use: exploration was called for a simple wording request.

## Limitations

- One synthetic attempt per Scene. Repeatability has not been established.
- Response review was performed by coding agents. No independent human validation or additional model grader was used.
- The Hume source is a live web page fetched at run time; a later run may see different content.
- This bundle recorded no effective per-role configuration (linger-a3fz). The run used the same .env settings as the other final results.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
