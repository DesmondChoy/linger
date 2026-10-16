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
| scene-exact-duplicate | Link the two identical kiln-notebook notes as duplicates. | Sculptor linked exactly those two notes. Both originals stayed unchanged. | passed (1/1) | passed | The full path works on the easiest case. Sculptor proposes, Provenance reviews, the change is applied, and the audit record is checked. |
| scene-paraphrased-duplicate | Link two spare-key notes, worded differently, as one fact. | Sculptor linked exactly the two reworded notes. Both originals stayed unchanged. | passed (1/1) | passed | Sculptor matched meaning, not wording. |
| scene-evolving-fact-with-noise | Summarise the open-house date change from three notes. Leave out the poster and tea notes. | Sculptor cited only the three date notes. The summary says the date moved from 14 to 21 September, 2:00–5:00 p.m., with no unrelated details. | passed (1/1) | passed | Sculptor kept related but irrelevant details out of the summary note. |
| scene-related-distinct-with-distractor | Group the ramp, large-print and quiet-room notes under accessibility. Leave out the bakery receipt. | Sculptor grouped exactly those three notes as 'Pottery open house accessibility and visitor accommodations'. | passed (1/1) | passed | A shared event name did not pull the bakery receipt, a note that should be left out, into the group. |
| scene-superficial-similarity | Propose no change for two notes that share the word 'rib': a pottery tool and a physiotherapy stretch. | Sculptor proposed no change. Its reason was that the shared word does not make the facts related. | passed (1/1) | passed | A shared word alone did not trigger curation. No automated check covers the reason. |

## Worked example

Scene: `scene-evolving-fact-with-noise`.

Request: Five open-house notes: the original date, the move, the confirmation, the poster-ink choice and the tea order.

Before revision: The original date was 14 September at 2:00–5:00 p.m. The event was moved to 21 September, and the community center confirmed 21 September at the same time.

Repair instruction: Sculptor proposed a summary note (`update_derived_summary`) that cites only the three date notes. Provenance allowed it.

Released answer: “…moved to Saturday, September 21; the community center confirmed the September 21 event, still from 2:00 to 5:00 p.m.”

Lesson: The summary note follows the date as it changed and leaves out unrelated notes about the same event. All five original notes stay intact, and search can still find them.


## Report points

- All five curation Scenes passed the automated checks and LLM-review in one run.
- Sculptor chose the expected action in each Scene: two duplicate links, one summary note, one topic group and one decision to change nothing.
- Some notes shared the event name but did not belong, such as the poster ink, the tea order and the bakery receipt. Sculptor left their IDs out of its proposals.
- Each original note's hash, a fingerprint of its content, was the same before and after every Scene. Curation added new notes built from the originals and never rewrote the originals.
- Provenance allowed all four proposals. The no-change Scene needed no Provenance review.
- This run used only Sculptor and Provenance. The `linger-mio6` fix concerns how Muse revises a reply after Provenance asks for a revision. It does not affect the curation steps this run tests.

## Slide points

- Pottery curation: 5/5 automated, 5/5 LLM-review.
- Sculptor chose the right action every time, including no change for two notes that only share a word.
- Original notes never change. Curation only adds links or new notes built from the originals.

## Limitations

- One attempt on synthetic data. Each of the five Scenes ran once. Repeatability has not been established.
- Coding agents did the LLM-review. No person checked it independently, and no extra grader model was used.
- No automated check covers the kind of reason Sculptor gives for proposing no change. Its correctness rests on LLM-review.
- The curation replay did not record the settings each agent actually ran with. This result therefore does not show Sculptor's reasoning effort for this run.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
