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
| farm-decision-reversal | Quote Squealer's two sentences exactly; link the framing to lost debate and, tentatively, to the reader's project lead. | Exact quotation within chapter 5; sacrifice and private-committee framing; tentative personal link. | passed (1/1) | passed | Grounded quotation and a restrained analogy worked together. |
| farm-personal-trust | Book-free reflection on acknowledging the lead's effort while asking for a say. | Reflection plus brief suggested wording, approved by Provenance on the first review. | passed (1/1) | passed | After the scope fix, a book-free personal question gets real help instead of a refusal. |
| farm-spoiler-inference | Infer chapter 5 from the puppies memory and the 'tactics' stopping event, anchoring three events. | Chapter 5 inferred and answered correctly; one required anchor ('recognised them as those puppies') was missing. | failed (0/1) | passed | The answer was right, but the audit trail was incomplete, and the hard check measures the trail. |
| farm-interrupted-discussion | Clarify progress, since the sheep's chant ends discussion in both chapter 5 and chapter 7. | Librarian returned uncertain; the reply asked for the latest chapter or scene; nothing was retrieved. | passed (1/1) | passed | Genuine ambiguity led to a clean clarification. |

## Failures

### farm-spoiler-inference

**Failure type: Prompt failure** (cause suspected). Automated failed; LLM-review passed.

**What failed.** The Librarian inferred the correct chapter 5 ceiling, and the released answer was correct and spoiler-safe. Its boundary support cited only two anchors: the puppies memory (chapter 3) and tonight's windmill and tactics stop (chapter 5). The automated boundary_support_differs_from_ground_truth check failed because the third adopted anchor was missing.

**Ground truth.** The adopted expectation anchors three events: the puppies being taken (chapter 3), the reader recognising the dogs as those puppies (chapter 5, lines 1082-1114), and the tactics acceptance (chapter 5). The reader reported the recognition directly: "I recognised them as those puppies". The Librarian placed both recognition passages in event_resolution.other_evidence_ids.

**Root cause.** The Librarian's boundary-inference skill says to "Select only the needed current-event and memory anchors as boundary support". Tonight's stopping event alone establishes chapter 5, so omitting the earlier reported event is consistent with that instruction. Nothing in the skill asks for an anchor for each completed event the reader reports. The prompt and the adopted expectation therefore disagree. This is suspected, not confirmed, because the model might still have omitted the anchor under clearer wording.

**Proposed solution.** Keep this result and the fixed expectation. Propose a Librarian boundary-inference change: cite an anchor for each reader-reported completed event that the candidate passages locate, not only the stopping event. Check cross-agent impact on the Provenance and Muse handoffs first. Verify by replaying the captured boundary-inference input and checking that farm-puppies-recognised appears in supporting_evidence.

## Worked example

Scene: `farm-personal-trust`.

Request: How can I acknowledge my project lead's effort while still asking to have a say?

Before revision: First run: Provenance flagged Muse's suggested wording as out_of_scope, and the revision released only 'I can't help draft workplace-conflict language.'

Repair instruction: linger-em30: the Muse and Provenance scope rules now treat reflection on the reader's own life, with or without a book, as in scope, including brief wording they could use.

Released answer: Rerun: “I hear you saying you’re carrying a lot for us, and I appreciate the effort… Could we talk about how decisions are made when plans change?”, approved on the first review.

Lesson: A no-retrieval check passed both the refusal and the help. Only reading the reply showed the difference.


## Report points

- Automated checks passed 3 of 4 Scenes, and coding-agent response review passed 4 of 4.
- Before-fix baseline, 16 October 2026 at 14:20 Singapore time: 3/4 automated passes and 2/4 LLM-review passes. The personal control was refused, and spoiler inference failed on two mis-copied excerpts. The linger-em30 prompt fix clarified that book-free personal reflection is in scope for Muse and Provenance. [Superseded run in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a1435c6770990adf776e268e93bd29-1471676db92ae8b6>).
- This rerun replaces the first final Animal Farm result after the linger-em30 fix, which put book-free personal reflection in scope for Muse and Provenance.
- In the first run, the book-free personal control was refused after an out_of_scope finding. After the fix, Provenance approved a useful reflection on the first review.
- Spoiler inference reached the right chapter 5 ceiling and answer, but failed the hard check for omitting one required support anchor.
- The ambiguous repeated chant again led to a clarification with no retrieval or disclosure.

## Slide points

- Animal Farm: 3/4 automated, 4/4 response review.
- Scope fix: refusal → real help on a book-free personal question.
- The remaining failure is an incomplete audit trail, not a wrong answer.

## Limitations

- One synthetic attempt per run: four Scenes executed once after the fix. Repeatability has not been established.
- Response review was performed by coding agents. No independent human validation or additional model grader was used.
- The instruction change was made after the first run's failure, so this result is not blind to that failure mode.
- This bundle recorded no effective per-role configuration (linger-a3fz). The run used the same .env settings as the other final results.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
