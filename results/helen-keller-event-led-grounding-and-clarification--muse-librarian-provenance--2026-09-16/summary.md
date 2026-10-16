# Helen keller event led grounding and clarification

Final run. 2026-10-16T16:08:47.558580+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **3/4 Scenes passed**. LLM-review: **3/4 Scenes passed** (3 passed, 1 failed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a143bf25dd01d22e14be4e319ba362-5f0ef33309358756>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| keller-grounded | Quote the 'My disappointment was bitter' sentence exactly within Part I, Chapter 10, attributed to Keller; offer a tentative comparison with arranging the sister's flat. | Exact quotation and a tentative comparison. Provenance removed a correct 'Helen Keller writes' because its input had no author metadata. | passed (1/1) | passed | The reflection worked. A reviewer without book metadata can strip correct attribution. |
| keller-personal | Book-free, practical help offering support while leaving the flat's choices to the sister. | No retrieval; explicit wording that offers ideas or support for her choices; a closing question. | passed (1/1) | passed | A book-free personal question got concrete, respectful help. |
| keller-spoiler-inference | Infer Chapter 10 from the Perkins memory and the crab stop, then answer without the later Frost King discovery. | Librarian chose Chapter 10 with the right anchors twice. Both outputs failed mechanical checks (mis-copied IDs, then a duplicate support ID), so the reply was only a generic clarification. | failed (0/1) | failed | Same mechanism as Douglass: a correct decision discarded over ID bookkeeping. |
| keller-uncertain | Clarify, because the vanished pet fits both the canary (Chapter VIII) and the crab (Chapter X). | Librarian grounded the memory in both episodes and returned uncertain; the reply asked for the latest chapter or scene; nothing was retrieved. | passed (1/1) | passed | Genuine ambiguity was recognised for the right reason. The fixed clarification wording is generic. |

## Failures

### keller-spoiler-inference

**Failure type: Legitimate model failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.** Librarian boundary inference failed (boundary_inference_model_failed), so no ceiling was granted. The reader received the application's generic clarification instead of the requested quotation and reflection. All five automated failures follow from that one stage failure.

**Ground truth.** Infer the Part I, Chapter 10 ceiling from the authorised Perkins memory (keller-perkins-companionship) and the crab stopping event (keller-crab-disappearance, keller-disappointment-quotation). Withhold the later Frost King discovery (keller-later-frost-discovery).

**Root cause.** Both attempts returned the expected decision: Chapter 10, memory_supported, citing sec011-ln1127-1155 (Perkins) and sec012-ln1237-1254 (the crab). Attempt 1 listed three IDs that were never supplied. They match real candidates except for the section ordinal, sec014 for sec016 and sec021 for sec023, and the wrong ordinals equal those sections' chapter numbers. It also omitted the Perkins anchor from the inventory. Attempt 2 fixed the inventory but cited sec012-ln1237-1254 twice in supporting_evidence, once per excerpt. Boundary inference allows one output retry (src/linger/orchestration/boundary.py:57), so the stage failed. Each rule is stated in the skill and the repair prompt, so the primary type is model failure. The opaque-ID copying contract is a contributing design factor shared with Douglass and Pinocchio.

**Proposed solution.** Keep this result. Address it with the shared boundary-contract fix in linger-ey6i. Options: derive the inventory in code; allow several excerpts per support record, or merge them; raise output_retries to 2. Verify by replaying the captured outputs and checking that a Chapter 10 candidate is accepted.

## Worked example

Scene: `keller-spoiler-inference`.

Request: Tonight… I reached the part where the horseshoe crab disappears… then stopped there. Could you quote the final sentence, beginning 'My disappointment', exactly…?

Before revision: Attempt 1: Chapter 10, supported by the Perkins and crab passages. The inventory listed sec014-ln1597-1622, sec014-ln1606-1633 and sec021-ln2701-2724, which were never supplied. The real IDs are sec016 and sec023, whose chapter numbers are 14 and 21.

Repair instruction: Validator repair prompt naming the unknown and missing IDs, plus the duplicate support ID.

Released answer: Attempt 2: same correct decision, but sec012-ln1237-1254 appeared twice in supporting_evidence. The request limit was reached, and the reply was 'What is the latest chapter or scene in The Story of My Life that you have completed?'

Lesson: Opaque IDs with section ordinals that differ from chapter numbers invite copy errors. Every slip discards a correct decision.


## Report points

- Automated checks passed 3 of 4 Scenes, and LLM-review passed 3 of 4. Both fail keller-spoiler-inference.
- Spoiler inference failed in the Librarian's boundary output, as in Douglass and Pinocchio. Both attempts chose the right Chapter 10 ceiling and anchors. Attempt 1 mis-copied three candidate IDs, writing the chapter number where the section ordinal belongs (sec014 for sec016). Attempt 2 cited one record twice. The single retry was exhausted, and the reader got a generic clarification.
- In the grounded Scene, Provenance removed a correct 'Helen Keller writes' as an unsupported claim. Its review input carries no work title or author.
- The uncertain Scene identified both vanished-pet episodes and correctly declined to choose.

## Slide points

- Helen Keller: 3/4 automated, 3/4 LLM-review.
- Right chapter, wrong IDs: the model wrote chapter numbers into section IDs.
- Safe fallback: a clarification, with no spoiler.

## Limitations

- One synthetic attempt per Scene. Repeatability has not been established.
- Response review was performed by coding agents. No independent human validation or additional model grader was used.
- This bundle recorded no effective per-role configuration (linger-a3fz). The run used the same .env settings as the other final results.
- The answer for the failed Scene was never generated, so its quotation and spoiler behaviour under a Chapter 10 grant are untested in this run.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
