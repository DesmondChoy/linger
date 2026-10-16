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
| douglass-grounded | Quote the sentence that begins "It opened my eyes" exactly, staying within chapter 7. Reflect on the gap between seeing a problem and finding an action. | The reply quoted the sentence exactly from Chapter 7. It suggested a practical first step about tracing the missing repair requests. | passed (1/1) | passed | When she names her chapter, answering from the book works end to end. |
| douglass-personal | Give practical help with no book in it, to move her from reviewing requests to one action. | Nothing was retrieved. The reply suggested one concrete step, which is to ask for the status of one request. | passed (1/1) | passed | The personal-only control Scene stayed free of the book. |
| douglass-spoiler-inference | Work out that she has read to chapter 7, from her note about the earlier lessons and the copybook scene where she stopped. Then quote the pit sentence and reflect. Leave out the later scene in New Bedford where he gets the name Douglass. | Boundary inference returned chapter 7 in one call, citing three correct supporting passages. The reply said it could not find the pit sentence, and reflected on a passage from Chapter VI. | failed (0/1) | failed | The fix moved the failure to a later step. The chapter limit is now right. But the book-request plan dropped her description of the sentence, so the search missed it. |
| douglass-uncertain | Ask a clarifying question, because the return to Baltimore she remembers fits both Chapter VIII and Chapter X. | Boundary inference judged her position uncertain. The reply asked for the latest chapter or scene she has completed. Nothing was retrieved. | passed (1/1) | passed | The ambiguity was handled safely. The question asks where she is in the book, not for a detail she remembers. |

## Failures

### douglass-spoiler-inference

**Failure type: Legitimate model failure** (cause suspected). Automated failed; LLM-review failed.

**What failed.**

- The automated check failed because the passages cited for her reading position differ from the approved answer (`boundary_support_differs_from_ground_truth`).
- LLM-review failed because the reply leaves out the quotation she asked for. It said "I couldn’t locate the exact “pit without a ladder” sentence in the passages available here."

**Ground truth.**

- The approved answer (`douglass-proposal-boundary`) expects chapter 7 as the limit on what the reply may use.
- It infers that limit from two passages:
  - `douglass-prior-prohibition` (`sec09`)
  - `douglass-copybook-stop` (`sec10-ln1597-1629`)
- It withholds `douglass-later-new-name`.
- She also asks for the pit sentence exactly. That sentence is in `sec10-ln1517-1552` (chapter 7).

**Root cause.**

- There are two separate causes.
- Cause 1, in the grader:
  - Boundary inference, the Librarian step that works out how far she has read, cited three passages: `sec09-ln1346-1385`, `sec10-ln1597-1629`, and `sec10-ln1517-1552`.
  - The third is the pit passage, which she says she has read. So citing it is correct.
  - The approved answer lists no optional supporting passages.
  - This part is a mismatch with the approved answer. It is the opposite of the Animal Farm Scenario, where the approved answer requires such passages.
- Cause 2, in the model:
  - The book-request plan is the Librarian step that picks the parts of her message to search with (`reader_spans`).
  - The second plan (`agent_exchanges[6]`) kept "quote that sentence exactly" but dropped "he describes reading as showing him a pit without a ladder".
  - The search returned only `sec09-ln1346-1385` (chapter 6).
  - The Librarian's evidence assessment marked the quotation unsupported (`agent_exchanges[7]`).
  - Muse then said it could not find the sentence.
- Cause 2 is suspected, not confirmed, because the planner leaves no reasoning trace for the parts it keeps.

**Proposed solution.**

- Not implemented.
- For cause 1, write a successor version of the approved answer. List the events she says she has finished as optional supporting passages.
- Choose one rule for both the Douglass and Animal Farm Scenarios.
- For cause 2, a future comparison should check whether the book-request plan keeps the words that describe a requested quotation in `reader_spans`.
- To verify, replay the planning input for this message and check that the search returns `sec10-ln1517-1552`.

## Worked example

Scene: `douglass-spoiler-inference`.

Request: Part of her message: "…Earlier in that account he describes reading as showing him a pit without a ladder. Could you quote that sentence exactly…?"

Before revision: Previous run: two boundary-inference attempts chose chapter 7. Both failed the rule that every candidate passage is listed exactly once. She got a generic clarifying question.

Repair instruction: Fix `3e8a422c`: the application builds the list of candidate passages itself.

Released answer: This run: chapter 7 was accepted in one call. The book-request plan searched only with "quote that sentence exactly". The reply said it could not find the sentence.

Lesson: Fixing one step exposed the next problem. The step after boundary inference must pass on her description of what to look up.


## Report points

- Rerun after the Librarian fix `3e8a422c`. With that fix, the application builds the list of candidate passages for boundary inference and merges repeated supporting passages.
- Automated checks passed 3 of 4 Scenes, and LLM-review passed 3 of 4. Both fail `douglass-spoiler-inference`, as before, but for different reasons.
- The fix worked here. The Librarian inferred chapter 7 in one call with the right supporting passages. The previous run used up its retry on faults in the candidate list.
- The automated failure now comes from one extra supporting passage. That passage is correct, but the approved answer does not allow it.
- She still did not get the quotation. A later book-request plan dropped the words that describe the sentence, so the search missed it.

## Slide points

- Douglass: 3/4 automated, 3/4 LLM-review.
- Boundary inference is fixed. The failure moved to planning what to search for.

## Limitations

- One synthetic attempt per Scene. Repeatability has not been established.
- LLM-review was done by coding agents. No independent human validation or additional model grader was used.
- This bundle did not record the settings each agent actually used (`linger-a3fz`). The run used the same `.env` settings as the other final results.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
