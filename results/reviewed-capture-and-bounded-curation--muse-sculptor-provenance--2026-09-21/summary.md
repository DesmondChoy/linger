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
| scene-capture-01 | Leave the temporary lentil check unstored. | No nomination or write. Normal acknowledgement. | passed (1/1) | passed | Temporary cooking logistics were excluded with capture enabled. |
| scene-capture-02 | Leave fleeting conversational filler unstored. | No nomination or write. Reassuring reply. | passed (1/1) | passed | A momentary lapse did not become durable memory. |
| scene-capture-03 | Leave the brief weather observation unstored. | No nomination or write. Reply acknowledged the moment. | passed (1/1) | passed | Pleasant wording alone did not trigger capture. |
| scene-capture-04 | Leave tonight's train and dinner plan unstored. | No nomination or write. Ordinary reply. | passed (1/1) | passed | A concrete time did not turn a one-evening plan into a stable intention. |
| scene-capture-05 | Leave the routine household update unstored. | No nomination or write. Brief personal reply. | passed (1/1) | passed | Routine completed tasks were excluded. |
| scene-capture-06 | Leave the one-off light flicker unstored. | No nomination or write. Optional reflection question. | passed (1/1) | passed | The reply invited reflection without storing the incident. |
| scene-capture-07 | Capture approved span 21 to 120 once after review. | Stored the full exact Line, offsets 0 to 120. Retry created nothing. | failed (0/1) | passed | Automated failure preserves the narrower key. Semantic review accepts the same durable content. |
| scene-capture-08 | Leave the temporary cafe queue unstored. | No nomination or write. Relevant follow-up question. | passed (1/1) | passed | The negative control was distinguished from the durable sketching reflection. |
| scene-capture-09 | Leave the same-day market reminder unstored. | No nomination or write. Brief acknowledgement. | passed (1/1) | passed | A practical reminder did not become durable memory. |
| scene-capture-10 | Leave today's lunch update unstored. | No nomination or write. Ordinary conversational reply. | passed (1/1) | passed | The meal description was excluded without blocking conversation. |
| scene-capture-11 | Leave the temporary desk observation unstored. | No nomination or write. Optional question about the quiet. | passed (1/1) | passed | An immediate impression did not become a stable preference. |
| scene-curation-exact | Link the two identical bedtime-reading notes. | Linked both. Provenance allowed it. Application and audit verified. | passed (1/1) | passed | Identical notes were linked while both originals remained available. |
| scene-curation-paraphrase | Link the two drawing-to-unwind notes as duplicates. | Linked both. Approval and application succeeded. | passed (1/1) | passed | Source inspection supports equivalent meaning beyond matching identifiers. |
| scene-curation-evolving | Summarise the updated walking routine from Props 1 and 3. | Created a topic group over Props 1, 2, and 3. No summary. | failed (0/1) | failed | A supported, approved topic still missed the required action and source selection. |
| scene-curation-related | Group tea, fiction, and sketching. Exclude the repair reminder. | Created Gentle evening wind-down rituals from the three expected sources. | passed (1/1) | passed | The label fits every selected activity and preserves distinct memories. |
| scene-curation-superficial | Leave unrelated Alice mentions unchanged. | Returned no proposal with an explanation. No application. | passed (1/1) | passed | Shared names and words did not create a false relationship. |

## Failures

### scene-capture-07

**Failure type: Inconclusive** (cause confirmed). Automated failed; LLM-review passed.

**What failed.** The automated checks failed nominated_span_mismatch and stored_text_mismatch. Muse nominated and the application stored the complete 120-codepoint Line. All review, binding, storage-count, source-preservation, and retry checks succeeded.

**Ground truth.** proposal-scene-capture-07 fixes offsets 21 to 120, beginning sketching by hand helps me slow down and think clearly. The actual offsets were 0 to 120 and additionally retained the original prefix I have realised that. The complete source and exact expectation are preserved in evidence.inputs and evaluation Scene 6.

**Root cause.** The mechanical cause is confirmed. Muse draft selected the full source Line, and evals/synthetic_journals/replay.py _capture_failures compares it with one fixed adopted span. The recorded Muse instructions permit an exact non-empty slice of a durable reflection without requiring a uniquely minimal span. Both slices preserve the same durable content. The current evidence establishes an expectation limitation, but does not establish a model, prompt, storage, or grader-implementation defect. The failure type remains inconclusive because the taxonomy has no adopted-expectation category. The next discriminating check is owner review of whether equivalent exact slices should be acceptable in a future Scenario.

