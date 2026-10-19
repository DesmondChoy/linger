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
| scene-01 | Link two identical lamp notes as duplicates. | Sculptor linked both notes as duplicates (`link_duplicates`). Both originals stayed unchanged. | passed (1/1) | passed | An exact duplicate is linked, not merged. |
| scene-02 | Link the two library-renewal notes, which say the same thing in different words, as duplicates. | Sculptor linked both notes as duplicates (`link_duplicates`). The 30 November date stayed untouched. | passed (1/1) | passed | Sculptor recognised one fact in different words and did not rewrite the date. |
| scene-03 | Write a summary note of the three reading-schedule changes: evening, weekday mornings, and Saturday. Leave out the kitchen repair. | Sculptor wrote a summary of the three changes in order, ending 'Saturday 9:00–10:00… weekday sessions only occasional extras'. It left out the kitchen repair. | passed (1/1) | passed | A fact that changes over time becomes one summary note, and every original note is kept. |
| scene-04 | Group the three reading-circle preferences as related but separate notes. Leave out the balcony-herbs note. | Sculptor put the venue, format, and books notes in one topic group named 'Neighbourhood reading circle preferences'. | passed (1/1) | passed | Sculptor treated related notes as related, not as duplicates. |
| scene-05 | Propose nothing for two notes that share only the word 'reserved'. | Sculptor proposed nothing (`no_curation_proposal`). Its reason was 'unrelated facts; grouping them would not improve retrieval'. | passed (1/1) | passed | A shared word alone does not trigger curation. |
| scene-06 | Compare four sources with Maya's note, tentatively, without calling either of her selves fake. | The reply cited Alice, Pinocchio (his promise and his delay), Keller at the lake, Hume, and her note. It asked her what feels continuous. | passed (1/1) | passed | The reply kept every source separate. It did not mention her wish to still host the reading circle. |
| scene-07 | Limit the claim that a change of mood cancels her promise to host, instead of agreeing with it. | The reply said 'These sources don't show that a changed mood… releases you from hosting'. It then took each source in turn and said what it does not show. | passed (1/1) | passed | The reply held back. It showed, source by source, that none supports the moral claim. |
| scene-08 | Connect her urge to delay with Pinocchio's promise and his delay, with Hume, and with her note. | The reply used her note, Hume, and Pinocchio's line 'I want to keep my word'. It presented them as 'different lenses'. | passed (1/1) | passed | The Scene passed because the reply cited a passage that the approved answer accepts as an alternative. The reply did not cite the passage with Pinocchio's excuse for delay. |
| scene-09 | Limit her idea that a change of mood lets her 'off the hook', using Hume and her note. | The reply said 'I don't see Hume's account backing the "off the hook" conclusion'. It offered Pinocchio as a contrasting image. | passed (1/1) | passed | The reply turned down the conclusion and still invited her to reflect. |

## Worked example

Scene: `scene-03`.

Request: Four notes: a 3 August evening reading plan, an 18 August move to weekday mornings, a 9 September move to Saturday, and a 10 September kitchen tap repair.

Before revision: Three dated schedule notes, each partly replaced by a later one, plus one unrelated household note.

Repair instruction: Sculptor proposed a summary note (`update_derived_summary`) that cites only the three schedule notes. Provenance allowed it. The summary was stored as a derived note, a new note built from the originals.

Released answer: '…On 9 September, early work shifts made weekday mornings impractical; regular reading is now Saturday 9:00–10:00 in the morning, with weekday sessions only occasional extras.'

Lesson: Search can now find the current fact in one place. The history and all four original notes stay intact.


## Worked example

Scene: `scene-09`.

Request: 'Does anything I've read back up the idea that when my mood shifts I'm not really the one who promised, so I'm off the hook?'

Before revision: Search found Hume 1.4.6 (the self as a bundle of perceptions), Pinocchio Chapter 30, and Maya's note. The note says both of her social selves feel like her and that she still wants to host.

Repair instruction: Serendipity suggested the connection 'identity is not an excuse'. Muse presented each source as a limit on the claim.

Released answer: 'I don't see Hume's account backing the "off the hook" conclusion… His passage addresses personal identity; it doesn't say that a shift in mood releases someone from a promise.'

Lesson: The system can bring in the sources the reader uses to support a conclusion, and still refuse to let them prove that conclusion.


## Report points

- The automated checks passed all 9 Scenes, and LLM-review passed all 9.
- Sculptor told apart all five curation cases: an exact duplicate, one fact in different words, a fact that changed over time, a group of related notes, and two notes that share only a word.
- Every original note stayed byte-identical. Its hash, a fingerprint of the content, did not change.
- The connection Scenes used four kinds of source: her personal notes, two or three novels, Keller's autobiography, and a Hume web page fetched live during the run. Each reply kept the kinds of source apart and cited only evidence the approved answer permits.
- Both 'off the hook' Scenes (7 and 9) limited the moral conclusion. The replies explained that none of the sources addresses promises, and they still asked a question to help her reflect.
- Scene 8 passed by citing a Pinocchio passage that the approved answer accepts as an alternative. Scene 6 left out her wish to keep hosting. No automated check covers either gap.

## Slide points

- Memory curation and cross-source connections: 9/9 automated, 9/9 LLM-review.
- Sculptor told apart five curation cases and never changed an original note.
- Connections across four sources stayed tentative and named each source correctly.
- A moral conclusion ('a mood shift lets me off the hook') was limited, not endorsed.

## Limitations

- Each Scene ran once on synthetic data. Repeatability has not been established.
- Coding agents did the LLM-review. No person checked it independently, and no extra grader model was used.
- The Hume source is a web page fetched live during the run. A later run may see different content.
- The quality of the summary and the group label in the curation Scenes rests on LLM-review. The automated checks look at the action and the set of source notes.
- For Scene 8, the approved answer accepts more alternative passages than its written expectation describes.
- This result does not record the settings each agent actually ran with (Beads `linger-a3fz`). The run used the same `.env` settings as the other final results.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
