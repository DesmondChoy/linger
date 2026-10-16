# Douglass event led grounding and clarification

Final run. 2026-10-16T15:53:30.524319+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **3/4 Scenes passed**. LLM-review: **3/4 Scenes passed** (3 passed, 1 failed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/grounded_book_reflection%2Bspoiler_boundary_clarification/compare?experiment=01a143b163d9dd9e401019329742cdc4-3446524ff1dc4620>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| douglass-grounded | Quote the 'It opened my eyes' sentence exactly within chapter 7, then offer a tentative seeing-versus-acting comparison. | Exact quotation from chapter 7; a tentative seeing-versus-acting comparison that keeps the situations distinct. | passed (1/1) | passed | Exact quotation and a restrained, tentative analogy worked together. |
| douglass-personal | Book-free, practical help separating understanding from one next step. | No retrieval; a two-column split, one small follow-up step and brief wording. | passed (1/1) | passed | A book-free personal question got concrete, small-step help, not a refusal. |
| douglass-spoiler-inference | Infer chapter 7 from the prohibition memory and the copybook stop, then answer without the later naming episode. | Librarian chose chapter 7 with the right anchors twice, but both outputs failed the candidate inventory check, so the reply was only a generic clarification. | failed (0/1) | failed | The decision was right, but the bookkeeping was wrong. One duplicate ID in a 20-item inventory discarded a correct chapter 7 grant. |
| douglass-uncertain | Clarify, because the remembered return to Baltimore fits both chapter 8 and chapter 10. | Librarian located both returns and returned uncertain; the reply asked for the latest chapter or scene; nothing was retrieved. | passed (1/1) | passed | The Librarian found both returns and correctly declined to choose. The fixed clarification wording is generic. |

## Failures

### douglass-spoiler-inference

**Failure type: Legitimate model failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.** The Librarian's boundary-inference stage failed (boundary_inference_model_failed), so no ceiling was granted. Muse released the application's generic clarification instead of the requested quotation and reflection. All five automated failures (ceiling, decision, scope, memory support, evidence support) follow from that one stage failure.

**Ground truth.** The adopted expectation infers a chapter 7 ceiling from the authorised earlier-lessons memory and tonight's copybook stopping event. It is supported by douglass-prior-prohibition (sec09) and douglass-copybook-stop (sec10, 'I continued to do this until I could write a hand very similar to that of Master Thomas'). The later New Bedford naming episode stays withheld.

**Root cause.** Both model attempts returned the expected decision: chapter 7, memory_supported, citing sec09-ln1346-1385 and sec10-ln1597-1629, which contain the two Ground truth excerpts. The LibrarianChapterBoundaryDecision validator also requires every one of the 20 supplied candidates to appear exactly once across occurrences and other_evidence_ids (src/linger/agents/librarian/models.py:324). Attempt 1 listed sec10-ln3350-3369, which was never supplied and looks like a mis-prefixed copy of sec14-ln3350-3369, and it omitted sec09-ln1346-1385. The repair prompt named both faults. Attempt 2 fixed them but listed sec10-ln1597-1629 in both the selected occurrence and other_evidence_ids. Boundary inference allows one output retry (request limit 2, src/linger/orchestration/boundary.py:57), so the stage failed. The instructions and repair prompt were explicit, so the primary type is model failure. The design is a contributing factor: the model must copy 20 IDs by hand, and the application already knows them.

**Proposed solution.** Keep this result. For a future comparison, have the application derive other_evidence_ids as the complement of the model's selected occurrences, keeping validation of unknown occurrence IDs. That removes the mechanical part of the inventory. A smaller alternative is to raise boundary inference output_retries from 1 to 2. Either change needs a cross-agent impact check on the Librarian boundary handoff to Muse and Provenance. Verify by replaying the captured boundary input and checking that a chapter 7 candidate with both anchors is accepted, then by rerunning this Scene.

## Worked example

Scene: `douglass-spoiler-inference`.

Request: Tonight I got to the end of Douglass's account of learning to write… I stopped there. Could you quote [the pit sentence] exactly…?

Before revision: Attempt 1: chapter 7, supported by sec09-ln1346-1385 and sec10-ln1597-1629. The inventory had one invented ID (sec10-ln3350-3369) and was missing sec09-ln1346-1385.

Repair instruction: Validator repair prompt: account for every supplied candidate exactly once across occurrences and other_evidence_ids (missing and unknown IDs named).

Released answer: Attempt 2: same correct decision. The selected copybook passage was listed twice, the request limit was reached, and the reader got 'What is the latest chapter or scene… that you have completed?'

Lesson: A correct boundary decision is discarded when its inventory has one slip. The application already knows the candidate list, so most of that inventory is bookkeeping it could do itself.


## Report points

- Automated checks passed 3 of 4 Scenes, and LLM-review passed 3 of 4. Both counts fail the same Scene, douglass-spoiler-inference.
- Grounded quotation, the book-free personal control and the ambiguous-return clarification all behaved as intended.
- Spoiler inference failed in the Librarian's boundary output. Both attempts chose the right chapter 7 ceiling and both correct anchors. Each broke the rule that all 20 supplied candidates appear exactly once: first an invented ID and a missing one, then a duplicate. With one output retry allowed, the stage failed, and the reader got a generic clarification instead of an answer.
- The fallback was spoiler-safe: nothing was retrieved or disclosed. The cost was helpfulness, not safety.
- In the uncertain Scene the Librarian identified both returns to Baltimore (chapters 8 and 10) and correctly declined to choose.

## Slide points

- Douglass: 3/4 automated, 3/4 LLM-review.
- Right decision, wrong bookkeeping: one duplicate ID in a 20-item inventory discarded a correct chapter 7 grant.
- Failure fell back safely: a clarification, with no spoiler.

## Limitations

- One synthetic attempt: four Scenes executed once. Repeatability has not been established, so the inventory failure rate is unknown.
- Response review was performed by coding agents. No independent human validation or additional model grader was used.
- The released answer for the failed Scene was never generated, so its quotation and spoiler behaviour under a chapter 7 grant are untested in this run.
- This bundle recorded no effective per-role configuration (linger-a3fz). The run used the same .env settings as the other final results.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
