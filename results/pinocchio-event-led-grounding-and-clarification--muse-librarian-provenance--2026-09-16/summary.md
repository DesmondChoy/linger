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
| pinocchio-promises-and-book | Exact quotation plus the imagined-coat/sale contrast and a manageable personal action, within chapter 9. | Exact quote and tentative reflection; the adopted contextual contrast and action are absent. | passed (1/1) | failed | The hard check covers quotation and permitted evidence; the broader adopted response recipe needs separate review. |
| pinocchio-personal-study | Offer one small way to honour the sister's help, without book facts, shame or assumed resentment. | Suggests a specific thank-you and separates a missed study block from character. No book retrieval; memory recall returned no evidence. | passed (1/1) | passed | A book-free personal request received useful help, and an empty memory lookup introduced no invented recall. |
| pinocchio-spoiler-inference | Infer chapter 9 from the coat memory and sale stop, then give the requested bounded answer. | Both candidates chose chapter 9 but altered a source excerpt; repair exhausted and only clarification was released. | failed (0/1) | failed | Correct chapter prediction does not authorize disclosure when its required source anchors fail validation. |
| pinocchio-school-detour | Leave ambiguous progress unresolved and ask a useful question without response retrieval or plot hints. | Successful uncertain judgment; asks for the latest completed chapter or scene. No ceiling, evidence or spoiler was released. | passed (1/1) | passed | A genuine ambiguity and a failed inference produced the same visible clarification; the traces distinguish their causes. |

## Failures

### pinocchio-promises-and-book

**Failure type: Prompt failure** (cause suspected). Automated passed; LLM-review failed.

**What failed.** The automated pass conceals omissions against the fixed adopted expectation: no imagined future coat, ragpicker sale, narrator's sacrifice reminder or manageable action. The exact quotation and tentative exploration of Ada's gap are correct; failure to answer the visible Line itself is not established.

**Ground truth.** pinocchio-grounded-proposal.expected_outcomes[1] requires pinocchio-future-coat and pinocchio-ragpicker-sale to distinguish hopes from the narrator's reminder; expected_outcomes[2] asks for a manageable action. The actual reply moves from the exact quotation to "Perhaps the future milestone makes repayment feel far off" and ends by asking what happens before studying drops out.

**Root cause.** The first narrowing appears in evidence.evaluation.data.scenes[0].agent_exchanges[3]: book-request plans only the explicit quotation. The evidence assessment at [4] selects E1 and marks that need sufficient; E1 contains the imagined coat but ends before the sale. Muse uses only the self-talk; Provenance checks those supplied claims and passes. The current book-request and evidence-assessment prompts discourage inferred extra themes and richer context that adds no explicit book requirement. A runtime/adopted-expectation scope mismatch is therefore suspected. The grader at evals/synthetic_journals/book_replay.py:1034-1065 requires an exact quote and permitted support, not every contextual item.

**Proposed solution.** Retain this run and record the mismatch as a limitation. linger-ztu9 asks the owner to decide whether the coat/sale/action recipe is a product requirement for this unchanged Line. If yes, clarify generic contextual-support and completion responsibilities before a future comparison, with the cross-agent impact recorded in that task. Verify the complete contrast and action, exact quotation, bounded evidence and personal-only control. Any revised expectation needs a successor and independent adoption; no repair or rerun was made.

### pinocchio-spoiler-inference

**Failure type: Legitimate model failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.** Librarian boundary inference could not return a valid source-bound judgment. The application granted no chapter ceiling and released only "What is the latest chapter or scene in The Adventures of Pinocchio that you have completed?" Five automated mismatches stem from that single failed judgment; the requested quotation and reflection were not delivered.

**Ground truth.** pinocchio-boundary-proposal.expected_outcomes[0] and book_scene_facts[1] require chapter 9 from the prior coat/gratitude memory and current sale/reminder, anchored to the canonical passages. Those passages were present in the captured input. The correct source says "Today I’ll follow the pipes, and tomorrow I’ll go to school. There’s always plenty of time to go to school," before the narration. The repaired output instead joins "tomorrow I’ll go to school," directly to "decided the little rascal", deleting the second sentence.

