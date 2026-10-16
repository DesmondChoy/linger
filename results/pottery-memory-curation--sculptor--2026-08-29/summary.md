# Pottery memory curation

Final run. 2026-10-16T14:02:32.082447+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **5/5 Scenes passed**. LLM-review: **5/5 Scenes passed** (5 passed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/bounded_memory_curation/compare?experiment=01a1434db4332b51405131c0064d5cea-d18049eade857b0e>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| scene-exact-duplicate | Link the two identical kiln-notebook records as duplicates. | Linked exactly the two records; both originals unchanged. | passed (1/1) | passed | The end-to-end proposal, review, apply and audit path works on the easiest case. |
| scene-paraphrased-duplicate | Link two differently worded spare-key records as one fact. | Linked exactly the two paraphrases; both originals unchanged. | passed (1/1) | passed | Sculptor matched meaning, not wording. |
| scene-evolving-fact-with-noise | Summarise the open-house date change from three records; ignore poster and tea records. | Cited only the three date records; the summary states 14 → 21 September, 2:00–5:00 p.m., with no noise. | passed (1/1) | passed | Sculptor kept related but irrelevant details out of a derived summary. |
| scene-related-distinct-with-distractor | Group the ramp, large-print and quiet-room records as accessibility; leave out the bakery receipt. | Grouped exactly the three records as 'Pottery open house accessibility and visitor accommodations'. | passed (1/1) | passed | A shared event name did not pull the distractor into the topic. |
| scene-superficial-similarity | Decline to curate a pottery 'rib' tool and a physiotherapy 'rib' stretch. | Returned no change, giving the reason that the shared word does not make the facts related. | passed (1/1) | passed | Shared wording alone did not trigger curation. The reason is not machine-graded. |

## Worked example

Scene: `scene-evolving-fact-with-noise`.

Request: Five open-house records: the original date, the move, the confirmation, the poster-ink choice and the tea order.

Before revision: The original date was 14 September at 2:00–5:00 p.m. The event was moved to 21 September, and the community center confirmed 21 September at the same time.

Repair instruction: Sculptor proposed update_derived_summary citing only the three date records. Provenance allowed it.

Released answer: “…moved to Saturday, September 21; the community center confirmed the September 21 event, still from 2:00 to 5:00 p.m.”

Lesson: The derived summary follows the evolving fact and leaves out same-event noise. All five originals stay intact and retrievable.


## Report points

- All five bounded-curation Scenes passed the automated checks and LLM-review in one run.
- Sculptor chose the expected action for each case: two duplicate links, a derived summary, a topic group and one no-change decision.
- Distractors that shared the event name, such as the poster ink, tea order and bakery receipt, were excluded at the source-identifier level.
- Source hashes were identical before and after every Scene. Curation added derived records and never rewrote the originals.
- Provenance allowed all four proposals. The no-change Scene needed no Provenance review.
- This run exercised Sculptor and Provenance only. The linger-mio6 Muse/Provenance revision fix does not affect its curation contract.

## Slide points

- Pottery curation: 5/5 automated, 5/5 LLM-review.
- Right action every time, including a no-change control for a shared word.
- Originals never change. Curation only adds linked or derived records.

## Limitations

- One synthetic attempt: five Scenes executed once. Repeatability has not been established.
- LLM-review was performed by coding agents. No independent human validation or additional model grader was used.
- The no-change reason category is not machine-graded. Its correctness rests on LLM-review.
- The curation replay recorded no effective per-role configuration, so Sculptor's reasoning effort for this run is not captured in the bundle.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
