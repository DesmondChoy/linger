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
| alice-race-reflection | Exact chapter 3 quotation and a useful personal connection. | Quote and lunch/deposit reflection retained; one unsupported detail about taking the thimble from the pocket. | passed (1/1) | failed | Legitimate model failure. Muse added an unsupported thimble action, and Provenance approved it despite the correct source being available. |
| alice-personal-comparison | Separate recognition from shared work without book retrieval. | Compared meaningful thanks with practical help; no book routing or retrieval. | passed (1/1) | passed | Personal reflection works without importing book context. |
| alice-spoiler-inference | Infer chapter 3, stay within it, and preserve the personal connection. | Correct reading limit; revision repaired book mapping and retained the lunch/deposit bridge. | passed (1/1) | passed | Coverage by sentence preserves reflection during factual repair. |
| alice-bottle-ambiguity | Clarify the ambiguous bottle episode without guessing or disclosing plot. | Asked for the latest completed chapter or scene; no response retrieval or plot explanation. | passed (1/1) | passed | Ambiguity leads to clarification rather than a guessed reading limit. |

## Failures

### alice-race-reflection

**Failure type: Legitimate model failure** (cause confirmed). Automated passed; LLM-review failed.

**What failed.** The released answer says the Dodo "takes the thimble from her pocket". Muse wrote this paraphrase, and Provenance approved it as supported. The quotation and the lunch/deposit reflection were otherwise correct.

**Ground truth.** Every book claim must be supported by the cited passage (Chapter 3, lines 578-617). There the Dodo asks "What else have you got in your pocket?", says "Hand it over here," and then presents the thimble. Alice hands it over; the Dodo does not take it.

**Root cause.** Muse paraphrased the scene loosely, although its reflection skill says a source establishes only what it reports. Provenance then excerpted the correct lines and summarised them as the Dodo "receiving the thimble", yet judged Muse's sentence supported. It never compared the actor and action with its own excerpt. Suspected contributing factors: Provenance's candidate-review instructions focus on mapping and quotation mechanics without explicitly asking who performed each paraphrased action, and this sentence also went through a quotation line-break repair that may have drawn attention away from the paraphrase. Neither makes the instructions unclear, so the primary type stays model failure.

**Proposed solution.** Keep this result. For a future comparison, add one line to Provenance candidate review: a paraphrased event must keep the source's actor and action, otherwise it is unsupported_claim. Add a risk-code eval case built on this sentence, or compare a stronger reasoning setting for candidate review. Verify by replaying this Scene's captured candidate through Provenance and checking that the sentence is flagged.

## Worked example

Scene: `alice-spoiler-inference`.

Request: Infer the reading limit, quote the Dodo, and connect the thimble to organising lunches and paying the deposit.

Before revision: The draft contains an unmapped book interpretation followed by a personal connection and an open question.

Repair instruction: The book interpretation is marked needs_source. The personal bridge and question receive preservation labels and require no source mapping.

Released answer: The book interpretation gains its source mappings. The sentence beginning "In your case, when you arrange the lunches and pay the deposit" and the following question remain unchanged.

Lesson: A factual repair can preserve the personal part of the answer without mapping it to book evidence.

[Inspect this example in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare/cases?experiment=01a1434f06b8e6b73843d7fbc2d492f7-bec2654b34bb98c3&case=01a1434f06b8e6b73843d7fbc2d492f7-b3e1ba8fa2ad3f55>)


## Report points

- One run completed all four Scenes. Automated checks passed 4/4; LLM-review passed 3/4. Retain the remaining failure as a legitimate model error.
- The personal-reflection defect linger-mio6 is fixed. Source coverage is assessed in separate sentence fragments. In Scene 3, factual mapping was repaired while the personal lunch/deposit connection and question remained unchanged.
- The personal-only control required no book retrieval. Reading-limit inference stayed within chapter 3, and the ambiguous bottle episode produced clarification without plot disclosure.
- In alice-race-reflection, Muse says the Dodo takes the thimble from Alice's pocket. The source has him ask Alice to hand it over. Provenance describes receiving the thimble in its rationale but approves Muse's sentence. No code defect was identified behind this remaining error. Keep this run without repeating it to obtain a pass.

## Slide points

- Automated: 4/4 passed. LLM-review: 3/4 passed.
- Actual revision preserved personal reflection while repairing a book claim.
- Legitimate model failure: Muse adds an unsupported action, and Provenance misses it.

## Limitations

- One synthetic Scenario invocation with four Scenes; these observations do not establish repeatability.
- Coding agents performed LLM-review. No independent human validation or additional grading model was used.
- Logfire can redact expected-output metadata containing session. The complete input snapshots remain in result.json.
- Automated checks cover exact quotations, permitted evidence, and Provenance approval. They do not independently verify every paraphrased action; the 4/4 automated score therefore coexists with 3/4 LLM-review passes.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
