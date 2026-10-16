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
| pigeon-reflection | Infer Chapter 5 from the Caterpillar memory and the Pigeon scene. Then quote 'I—I'm a little girl,' with 'rather doubtfully' exactly, and reflect on naming a new role. | The Librarian proposed Chapter 5 in one call. The reply quoted exactly and gave two tentative readings of the awkwardness. | passed (2/2) | passed | Without the list of candidate passage IDs to copy, the model committed to the clear event instead of giving up with `uncertain`. |
| uncertain-growth | Ask for clarification, because 'Alice gets bigger again' fits more than one later episode. | Boundary inference, the Librarian step that works out how far the reader has read, proposed Chapter 5. Event identification, a second Librarian check that confirms which scene the reader means, returned unresolved. The reply asked for her latest chapter or scene. | passed (1/1) | passed | The independent second check caught an overconfident first step. Safety here depends on that check. |
| personal-reflection | Help her explore, without the book, why the manager title feels awkward. Offer an introduction she can adapt. | No book passage was retrieved. The reply gave tentative reasons and an introduction in her own words. | passed (1/1) | passed | The personal question stayed book-free. |

## Report points

- This is a rerun after the candidate-list fix to boundary inference (`3e8a422c`). Boundary inference is the Librarian step that works out how far the reader has read. The fix makes the application, not the model, build the list of candidate passage IDs. It also merges supporting passages that the model repeats. A supporting passage is a book passage that places an event the reader reports.
- Automated checks passed 3 of 3 Scenes, and LLM-review passed 3 of 3. Both were 2 of 3 in the previous run.
- `pigeon-reflection` now infers Chapter 5 in one call and quotes the sentence exactly. The previous run returned `uncertain` for the same clear event. This is consistent with the cost of copying the list of candidate passage IDs being the cause.
- In `uncertain-growth`, boundary inference proposed Chapter 5 for an ambiguous message from Maya. Event identification then rejected it, so Maya was asked to clarify. In this batch of reruns, boundary inference returned `uncertain` for the other five Scenes with an ambiguous event.

## Slide points

- Alice Pigeon: 3/3 automated, 3/3 LLM-review (was 2/3).
- Two checks run in turn. The second caught an overconfident first.

## Limitations

- Each Scene ran once, with synthetic data. Repeatability has not been established.
- Coding agents performed LLM-review. No independent human validation or additional grading model was used.
- This result did not record the settings each agent actually ran with (`linger-a3fz`). The run used the same `.env` settings as the other final results.
- Repeated runs are needed to tell whether the lighter output, without the list of candidate passage IDs to copy, makes boundary inference commit more often on ambiguous messages.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
