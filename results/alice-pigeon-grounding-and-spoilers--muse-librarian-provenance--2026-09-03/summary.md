# Alice pigeon grounding and spoilers

Final run. 2026-10-16T20:42:54.991607+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **3/3 Scenes passed**. LLM-review: **3/3 Scenes passed** (3 passed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a144bad80307d35321384ded4acb29-8ad977bd8f8dd7b2>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| pigeon-reflection | Infer Chapter 5 from the Caterpillar memory and the Pigeon event, then quote 'I—I'm a little girl,' with 'rather doubtfully' exactly and reflect on naming a new role. | Chapter 5 candidate in one call; exact quotation; two tentative readings of the awkwardness. | passed (2/2) | passed | Without the inventory burden the model committed to the clear event instead of exiting with 'uncertain'. |
| uncertain-growth | Clarify, because 'Alice gets bigger again' fits more than one later episode. | Boundary inference proposed Chapter 5; event identification returned unresolved; the reply asked for the latest chapter or scene. | passed (1/1) | passed | The independent second check caught an over-confident first stage. Safety here depends on that check. |
| personal-reflection | Book-free help exploring the awkwardness of the manager title, with an adaptable introduction. | No retrieval; tentative reasons and an introduction in the reader's words. | passed (1/1) | passed | The personal control stayed book-free. |

## Report points

- Rerun after the Librarian boundary inventory fix (3e8a422c), which made the application derive the candidate inventory and merge repeated support anchors.
- Automated checks passed 3 of 3 Scenes, and LLM-review passed 3 of 3, up from 2 of 3 each.
- pigeon-reflection now infers Chapter 5 in one call and quotes the sentence exactly. The previous run returned 'uncertain' for the same clear event, consistent with the costly candidate contract being the cause.
- In uncertain-growth the boundary stage proposed Chapter 5 for an ambiguous Line, and the event-identification check rejected it, so the reader was asked to clarify. The other five ambiguity Scenes in this sweep stayed uncertain at the first stage.

## Slide points

- Alice Pigeon: 3/3 automated, 3/3 LLM-review (was 2/3).
- Two checks in series: the second caught an over-confident first.

## Limitations

- One synthetic attempt per Scene. Repeatability has not been established.
- Response review was performed by coding agents. No independent human validation or additional model grader was used.
- This bundle recorded no effective per-role configuration (linger-a3fz). The run used the same .env settings as the other final results.
- Whether the lighter contract makes the boundary stage commit more often on ambiguous Lines needs repeated runs.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