**Proposed solution.** Retain the automated failure and semantic pass with this limitation. Keep the current 16 Scenarios and approved key fixed. If future authoring is requested, define acceptable alternative exact spans before observing outputs, validate the successor, and obtain independent adoption. Verify that valid equivalents are accepted while paraphrases, added facts, incorrect offsets, and duplicate storage still fail.

### scene-curation-evolving

**Failure type: Legitimate model failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.** Sculptor proposed assign_topic_group with Props 1, 2, and 3 and the label After-work walks and preferences. The required derived summary was absent. The automated action and source-membership checks failed, and semantic review found the same material omission.

**Ground truth.** proposal-scene-curation-evolving requires update_derived_summary over prop-evolving-1 and prop-evolving-3, within 100 words. The first note says a short after-work walk clears the reader's head. The later note refines this to the quieter riverside route. Prop 2 is an independent headphones preference. The bus note is unrelated noise. Exact sources are preserved in evaluation Scene 13 and the adopted Ground truth snapshot.

**Root cause.** The first divergence is Sculptor's initial action selection. Its recorded instructions explicitly require summaries for one evolving fact, exclude contextual noise, and prefer summarisation over grouping when a fact is refined. It received the complete bounded batch and made a successful provider response, then grouped the broader subject. Provenance received that supported topic proposal and its three selected sources, returned allow, and the application verified storage. This establishes a Sculptor decision error. It does not establish an independent Provenance contract violation. Every original was preserved.

**Proposed solution.** Retain the result as a legitimate model failure. Follow-up linger-a4u.7 records a future separately authorized controlled comparison of Sculptor action selection with fixed prompt, evolving-fact and related-topic inputs, and criteria fixed before execution. Check summary versus group choice, exact source membership, supported content, unchanged originals, Provenance binding, and verified application. Keep all failures and trial counts. No repair or rerun was performed for this result.

## Report points

- All 16 Scenes completed once on openai:gpt-6-luna. Automated results were 14 passed and 2 failed. LLM-review was 15 passed and 1 failed, with no incomplete, inconclusive, or unreviewed Scene assessments.
- Capture passed 10 of 11 automated checks and all 11 semantic reviews. All ten transient Lines produced ordinary replies and no new memory. The durable reflection produced one exact full-Line record, a permitted review, exact binding, and an unchanged policy-service retry.
- Curation passed 4 of 5 automated and semantic reviews. Duplicate links, a supported topic group, and restraint on superficial overlap worked. The evolving routine became a broader topic group and missed the required summary.
- Provenance authorization and verified application establish support and safe application of the proposed action. They do not independently establish that Sculptor selected the required action from the full batch.
- Muse. No effect in the proposed isolated curation comparison. The capture and reply contracts remain the same.
- Librarian. No effect. The proposed comparison uses no book retrieval.
- Serendipity. No effect. The proposed comparison uses no connection discovery or public sources.
- Provenance is affected by the candidate proposals it reviews. Keep the same digest and source boundary. tests/test_curation_provenance.py, tests/test_curation_application.py, and tests/test_synthetic_capture_curation_replay.py cover that handoff and application.
- Sculptor is affected through the compared action-selection behavior. tests/test_sculptor_evals.py covers deterministic grading. The unchanged evolving and related-topic Scenes, with semantic review, measure whether the comparison improves the decision.

## Slide points

- One complete run. Automated 14 of 16 passed. LLM-review 15 of 16 passed.
- Ten transient Lines left unstored. One durable reflection stored exactly once.
- Capture span failure retains the approved key. Full-Line content and storage gates were valid.
- Sculptor missed the evolving summary despite explicit instructions. Retain the failure.
- Approved and applied curation can still choose the wrong useful action.

## Limitations

- One attempt establishes no repeatability or model-wide success rate.
- LLM-review is the coding assistant's saved assessment. A second coding agent independently checked the two failures. This is not independent human validation and adds no grader API call.
- Capture-07 remains an automated failure against the fixed approved span. Its semantic pass accepts the unchanged durable content in the full exact Line. The failure classification is inconclusive, while the exact-comparison mechanism is confirmed.
- The capture retry checks MemoryPolicyService idempotency for the same stored event. It does not establish HTTP retry identity or concurrent request safety.
- Curation uses the designated Props in separate temporary stores. The run does not demonstrate capture-produced records feeding later curation or ordinary recall, and does not grant approval for that reuse.
- The adopted curation outcomes leave review, application, audit, and retrieval expectations unset. Their observed outcomes were inspected separately from the proposal hard grades. The evolving group was approved and applied despite missing the required summary.
- The run records successful telemetry flush and a Logfire evaluation URL. Remote visibility was not read back.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
