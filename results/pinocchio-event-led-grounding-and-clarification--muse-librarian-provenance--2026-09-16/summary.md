# Pinocchio event-led grounding and clarification

Final run. 2026-10-16T15:51:37.768954+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **3/4 Scenes passed**. LLM-review: **2/4 Scenes passed** (2 failed, 2 passed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a143af7a975c5ae32a17f64fb665d1-54516710781947bf>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| pinocchio-promises-and-book | Quote Pinocchio's words exactly, staying within chapter 9. Contrast the coat he imagines buying his father with his sale of the A-B-C book. Suggest one manageable action for her. | The reply quoted exactly and reflected tentatively. It left out the coat-and-sale contrast and the action that the approved answer asks for. | passed (1/1) | failed | The automated check covers only the quotation and the permitted passages. The rest of the approved answer needs a separate review. |
| pinocchio-personal-study | Offer one small way to honour her sister's help. Use no book facts and no shame, and do not assume her sister resents her. | The reply suggested a specific thank-you. It separated a missed study block from her character. No book passages were retrieved, and the memory search found no notes. | passed (1/1) | passed | A personal request with no book in it got useful help. The empty memory search led to no invented memories. |
| pinocchio-spoiler-inference | Work out that she has read to chapter 9, from her note about the coat and the sale where she stopped. Then answer her request using only passages up to chapter 9. | Both Librarian attempts chose chapter 9, but each altered a passage it quoted from the source. The one allowed retry was used up, and only a clarifying question was released. | failed (0/1) | failed | A correct chapter guess does not open the book to the reply when the quoted passages that support the guess fail validation. |
| pinocchio-school-detour | Her message fits more than one place in the book, so leave her reading position unresolved. Ask a useful question. Retrieve no passages for the reply and give no plot hints. | Boundary inference correctly judged her position uncertain. The reply asked for the latest chapter or scene she has finished. No chapter limit was set, and no passage or spoiler was released. | passed (1/1) | passed | A real ambiguity here and a failed inference in `pinocchio-spoiler-inference` produced the same clarifying question. Only the traces show the different causes. |

## Failures

### pinocchio-promises-and-book

**Failure type: Prompt failure** (cause suspected). Automated passed; LLM-review failed.

**What failed.**

- The automated pass hides gaps against the approved answer, which stays fixed. The reply left out:
  - the future coat that Pinocchio imagines
  - the sale of the book to the ragpicker
  - the narrator's reminder of Geppetto's sacrifice
  - a manageable action for her
- The exact quotation is correct. The tentative look at the gap she described is also correct.
- It is not established that the reply failed the request in her message itself.

**Ground truth.**

- The approved answer (`pinocchio-grounded-proposal`) sets two requirements that matter here:
  - `expected_outcomes[1]` requires the passages `pinocchio-future-coat` and `pinocchio-ragpicker-sale`, used to separate Pinocchio's hopes from the narrator's reminder.
  - `expected_outcomes[2]` asks for a manageable action.
- The actual reply moves from the exact quotation to "Perhaps the future milestone makes repayment feel far off".
- It ends by asking what happens before studying drops out.

**Root cause.**

- The request first narrows in the Librarian's book-request plan, the step that decides what to look up (`evidence.evaluation.data.scenes[0].agent_exchanges[3]`). The plan covers only the quotation she asked for.
- Next, the Librarian's evidence assessment (`agent_exchanges[4]`) selects passage `E1` and marks that need as "sufficient".
- `E1` contains the imagined coat but ends before the sale.
- Muse uses only Pinocchio's words to himself. Provenance checks those supplied claims and passes them.
- The current book-request and evidence-assessment prompts discourage extra themes that the model infers. They also discourage richer context that adds no explicit book requirement.
- So the suspected cause is a mismatch in scope. The approved answer expects more than the runtime is built to fetch.
- The automated grader (`evals/synthetic_journals/book_replay.py:1034-1065`) requires an exact quote and permitted passages. It does not require every piece of context.

**Proposed solution.**

- Keep this run, and record the mismatch as a limitation.
- Beads `linger-ztu9` asks the owner to decide one question. Should the reply to this unchanged message have to include the coat, the sale, and an action?
- If yes, clarify in general terms which step supplies supporting context and which step makes the answer complete. Do this before a future comparison, and record the effect on other agents in that task.
- Then verify the full contrast and action, the exact quotation, the chapter limit on passages, and the personal-only control Scene.
- Any revised expectation needs a new Scenario, and a person must approve it again.
- No repair or rerun was made.

### pinocchio-spoiler-inference

**Failure type: Legitimate model failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.**

- Boundary inference is the Librarian step that works out how far the reader has read. Here it could not return a valid judgment tied to the source text.
- So the application set no chapter limit, which caps the chapters the reply may use.
- The only released reply was "What is the latest chapter or scene in The Adventures of Pinocchio that you have completed?"
- Five automated mismatches all come from that one failed judgment.
- She did not get the quotation or the reflection she asked for.

**Ground truth.**

- The approved answer requires chapter 9 (`pinocchio-boundary-proposal.expected_outcomes[0]` and `book_scene_facts[1]`).
- Chapter 9 follows from two things:
  - her earlier note about the coat and Pinocchio's gratitude
  - the sale and the reminder of Geppetto, where she stopped this time
- The judgment must be tied to the book's own passages. Those passages were in the captured input.
- The source text says "Today I’ll follow the pipes, and tomorrow I’ll go to school. There’s always plenty of time to go to school," before the narration.
- The output after the retry joins "tomorrow I’ll go to school," directly to "decided the little rascal". It deletes the second sentence.

**Root cause.**

- Confirmed in `evidence.evaluation.data.scenes[2].agent_exchanges[4]`.
- Both model outputs choose chapter 9, but both alter the exact text they quote from the source.
- The first output has a second fault. It must list every candidate passage it was given exactly once. It left out eight passage IDs and listed one twice.
- The retry fixes that list but still quotes text that is not continuous in the source.
- The boundary prompt and the retry both say to copy the source exactly.
- An offline check, kept in `diagnostics["boundary-offline-validation.json"]`, reproduced the failure:
  - It runs the real validator.
  - It replays the two captured outputs with `FunctionModel` against the exact captured input.
  - It reproduces `UnexpectedModelBehavior: Exceeded maximum output retries (1)`.
- Validation and the safe fallback behaved as specified. No provider outage is established.

**Proposed solution.**

- Keep this as a legitimate failure. The evidence is attached to Beads `linger-3ury`.
- Proposed future comparison, which needs separate approval:
  - Run the Librarian at low and at medium reasoning effort.
  - Use saved cases where the quoted source text failed validation, and control cases with genuine ambiguity.
  - Keep the strict quotation checks, the same retry budget, and all outcomes.
  - Verify exact quoted passages, complete candidate lists, valid chapter limits, and answers that stay within the limit.
- This is a proposal only. No default, prompt, validator, or approved answer was changed.

## Worked example

Scene: `pinocchio-spoiler-inference`.

Request: She has an earlier note about the coat. Her message says she stopped at the ragpicker sale. She asks for Pinocchio's exact words about going to school tomorrow, and for a reflection on her protected study time.

Before revision: The first boundary-inference output chooses chapter 9. It gives this as an exact quote from the source: “Today I’ll follow the pipes, and tomorrow I’ll go to school.”

Repair instruction: Validation asks for an exact, continuous quote from the source. It also asks for the eight missing candidate passages and the removal of one duplicate. The retry fixes the candidate list but joins two phrases of the source across a deleted sentence.

Released answer: "What is the latest chapter or scene in The Adventures of Pinocchio that you have completed?"

Lesson: The application withholds the book from the reply, because a correct chapter number cannot replace valid quotes from the source. The offline replay of the captured outputs reproduces the one-retry limit without a provider call.


## Report points

- One confirmed run with `openai:gpt-6-luna` completed four Scenes. Automated: 3 passed and 1 failed, across four checks. LLM-review: 2 passed and 2 failed. No Scene is left inconclusive, unreviewed, or incomplete.
- The exact-quotation Scene passed the automated checks but missed the wider contrast and the action that the approved answer asks for. The trace supports a suspected mismatch in scope between the prompts and the approved answer. It is not established that the reply failed her actual request. Follow-up: `linger-ztu9`.
- Boundary inference twice chose the correct chapter but altered a supporting passage it quoted from the book. The strict check that quotes match the source blocked access to the book. An offline replay of the captured outputs reproduced the used-up retry. Follow-up evidence is in `linger-3ury`.
- In the personal-only control Scene, the reply offered a specific thank-you without shaming her. In the ambiguous school-detour Scene, the reply correctly asked how far she had read, without hints from the possible matching passages.
- The settings each agent and task actually used are saved in `run.configuration`. Reasoning effort is low by default. It is medium for Serendipity, Muse's reflection (`muse.reflection`), and Provenance's review of the draft reply (`provenance.candidate-review`).

## Slide points

- Pinocchio: 3/4 automated passes. 2/4 passed LLM-review.
- An exact quote can pass the automated checks while the reflection that the approved answer asks for is incomplete.
- A correct chapter guess still needs exact quotes from the source. When the quotes failed, the application withheld the book and asked a clarifying question.

## Limitations

- Each of the four Scenes ran once. These are single synthetic runs. Repeatability and human validation have not been established.
- LLM-review was done by coding agents against the fixed approved answers. It leaves the original automated outcomes unchanged and makes no extra call to a grader model.
- In the quotation Scene, the approved answer asks for the coat, the sale, and an action. That is broader than what her message explicitly asks of the book, and broader than the current rules for choosing passages. The recorded LLM-review failure reflects that approved answer. The owner must decide the intended product scope before any repair.
- The offline `FunctionModel` check reproduces the rejection of the recorded outputs. It does not measure how often a live model would make or repair the same error.
- Boundary inference had private access to passages from later in the book. No later plot appeared in the released replies or in the passages retrieved for them. This is an observation about this run only. It is not a general guarantee against spoilers.
- The SDK returned a Logfire experiment URL and flushed its exports. Whether the traces are visible remotely was not checked independently.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
