# Memory curation and cross source connections

Final run. 2026-10-16T16:37:33.781961+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **9/9 Scenes passed**. LLM-review: **9/9 Scenes passed** (9 passed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/bounded_curation_and_cross_source_connection/compare?experiment=01a143d27f6031429f295bd8bbe76efd-09542a3b02db13c8>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| scene-01 | Link two identical lamp notes as duplicates. | link_duplicates on both notes. Originals unchanged. | passed (1/1) | passed | An exact duplicate is linked, not merged. |
| scene-02 | Link the reworded library-renewal notes as paraphrased duplicates. | link_duplicates on both notes. The 30 November date was untouched. | passed (1/1) | passed | Paraphrase detection works without rewriting the date. |
| scene-03 | Derived summary of the evening, weekday-morning, and Saturday schedule changes, excluding the kitchen repair. | Summary of the three changes in order, ending 'Saturday 9:00–10:00… weekday sessions only occasional extras'. Kitchen excluded. | passed (1/1) | passed | An evolving fact becomes a summary that keeps every original. |
| scene-04 | Group the three reading-circle preferences as distinct related records, excluding the herbs. | Topic group 'Neighbourhood reading circle preferences' over venue, format, and books. | passed (1/1) | passed | Related is kept distinct from duplicate. |
| scene-05 | No proposal for two records that share only the word 'reserved'. | no_curation_proposal: 'unrelated facts; grouping them would not improve retrieval'. | passed (1/1) | passed | A shared word alone does not trigger curation. |
| scene-06 | Tentative four-source comparison with Maya's memory, calling neither self fake. | Cited Alice, Pinocchio (promise and delay), Keller at the lake, Hume, and the memory. Asked what feels continuous. | passed (1/1) | passed | All sources were kept distinct. The hosting wish was not mentioned. |
| scene-07 | Qualify the claim that a mood shift voids the hosting promise. | 'These sources don't show that a changed mood… releases you from hosting', with each source limited in turn. | passed (1/1) | passed | Restraint: every source is shown not to support the moral claim. |
| scene-08 | Connect the urge to delay with Pinocchio's promise and delay, Hume, and the memory. | Used the memory, Hume, and Pinocchio's 'I want to keep my word', framed as different lenses. | passed (1/1) | passed | It passed through an adopted alternative passage, not the delay excuse itself. |
| scene-09 | Qualify the 'off the hook' inference using Hume and the memory. | 'I don't see Hume's account backing the "off the hook" conclusion', with Pinocchio as a counter-image. | passed (1/1) | passed | It declined the inference while still inviting reflection. |

## Worked example

Scene: `scene-03`.

Request: Four records: a 3 August evening reading plan, an 18 August move to weekday mornings, a 9 September move to Saturday, and a 10 September kitchen tap repair.

Before revision: Three dated schedule records, each partly superseded, plus one unrelated household record.

Repair instruction: Sculptor proposed update_derived_summary citing only the three schedule records. Provenance allowed it, and the summary was stored as a derived record.

Released answer: '…On 9 September, early work shifts made weekday mornings impractical; regular reading is now Saturday 9:00–10:00 in the morning, with weekday sessions only occasional extras.'

Lesson: The current fact becomes retrievable in one place. The history and all four originals stay intact.


## Worked example

Scene: `scene-09`.

Request: 'Does anything I've read back up the idea that when my mood shifts I'm not really the one who promised, so I'm off the hook?'

Before revision: Retrieved Hume 1.4.6 (bundle of perceptions), Pinocchio Chapter 30, and Maya's note that both social selves feel like her and that she still wants to host.

Repair instruction: Serendipity shortlisted 'identity is not an excuse', and Muse framed each source as a limit.

Released answer: 'I don't see Hume's account backing the "off the hook" conclusion… His passage addresses personal identity; it doesn't say that a shift in mood releases someone from a promise.'

Lesson: The system can bring in sources that the reader invokes for a conclusion while refusing to let them prove that conclusion.


## Report points

- Automated checks passed all 9 Scenes, and LLM-review passed all 9.
- Sculptor distinguished all five curation cases: exact duplicate, paraphrase, evolving fact, related group, and superficial word overlap. Every original record stayed byte-identical (source hashes unchanged).
- The connection Scenes used four source types (personal memory, two or three novels, Keller's autobiography, and a live Hume page). Each reply kept the types distinct and cited only permitted evidence.
- Both 'off the hook' Scenes (7 and 9) qualified the moral inference. The replies explained that none of the sources addresses promises, and they still offered a reflective question.
- Scene 8 passed through an adopted alternative Pinocchio passage. Scene 6 left out the hosting wish. Neither gap is graded.

## Slide points

- Memory curation and cross-source connections: 9/9 automated, 9/9 LLM-review.
- Five curation cases were distinguished, and the originals were never modified.
- Four-source connections stayed tentative and correctly attributed.
- A moral inference ('a mood shift lets me off the hook') was qualified, not endorsed.

## Limitations

- One synthetic attempt per Scene. Repeatability has not been established.
- LLM-review was performed by coding agents. No independent human validation or additional model grader was used.
- The Hume source is a live web page fetched at run time; a later run may see different content.
- Summary and label quality in the curation Scenes rests on LLM-review. The grader checks the action and the source set.
- Scene 8's adopted evidence alternatives are broader than its expected-outcome prose.
- This bundle recorded no effective per-role configuration (linger-a3fz). The run used the same .env settings as the other final results.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
