# Animal farm event led grounding and clarification

Final run. 2026-10-16T15:22:01.642857+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **3/4 Scenes passed**. LLM-review: **4/4 Scenes passed** (4 passed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a14392eab6b82c6460e6a1fc730af2-2c14e319742fc430>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| farm-decision-reversal | Quote Squealer's two sentences exactly. Link his framing to the loss of debate and, tentatively, to Ilya's project lead. | The reply quoted exactly from chapter 5. It described the framing as sacrifice and as a private committee, and made a tentative link to Ilya's own life. | passed (1/1) | passed | An exact quotation and a restrained comparison worked together. |
| farm-personal-trust | Help him reflect, without the book, on how to acknowledge his lead's effort while he asks for a say. | The reply gave reflection and brief suggested wording. Provenance approved it on the first review. | passed (1/1) | passed | After the scope fix, a book-free personal question gets real help instead of a refusal. |
| farm-spoiler-inference | Infer chapter 5 from the puppies memory and the 'tactics' scene where he stopped. Cite a supporting passage for each of three events. A supporting passage is a book passage that places an event the reader reports. | The Librarian inferred chapter 5, and the reply was correct. One required supporting passage was missing, for 'recognised them as those puppies'. | failed (0/1) | passed | The answer was right, but one supporting passage was missing. The automated check grades the supporting passages. |
| farm-interrupted-discussion | Ask how far he has read, because the sheep's chant ends discussion in both chapter 5 and chapter 7. | The Librarian returned `uncertain`. The reply asked for his latest chapter or scene. No book passage was retrieved. | passed (1/1) | passed | A truly ambiguous event led to a clean request for clarification. |

## Failures

### farm-spoiler-inference

**Failure type: Prompt failure** (cause suspected). Automated failed; LLM-review passed.

**What failed.**

- The Librarian inferred the correct chapter limit, chapter 5. The chapter limit is the latest chapter the reader has reached.
- The released answer was correct and gave away nothing beyond that limit.
- Boundary inference, the Librarian step that works out how far the reader has read, cited only two supporting passages:
  - the puppies memory (chapter 3)
  - tonight's stop at the windmill and "tactics" (chapter 5)
- The approved answer has a third supporting passage. Because it was missing, the automated check failed (`boundary_support_differs_from_ground_truth`).

**Ground truth.**

- The approved answer cites a supporting passage for each of three events:
  - the puppies being taken (chapter 3)
  - Ilya recognising the dogs as those puppies (chapter 5, lines 1082-1114)
  - the acceptance of "tactics" (chapter 5)
- Ilya reported the recognition directly: "I recognised them as those puppies".
- The Librarian put both recognition passages in `event_resolution.other_evidence_ids`.

**Root cause.**

- The boundary-inference skill says to "Select only the needed current-event and memory anchors as boundary support".
- Tonight's stopping point alone establishes chapter 5. Leaving out the earlier event he reported is therefore consistent with that instruction.
- Nothing in the skill asks for a supporting passage for each completed event the reader reports.
- The prompt and the approved answer therefore disagree.
- The cause is suspected, not confirmed. The model might still leave out the passage under clearer wording.

**Proposed solution.**

- Keep this result. Keep the approved answer unchanged.
- Propose a change to the boundary-inference skill. The Librarian should cite a supporting passage for each completed event that the reader reports and the candidate passages locate, not only for the stopping point.
- Before the change, check how it affects what the Librarian passes to Provenance and Muse.
- To verify, replay the recorded boundary-inference input and check that `farm-puppies-recognised` appears in `supporting_evidence`.

## Worked example

Scene: `farm-personal-trust`.

Request: How can I acknowledge my project lead's effort while still asking to have a say?

Before revision: First run: Provenance flagged Muse's suggested wording as out of scope (`out_of_scope`). The revised reply said only 'I can't help draft workplace-conflict language.'

Repair instruction: Fix `linger-em30`: the Muse and Provenance scope rules now treat reflection on the reader's own life as in scope, with or without a book. That includes brief wording the reader could use.

Released answer: Rerun: “I hear you saying you’re carrying a lot for us, and I appreciate the effort… Could we talk about how decisions are made when plans change?” Provenance approved it on the first review.

Lesson: A check that no book passage was retrieved passed both the refusal and the help. Only reading the reply showed the difference.


## Report points

- Automated checks passed 3 of 4 Scenes, and LLM-review passed 4 of 4.
- First run before the fix (16 October 2026, 14:20 Singapore time): 3/4 automated passes and 2/4 LLM-review passes. The book-free personal question was refused. The spoiler-inference Scene failed on two mis-copied excerpts. The `linger-em30` prompt fix made clear that book-free personal reflection is in scope for Muse and Provenance. [Superseded run in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a1435c6770990adf776e268e93bd29-1471676db92ae8b6>).
- This rerun replaces the first final Animal Farm result. It ran after the `linger-em30` fix, which put book-free personal reflection in scope for Muse and Provenance.
- In the first run, the book-free personal question was refused after an out-of-scope finding (`out_of_scope`). After the fix, Provenance approved a useful reflection on the first review.
- The spoiler-inference Scene reached the right chapter limit (chapter 5) and the right answer. It failed the automated check because one required supporting passage was missing.
- The ambiguous, repeated chant again led to a request for clarification. Nothing was retrieved from the book or given away.

## Slide points

- Animal Farm: 3/4 automated, 4/4 LLM-review.
- Scope fix: a book-free personal question now gets real help instead of a refusal.
- The remaining failure is a missing supporting passage, not a wrong answer.

## Limitations

- The four Scenes ran once each after the fix, with synthetic data. Repeatability has not been established.
- Coding agents performed LLM-review. No independent human validation or additional grading model was used.
- The instruction change was made after the first run failed, so this rerun is not blind to that kind of failure.
- This result did not record the settings each agent actually ran with (`linger-a3fz`). The run used the same `.env` settings as the other final results.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
