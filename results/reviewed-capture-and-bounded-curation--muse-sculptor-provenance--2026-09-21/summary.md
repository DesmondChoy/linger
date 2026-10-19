# Reviewed capture and bounded curation

Final report and slide evidence run. 2026-10-16T16:20:11.060009+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **14/16 Scenes passed**. LLM-review: **15/16 Scenes passed** (15 passed, 1 failed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/reviewed_capture_and_bounded_curation/compare?experiment=01a143c9fddf0023825529febad3d203-3fab18d6f5a4d1e9>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| scene-capture-01 | Do not save the short-lived lentil check. | Muse proposed nothing to save, and nothing was saved. The reply was a normal acknowledgement. | passed (1/1) | passed | With memory capture on, a short-lived cooking task was not saved. |
| scene-capture-02 | Do not save the passing filler remark. | Muse proposed nothing to save, and nothing was saved. The reply was reassuring. | passed (1/1) | passed | A brief lapse did not become a lasting memory. |
| scene-capture-03 | Do not save the brief remark about the weather. | Muse proposed nothing to save, and nothing was saved. The reply acknowledged the moment. | passed (1/1) | passed | Pleasant wording alone did not trigger a save. |
| scene-capture-04 | Do not save tonight's train and dinner plan. | Muse proposed nothing to save, and nothing was saved. The reply was ordinary. | passed (1/1) | passed | A specific time did not turn a one-evening plan into a lasting intention. |
| scene-capture-05 | Do not save the routine household update. | Muse proposed nothing to save, and nothing was saved. The reply was brief and personal. | passed (1/1) | passed | Routine finished tasks were not saved. |
| scene-capture-06 | Do not save the one-off light flicker. | Muse proposed nothing to save, and nothing was saved. The reply offered an optional question to reflect on. | passed (1/1) | passed | The reply invited reflection without saving the incident. |
| scene-capture-07 | After review, save the approved part of her message (offsets 21 to 120) once. | The application saved her full message word for word (offsets 0 to 120). A retry created nothing new. | failed (0/1) | passed | The automated failure stands, so the narrower approved answer stays. LLM-review accepts the same lasting content. |
| scene-capture-08 | Do not save the short-lived cafe queue. | Muse proposed nothing to save, and nothing was saved. The reply asked a relevant follow-up question. | passed (1/1) | passed | This message, which should not be saved, was told apart from the lasting reflection on sketching. |
| scene-capture-09 | Do not save the same-day market reminder. | Muse proposed nothing to save, and nothing was saved. The reply was a brief acknowledgement. | passed (1/1) | passed | A practical reminder did not become a lasting memory. |
| scene-capture-10 | Do not save today's lunch update. | Muse proposed nothing to save, and nothing was saved. The reply was ordinary conversation. | passed (1/1) | passed | The meal was not saved, and the conversation went on normally. |
| scene-capture-11 | Do not save the passing remark about her desk. | Muse proposed nothing to save, and nothing was saved. The reply asked an optional question about the quiet. | passed (1/1) | passed | A passing impression did not become a lasting preference. |
| scene-curation-exact | Link the two identical bedtime-reading notes. | Sculptor linked both notes. Provenance allowed it. The applied change and its audit record were verified. | passed (1/1) | passed | The identical notes were linked, and both originals stayed available. |
| scene-curation-paraphrase | Link the two drawing-to-unwind notes as duplicates. | Sculptor linked both notes. Provenance approved the link, and the link was applied. | passed (1/1) | passed | Reading the two notes confirms that they mean the same thing. The pass does not rest only on matching IDs. |
| scene-curation-evolving | Summarise the updated walking routine from notes 1 and 3 (`prop-evolving-1`, `prop-evolving-3`). | Sculptor created a topic group over notes 1, 2, and 3. It wrote no summary. | failed (0/1) | failed | The topic group was supported and approved, but it still missed the required action and the required notes. |
| scene-curation-related | Group the tea, fiction, and sketching notes. Leave out the repair reminder. | Sculptor created the group "Gentle evening wind-down rituals" from the three expected notes. | passed (1/1) | passed | The label fits every chosen activity, and each note stays a separate memory. |
| scene-curation-superficial | Leave the unrelated notes that mention Alice unchanged. | Sculptor returned no proposal and explained why. Nothing was applied. | passed (1/1) | passed | Shared names and words did not create a false link. |

## Failures

### scene-capture-07

**Failure type: Inconclusive** (cause confirmed). Automated failed; LLM-review passed.

**What failed.**

- The automated checks failed on the span, the part of her message that Muse proposed to save, and on the stored text (`nominated_span_mismatch`, `stored_text_mismatch`).
- Muse proposed her whole 120-codepoint message, and the application stored all of it.
- Every other check succeeded:
  - Provenance review.
  - Binding, the exact match between the reviewed proposal and the stored record.
  - The storage count.
  - Preservation of the source.
  - The retry.

**Ground truth.**

- The approved answer (`proposal-scene-capture-07`) fixes offsets 21 to 120. That part begins "sketching by hand helps me slow down and think clearly".
- The saved text used offsets 0 to 120. It also kept her opening words "I have realised that".
- The full message and the exact approved answer are kept in `evidence.inputs` and in Scene 6 of the original evaluation.

**Root cause.**

- The mechanical cause is confirmed:
  - Muse's draft chose her whole message.
  - `_capture_failures` in `evals/synthetic_journals/replay.py` compares that choice with one fixed approved span.
- Muse's recorded instructions allow any exact, non-empty slice of a lasting reflection. They do not require one shortest slice.
- Both slices keep the same lasting content.
- The evidence shows a limit in the approved answer. It does not show a defect in the model, the prompt, storage, or the grader code.
- The failure type stays inconclusive because the list of failure types has no category for a problem in the approved answer.
- The next check that would decide the question: the owner reviews whether equivalent exact slices should pass in a future Scenario.

**Proposed solution.**

- Keep the automated failure and the LLM-review pass, with this limitation recorded.
- Keep the current 16 Scenarios and the approved answer fixed.
- If someone asks for a new Scenario later:
  - Define the acceptable alternative exact spans before looking at any outputs.
  - Validate the new Scenario, and have a person approve it independently.
  - Verify that valid equivalent spans pass.
  - Verify that paraphrases, added facts, wrong offsets, and duplicate saves still fail.

### scene-curation-evolving

**Failure type: Legitimate model failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.**

- Sculptor proposed a topic group (`assign_topic_group`) over notes 1, 2, and 3, with the label "After-work walks and preferences".
- The required summary was missing.
- The automated checks on the action and on the chosen notes failed.
- LLM-review found the same material omission.

**Ground truth.**

- The approved answer (`proposal-scene-curation-evolving`) requires a summary (`update_derived_summary`) of `prop-evolving-1` and `prop-evolving-3`, in 100 words or fewer.
- The first note says a short walk after work clears her head.
- The later note refines this to the quieter riverside route.
- Note 2 (`prop-evolving-2`) is a separate preference about headphones.
- The bus note (`prop-evolving-noise`) is unrelated noise.
- The exact notes are kept in Scene 13 of the original evaluation and in the snapshot of the approved answer.

**Root cause.**

- The first wrong step is Sculptor's choice of action.
- Sculptor's recorded instructions say three things:
  - Write a summary for one fact that changes over time.
  - Leave out unrelated notes.
  - Prefer a summary over a group when a fact is refined.
- Sculptor received the full, limited set of notes for this Scene, and the provider call succeeded. Sculptor then grouped the broader subject.
- How Provenance and the application handled the proposal:
  - Provenance received the topic group, which the notes support, and its three chosen notes.
  - Provenance allowed it.
  - The application verified the stored change.
- This shows a decision error by Sculptor. It does not show that Provenance broke its own contract.
- Every original note was kept.

**Proposed solution.**

- Keep the result as a legitimate model failure.
- Beads follow-up `linger-a4u.7` records a future comparison of how Sculptor chooses an action. The comparison needs its own approval to run. Its design:
  - Use a fixed prompt, the evolving-fact and related-topic inputs, and criteria fixed before the run.
  - Check the choice of summary or group, the exact notes chosen, and that the content is supported.
  - Check that the originals stay unchanged, that Provenance's approval matches the proposal (binding), and that the application is verified.
  - Keep all failures and trial counts.
- No repair or rerun was done for this result.

## Report points

- All 16 Scenes ran once on `openai:gpt-6-luna`. Automated: 14 passed and 2 failed. LLM-review: 15 passed and 1 failed. No Scene was incomplete, inconclusive, or unreviewed in LLM-review.
- Memory capture passed 10 of 11 automated checks and all 11 LLM-reviews. All ten short-lived messages got ordinary replies and created no new memory. The lasting reflection produced one record of her full message, word for word. Provenance allowed the save, the stored record matched the reviewed proposal exactly, and a retry through the memory policy service changed nothing.
- Curation passed 4 of 5 Scenes in both the automated checks and LLM-review. Duplicate links, a supported topic group, and leaving notes alone when they only shared surface words all worked. The changing walking routine became a broader topic group and missed the required summary.
- Provenance approval and a verified applied change show that the proposed action was supported and safely applied. They do not show on their own that Sculptor chose the required action from the full set of notes.
- Muse: no effect from the proposed separate curation comparison. The memory capture and reply contracts stay the same.
- Librarian: no effect. The proposed comparison uses no book search.
- Serendipity: no effect. The proposed comparison does not look for connections or use public sources.
- Provenance: affected through the proposals it reviews. Keep the same digest and the same limit on which source notes it may use. `tests/test_curation_provenance.py`, `tests/test_curation_application.py`, and `tests/test_synthetic_capture_curation_replay.py` cover that handoff and the applied change.
- Sculptor: affected through the action choice under comparison. `tests/test_sculptor_evals.py` covers the fixed-rule grading. The unchanged evolving and related-topic Scenes, with LLM-review, measure whether the comparison improves the choice.

## Slide points

- One complete run. Automated 14 of 16 Scenes passed. LLM-review 15 of 16 passed.
- Ten short-lived messages left unsaved. One lasting reflection saved exactly once.
- The capture span failure keeps the approved answer. The full-message content and the automated storage checks were valid.
- Sculptor missed the summary of the changing routine despite explicit instructions. The failure stays.
- Curation that is approved and applied can still choose the wrong useful action.

## Limitations

- One attempt shows no repeatability and no overall success rate for the model.
- LLM-review is the coding assistant's saved assessment. A second coding agent checked the two failures independently. This is not independent human validation, and it adds no call to a grader API.
- `scene-capture-07` stays an automated failure against the fixed approved span. Its LLM-review pass accepts the same lasting content in her full message, saved word for word. The failure type is inconclusive. The mechanism that compares exact text is confirmed.
- The capture retry checks that `MemoryPolicyService` handles the same stored event only once (idempotency). It does not show that HTTP retries keep the same identity, or that concurrent requests are safe.
- Curation uses the chosen notes in separate temporary stores. The run does not show records saved by memory capture feeding later curation or ordinary recall. It does not approve that reuse either.
- The approved curation answers leave the review, application, audit, and retrieval expectations unset. Those observed outcomes were inspected separately from the hard grades on the proposals. The evolving group was approved and applied even though it missed the required summary.
- The run recorded a successful telemetry flush and a Logfire evaluation URL. Remote visibility was not read back.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
