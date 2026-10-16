# Douglass event led grounding and clarification

Final run. 2026-10-16T20:36:40.432528+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **3/4 Scenes passed**. LLM-review: **3/4 Scenes passed** (3 passed, 1 failed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a144b49af9a3a6a99cf903e9a7e3c0-5b0077c6f07bdca0>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| douglass-grounded | Quote the 'It opened my eyes' sentence exactly within chapter 7 and reflect on seeing a problem versus finding an action. | Exact quotation in Chapter 7; a practical first step about tracing missing repair requests. | passed (1/1) | passed | Explicit-chapter grounding works end to end. |
| douglass-personal | Book-free, practical help moving from reviewing requests to one action. | No retrieval; one concrete status request. | passed (1/1) | passed | The personal control stayed book-free. |
| douglass-spoiler-inference | Infer chapter 7 from the earlier-lessons memory and the copybook stop, then quote the pit sentence and reflect, without the later New Bedford naming. | Boundary inference returned chapter 7 in one call with three correct anchors. The reply said it could not locate the pit sentence and reflected on a Chapter VI passage. | failed (0/1) | failed | The fix moved the failure downstream: the ceiling is now right, but the book-request plan dropped the reader's description of the sentence, so retrieval missed it. |
| douglass-uncertain | Clarify, because the remembered return to Baltimore fits Chapters VIII and X. | Uncertain; the reply asked for the latest chapter or scene; nothing retrieved. | passed (1/1) | passed | Ambiguity handled safely; the question asks for a location, not a remembered detail. |

## Failures

### douglass-spoiler-inference

**Failure type: Legitimate model failure** (cause suspected). Automated failed; LLM-review failed.

**What failed.** Automated failed boundary_support_differs_from_ground_truth. LLM-review failed because the reply omits the requested quotation: 'I couldn’t locate the exact “pit without a ladder” sentence in the passages available here.'

**Ground truth.** douglass-proposal-boundary: infer the chapter 7 ceiling from douglass-prior-prohibition (sec09) and douglass-copybook-stop (sec10-ln1597-1629), withholding douglass-later-new-name. The reader also asks for the pit sentence exactly, which lies in sec10-ln1517-1552 (chapter 7).

**Root cause.** Two separate causes. (1) Grader: boundary inference cited sec09-ln1346-1385, sec10-ln1597-1629 and sec10-ln1517-1552. The third is the pit passage the reader reports reading, so it is correct, but the key lists no optional anchors. This part is an expectation mismatch, the inverse of Animal Farm, where the key requires such anchors. (2) Model: the second Librarian book-request plan (agent_exchanges[6]) kept reader_spans 'quote that sentence exactly' but dropped 'he describes reading as showing him a pit without a ladder'. Retrieval returned only sec09-ln1346-1385 (chapter 6), evidence assessment marked the quotation unsupported (agent_exchanges[7]), and Muse said it could not find the sentence. Suspected, because the planner's choice of spans has no reasoning trace.

**Proposed solution.** Not implemented. (1) In a successor key, list reader-reported completed events as optional boundary support, and choose one rule for Douglass and Animal Farm. (2) For a future comparison, check whether book-request planning keeps a quotation's descriptive span in reader_spans; verify by replaying this Line's planning input and checking that retrieval returns sec10-ln1517-1552.

## Worked example

Scene: `douglass-spoiler-inference`.

Request: …Earlier in that account he describes reading as showing him a pit without a ladder. Could you quote that sentence exactly…?

Before revision: Previous run: two boundary attempts chose chapter 7 but failed the exactly-once inventory; the reader got a generic clarification.

Repair instruction: Fix 3e8a422c: the application derives the inventory.

Released answer: This run: chapter 7 accepted in one call. The book-request plan searched with 'quote that sentence exactly' only, and the reply said it could not locate the sentence.

Lesson: Removing one bottleneck exposed the next: the stage after boundary inference must carry the reader's description of what to retrieve.


## Report points

- Rerun after the Librarian boundary inventory fix (3e8a422c), which made the application derive the candidate inventory and merge repeated support anchors.
- Automated checks passed 3 of 4 Scenes, and LLM-review passed 3 of 4. Both fail douglass-spoiler-inference, as before, but for different reasons.
- The boundary fix worked here: Librarian inferred chapter 7 in one call with the right anchors, where the previous run exhausted its retry on inventory faults.
- The automated failure now comes from one extra, correct anchor that the key does not allow.
- The reader still did not get the quotation: a later book-request plan dropped the words describing the sentence, so retrieval missed it.

## Slide points

- Douglass: 3/4 automated, 3/4 LLM-review.
- Boundary fixed; the failure moved to retrieval planning.

## Limitations

- One synthetic attempt per Scene. Repeatability has not been established.
- Response review was performed by coding agents. No independent human validation or additional model grader was used.
- This bundle recorded no effective per-role configuration (linger-a3fz). The run used the same .env settings as the other final results.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
