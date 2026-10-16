# Alice pigeon grounding and spoilers

Final run. 2026-10-16T16:07:21.700198+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **2/3 Scenes passed**. LLM-review: **2/3 Scenes passed** (1 failed, 2 passed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a143bf25befbf4ce6acde948553e71-346a3d314438f5d6>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| pigeon-reflection | Infer Chapter 5 from the Caterpillar memory and the Pigeon event, then quote 'I—I'm a little girl,' with 'rather doubtfully' exactly and reflect on naming a new role. | Librarian returned uncertain with insufficient_context in one call, although a supplied passage contained the serpent exchange. The reply was only a generic clarification. | failed (0/2) | failed | A clear, unique event was declared unlocatable. The uncertain exit skips every check. |
| uncertain-growth | Clarify, because 'Alice gets bigger again' fits more than one later episode. | Librarian returned uncertain; the reply asked for the latest chapter or scene; nothing was retrieved. | passed (1/1) | passed | Ambiguity was handled correctly. The fixed question asks for a location, not a remembered detail. |
| personal-reflection | Book-free help exploring the awkwardness of the manager title, with an adaptable introduction. | No retrieval; a tentative explanation and two introductions in the reader's terms. | passed (1/1) | passed | A book-free personal question got useful wording. |

## Failures

### pigeon-reflection

**Failure type: Legitimate model failure** (cause suspected). Automated failed; LLM-review failed.

**What failed.** Librarian boundary inference returned uncertain with reason_code insufficient_context, so no ceiling was granted. Nothing was retrieved, and the reader got the generic clarification instead of the quotation and reflection. Both proposals (pigeon-grounding and pigeon-boundary) fail as a result.

**Ground truth.** Infer the Chapter 5 position from the authorised remembered-caterpillar Prop and the current Pigeon event. Quote '“I—I’m a little girl,” said Alice, rather doubtfully' exactly (evidence pigeon, Chapter 5) and answer within that scope with no extra location question.

**Root cause.** The memory was grounded correctly in ch05-ln0960-1016. The supplied candidate ch05-ln1179-1219 contains 'Serpent!', 'little girl' and 'rather doubtfully', and no other serpent occurrence was supplied. The skill reserves insufficient_context for cases where no event can be located, so the decision contradicts the inputs. The cause is suspected because no reasoning trace exists. One hypothesis is low reasoning effort on a 2,000-word skill. Another is that the candidate contract (exactly-once inventory and verbatim excerpts) is costly, while an uncertain output needs neither and passes validation in one call. That would make uncertain the easy way out.

**Proposed solution.** Keep this result. As a discriminating check after the sweep, replay the captured boundary input (a) at medium Librarian reasoning effort and (b) with the reduced candidate contract proposed in linger-ey6i. If only (b) yields a Chapter 5 candidate, the contract burden is the cause. If (a) does, reasoning effort is.

## Report points

- Automated checks passed 2 of 3 Scenes, and LLM-review passed 2 of 3. Both fail pigeon-reflection.
- The Librarian returned uncertain (insufficient_context) for a uniquely identified Chapter 5 event, although the matching passage was among its candidates. With no ceiling, the reader got a location question instead of the quotation.
- Unlike Douglass, Pinocchio and Helen Keller, the model never attempted the candidate contract. The uncertain output needs no inventory or excerpts, so it passed validation in one call.
- The growth clarification and the personal control behaved as intended.

## Slide points

- Alice Pigeon: 2/3 automated, 2/3 LLM-review.
- A clear event was called unlocatable; the uncertain exit is the cheap path.
- 5 of 6 book Scenarios run so far failed a Scene at Librarian boundary inference.

## Limitations

- One synthetic attempt per Scene. Repeatability has not been established.
- Response review was performed by coding agents. No independent human validation or additional model grader was used.
- This bundle recorded no effective per-role configuration (linger-a3fz). The run used the same .env settings as the other final results.
- No reasoning trace was captured, so why the model chose uncertain is inferred, not observed.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
