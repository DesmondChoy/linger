# Alice grounding and clarification

Final run. 2026-10-16T14:08:05.608424+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **4/4 Scenes passed**. LLM-review: **3/4 Scenes passed** (1 failed, 3 passed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a1434f06b8e6b73843d7fbc2d492f7-bec2654b34bb98c3>) (visibility verified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| alice-race-reflection | Quote chapter 3 exactly and make a useful personal connection. | The quotation and the reflection on lunches and the deposit were kept. The reply added one unsupported detail about taking the thimble from the pocket. | passed (1/1) | failed | Legitimate model failure. Muse added an unsupported action with the thimble. Provenance approved it, although the correct source was available. |
| alice-personal-comparison | Tell recognition apart from shared work, without book search. | The reply compared meaningful thanks with practical help. No book was chosen or searched. | passed (1/1) | passed | Personal reflection works without pulling in book context. |
| alice-spoiler-inference | Infer chapter 3, stay within it, and keep the personal connection. | The chapter limit, the latest chapter the reader has reached, was correct. The revision repaired the links to book passages and kept the sentence about lunches and the deposit. | passed (1/1) | passed | Checking source support sentence by sentence keeps the reflection when a factual claim is repaired. |
| alice-bottle-ambiguity | Ask for clarification about the ambiguous bottle episode, without guessing or giving away plot. | The reply asked for her latest completed chapter or scene. No book passage was retrieved for the reply, and no plot was explained. | passed (1/1) | passed | Ambiguity leads to a question rather than a guessed chapter limit. |

## Failures

### alice-race-reflection

**Failure type: Legitimate model failure** (cause confirmed). Automated passed; LLM-review failed.

**What failed.**

- The released answer says the Dodo "takes the thimble from her pocket".
- Muse wrote this paraphrase, and Provenance approved it as supported.
- The quotation and the reflection on lunches and the deposit were otherwise correct.

**Ground truth.**

- Every book claim must be supported by the cited passage (Chapter 3, lines 578-617).
- In that passage the Dodo asks "What else have you got in your pocket?", says "Hand it over here," and then presents the thimble.
- Alice hands the thimble over. The Dodo does not take it.

**Root cause.**

- Muse paraphrased the scene loosely. Its reflection skill says a source establishes only what it reports.
- Provenance then extracted the correct lines and summarised them as the Dodo "receiving the thimble". It still judged Muse's sentence supported.
- Provenance never compared who acted, and how, against its own extract.
- Suspected contributing factors:
  - Provenance's instructions for reviewing Muse's draft focus on linking claims to passages and on quotation mechanics. They do not explicitly ask who performed each paraphrased action.
  - This sentence also went through a repair of a line break inside the quotation. That repair may have drawn attention away from the paraphrase.
- Neither factor makes the instructions unclear, so the main failure type stays model failure.

**Proposed solution.**

- Keep this result.
- For a future comparison, add one line to Provenance's draft review. The line says a paraphrased event must keep the source's actor and action, or it is an unsupported claim (`unsupported_claim`).
- Add an eval case for that risk code, built on this sentence. As another option, compare a stronger reasoning setting for the draft review.
- To verify, replay this Scene's recorded draft through Provenance and check that Provenance flags the sentence.

## Worked example

Scene: `alice-spoiler-inference`.

Request: Infer the chapter limit, quote the Dodo, and connect the thimble to organising lunches and paying the deposit.

Before revision: The draft has a book interpretation with no linked passage, followed by a personal connection and an open question.

Repair instruction: The book interpretation is marked `needs_source`, which means it needs a linked passage. The personal sentence and the question are labelled to keep as written, and they need no linked passage.

Released answer: The book interpretation gains its linked passages. The sentence beginning "In your case, when you arrange the lunches and pay the deposit" and the question after it stay unchanged.

Lesson: A factual repair can keep the personal part of the answer without linking it to a book passage.

[Inspect this example in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare/cases?experiment=01a1434f06b8e6b73843d7fbc2d492f7-bec2654b34bb98c3&case=01a1434f06b8e6b73843d7fbc2d492f7-b3e1ba8fa2ad3f55>)


## Report points

- One run completed all four Scenes. Automated checks passed 4/4. LLM-review passed 3/4. Keep the remaining failure on record as a legitimate model failure.
- The personal-reflection defect `linger-mio6` is fixed. Source support is now checked in separate sentence fragments. In Scene 3 (`alice-spoiler-inference`), the revision repaired the links to book passages. The personal connection about lunches and the deposit stayed unchanged, and so did the question.
- The book-free personal question needed no book search. The chapter limit stayed within chapter 3. The ambiguous bottle episode led to a request for clarification, with no plot given away.
- In `alice-race-reflection`, Muse says the Dodo takes the thimble from Alice's pocket. The source has him ask Alice to hand it over. In its reasoning, Provenance describes the Dodo receiving the thimble, but it still approves Muse's sentence. No code defect was found behind this remaining failure. Keep this run. Do not rerun it to get a pass.

## Slide points

- Automated: 4/4 passed. LLM-review: 3/4 passed.
- A real revision kept the personal reflection while it repaired a book claim.
- Legitimate model failure: Muse adds an unsupported action, and Provenance misses it.

## Limitations

- One synthetic Scenario run with four Scenes. These results do not establish repeatability.
- Coding agents performed LLM-review. No independent human validation or additional grading model was used.
- Logfire can redact expected-output metadata that contains `session`. The complete input snapshots remain in `result.json`.
- The automated checks cover exact quotations, permitted evidence, and Provenance approval. They do not independently verify every paraphrased action. That is why the automated score of 4/4 sits beside 3/4 LLM-review passes.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