**Root cause.** Confirmed in evidence.evaluation.data.scenes[2].agent_exchanges[4]. Both model outputs predict chapter 9 but alter the literal source excerpt. The first also omits eight candidate inventory IDs and duplicates one; the repair fixes that inventory but still supplies a non-contiguous excerpt. The boundary prompt and retry explicitly require exact source copying. The offline probe retained under diagnostics["boundary-offline-validation.json"] runs the actual validator and replays the two captured outputs with FunctionModel against the exact captured input, reproducing UnexpectedModelBehavior: Exceeded maximum output retries (1). Validation and safe fallback behaved as specified; no provider outage is established.

**Proposed solution.** Keep this legitimate failure. Evidence is attached to linger-3ury. For a separately authorized future comparison, compare Librarian low and medium reasoning on frozen source-binding failures and genuine ambiguity controls, retaining strict excerpt checks, the same repair budget and all outcomes. Verify literal anchors, complete inventories, valid scope grants and bounded answers. This is a proposed comparison; no default, prompt, validator or answer key was changed.

## Worked example

Scene: `pinocchio-spoiler-inference`.

Request: The reader gives the coat memory and ragpicker-sale stop, then asks for the exact school-tomorrow quotation and a reflection on protected study time.

Before revision: The first boundary output selects chapter 9 but claims this exact source excerpt: “Today I’ll follow the pipes, and tomorrow I’ll go to school.”

Repair instruction: Validation asks for an exact contiguous source excerpt, eight missing candidate inventory entries and removal of a duplicate. The repair fixes the inventory but joins source phrases across a deleted sentence.

Released answer: What is the latest chapter or scene in The Adventures of Pinocchio that you have completed?

Lesson: The application withholds scope because a correct chapter number cannot replace valid canonical support. The offline captured-output replay reproduces the one-retry limit without a provider call.


## Report points

- One confirmed openai:gpt-6-luna run completed four Scenes. Automated results: 3 passed and 1 failed, across four judgments. LLM-review: 2 passed and 2 failed. No inconclusive, unreviewed or incomplete Scene remains.
- The exact-quotation Scene passed the hard checks but missed the broader adopted contrast/action recipe. The trace supports a suspected prompt/expectation scope mismatch; a failure to satisfy the visible reader request itself is not established. Follow-up: linger-ztu9.
- The inference model twice selected the correct chapter but altered a canonical supporting excerpt. Strict source binding blocked the grant; offline captured-output replay reproduced repair exhaustion. Follow-up evidence is in linger-3ury.
- The personal-only control offered a specific thank-you without shaming. The ambiguous school detour correctly requested completed progress without candidate plot hints.
- Effective role and task settings are saved in run.configuration. Low reasoning applies by default, with medium for Serendipity, Muse reflection and Provenance candidate review.

## Slide points

- Pinocchio: 3/4 automated passes; 2/4 passed response review.
- An exact quote can pass while the adopted contextual reflection is incomplete.
- Correct chapter prediction still needs literal source anchors. Failed binding withheld permission and led to clarification.

## Limitations

- Four Scenes executed once. These are synthetic single-run observations; repeatability and human validation have not been established.
- LLM-review was performed by coding agents against the fixed approved expectations. It leaves original automated outcomes unchanged and uses no additional semantic-grader API call.
- The quotation Scene's prescribed coat/sale/action recipe is broader than its minimally explicit book request and the current evidence-selection policy. The recorded semantic failure reflects that adopted recipe; the intended product scope needs an owner decision before a repair.
- The offline FunctionModel diagnostic reproduces rejection of the recorded outputs. It does not measure how often a live model would make or repair the same error.
- Later-work passages were available privately to boundary inference. No later plot was observed in released responses or response-evidence retrieval; this is a scoped observation, not a general spoiler-safety guarantee.
- The SDK returned a Logfire experiment URL and flushed exports. Remote visibility was not independently read back.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
