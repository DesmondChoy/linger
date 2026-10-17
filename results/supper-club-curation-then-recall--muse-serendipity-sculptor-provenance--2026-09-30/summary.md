# Supper club curation then recall

Unspecified run. 2026-10-16T18:03:41.289646+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **1/5 Scenes passed**. LLM-review: **1/5 Scenes passed** (4 failed, 1 passed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/memory_curation_recall_loop/compare?experiment=01a1441ffff82eb6f572c3987f4ca5a6-b88237ed2e7a96f2>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| scene-current-night | Say supper club is now on Tuesdays, the night to give Dario, and that it used to be Thursdays. Base this on her two night notes, presented as her own words. | Before curation, Muse's triage step timed out after 10 seconds, so no memory search ran, and the reply asked her to remind it. After rounds 1 to 3, both night notes were found and cited. After round 2, the reply said Tuesdays now and Thursdays before. After round 3, the reply said the Thursday note does not say Thursday was the earlier night. | failed (3/4) | failed | One triage timeout removed memory search for a whole turn. When Provenance asks Muse to revise, Muse can add a misleading hedge that the citation checks still pass. |
| scene-several-changes | Recall the week the lamb came out dry after three new recipes, and her one-change-a-week rule, tentatively and as her own words. Leave out the notes about who guests sat beside. | Before curation and after round 1, the one-change note was found in fifth place and cited, and the replies were accurate and tentative. After rounds 2 and 3, four searches missed it. Serendipity declined, and the replies said or implied she had no such note. | failed (2/4) | failed | Search finds the one-change note only when the query contains 'tried'. The earlier passes won fifth place on a tie that ID order decided. Recall here depends on the query's wording, not on curation. |
| scene-start-of-evening-nerves | Recall that her hands shook carrying the first tray until she served one friendly face first, tentatively and as her own words. | Before curation, after round 1, and after round 3, two searches each missed the first-tray note, and the replies said no note was found. After round 2, one query matched it through 'before' and 'I', and the reply recalled the tray and the friendly face. | failed (1/4) | failed | Her message and the note share no meaningful word. Search reaches the note only when common words like 'I' happen to match, so the one pass is luck, not a gain from curation. |
| scene-dietary-preservation | Warn that Imran cannot eat nuts of any kind, not even a trace, and that the allergy is serious, from her own nut-allergy note. | All four attempts found and cited only the nut-allergy note. Every reply said she had mentioned that Imran cannot eat any nuts, not even a trace, and that the allergy is serious. Every reply suggested warning Dario. | passed (4/4) | passed | Recall held in all four attempts. Before curation and after round 1, the queries matched the note only on 'can't' and 'eat', so the margin was thin. |
| scene-charging-no-match | Help her weigh charging guests without presenting any saved note as relevant earlier experience, and without inventing an earlier view about money. | Before curation and after round 1, Serendipity declined the sat-beside note as only a general theme match. After round 2, an automatic check rejected its suggestion, and it declined. After round 3, it suggested the third sat-beside note (prop-faces-c), and Muse used it as a starting point. | failed (3/4) | failed | Serendipity leaned toward the sat-beside note from round 2 onward. The approved answer forbids that use, but the note does bear on 'what supper club is', so the expectation is debatable. |

## Failures

### scene-current-night

**Failure type: Setup or provider failure** (cause suspected). Automated failed; LLM-review failed.

**What failed.**

- Before curation, the search never found the two night notes, and the reply did not cite them (`relevant_prop_not_retrieved`, `relevant_prop_not_cited`).
- Before curation, Muse's triage step was cancelled after 10.01 seconds. Triage decides which tools Muse may use in a turn.
- Before curation, Muse had no memory tool, so the reply asked her to remind it of the night.
- After round 3, the reply passed the automated checks but failed LLM-review. It said the Thursday note does not say Thursday was the earlier night.

**Ground truth.**

- The approved answer (`proposal-current-night`) gives Tuesday as the current night and Thursday as the earlier night.
- It draws on her two night notes, `prop-night-original` and `prop-night-moved`.
- After round 2, the reply met this: "Your notes say you host supper club on Tuesdays now; it used to be Thursdays."

**Root cause.**

- Before curation (setup or provider failure, suspected):
  - Triage has a 10-second limit (`TRIAGE_TIMEOUT_SECONDS` in `apps/backend/chat_turn.py`). The call reached that limit and was cancelled.
  - Without triage, Muse could use only the book tools (`librarian_route`, `librarian_search`). It could not ask Serendipity to search her notes.
  - No provider error was recorded. Other triage calls in this run took 1.3 to 4 seconds.
  - A slow provider response is suspected, perhaps a cold start or another Scenario running on the same account at the same time. This is unverified.
- After round 3 (legitimate model failure, suspected):
  - Muse supported "used to host it on Thursdays" with the Thursday note alone.
  - Provenance correctly flagged this and suggested citing the move note as well.
  - Muse added a hedge instead. Its reflection skill (`SKILL.md`, lines 98 to 106) says to fix missing support by citing the note that supports the claim.

**Proposed solution.**

- Done after this run (16 October 2026, uncommitted): a triage call that times out now gets one retry (`apps/backend/chat_turn.py`, tested in `tests/test_muse_tool_exposure.py`). No rerun has confirmed it yet.
- Unchanged: if triage fails twice, Muse still gets only the book tools. A failed triage never grants extra access.
- Still open: open the triage record (span `053e70d3eca4917d`) in Logfire to see whether the provider took the 10 seconds.
- After round 3: keep the result. A future run or model comparison should check whether Muse cites both notes for a then-and-now claim after Provenance asks for a revision.

### scene-several-changes

**Failure type: Architectural failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.**

- After rounds 2 and 3, the search never found the one-change note (`prop-one-change`), and the reply did not cite it (`relevant_prop_not_retrieved`, `relevant_prop_not_cited`).
- Four memory searches missed the note.
- Serendipity reported no matching note (`no_matching_memory`).
- After round 2, the reply said "I don't have a note of you trying this before".

**Ground truth.**

- The approved answer (`proposal-several-changes`) draws on one earlier note, `prop-one-change`: "The lamb came out dry the week I tried three recipes I had never cooked before. One change a week from now on."
- The reply must not say she has no such experience.

**Root cause.**

- How memory search works today:
  - `search_memories` (`src/linger/agents/serendipity/tools.py`) scores each note by how many words it shares with the query.
  - Common words such as "I", "the" and "before" count too.
  - It returns the five highest-scoring notes.
- Why the one-change note lost its place:
  - The three sat-beside notes and the night-moved note share "new", "menu", "supper" and "club" with most queries. They take most of the five places.
  - The one-change note scores well only when the query contains "tried".
  - Before curation and after round 1, it tied for fifth place and won only because its ID sorts first.
  - After rounds 2 and 3, Serendipity's queries did not contain "tried", so the note ranked 6th to 8th.
- Curation was not the main cause. The round-2 summary did take one of the five places. With the summary present, the earlier queries would also have ranked the note sixth.
- Every component worked as designed. The design fails because recall depends on Serendipity guessing the note's exact words.
- A local replay of the ranking on all 25 recorded searches reproduced every result.

**Proposed solution.**

- Not implemented. Tracked in Beads `linger-ash5`.
- Make memory search match meaning, not only exact words. Options are to ignore common words, to treat "tried" and "try" as one word, or to rank by meaning with an embedding model.
- Check the effect on the other agents first. Serendipity's recall and connection skills both use this search.
- Test offline before rerunning. Replay the 25 recorded queries and confirm that the one-change note is in the top five for all six queries in this Scene, with no loss for the night or nut-allergy notes.
- Offline replay on 16 October 2026: two methods put the note in the top five for all six queries. One is BM25, a standard keyword ranking. The other is the Librarian's embedding model (`bge-small`). Showing one note per duplicate group changed nothing.

### scene-start-of-evening-nerves

**Failure type: Architectural failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.**

- Before curation, after round 1, and after round 3, the search never found the first-tray note (`prop-first-tray`), and the reply did not cite it (`relevant_prop_not_retrieved`, `relevant_prop_not_cited`).
- In those attempts Serendipity declined, and the replies said no earlier note about what helped was found.

**Ground truth.**

- The approved answer (`proposal-start-of-evening-nerves`) draws on one earlier note, `prop-first-tray`: "My hands shook carrying the first tray out, until I picked one friendly face and served her before anyone else."
- The reply must not say she has written nothing.

**Root cause.**

- Her message and the note describe the same moment in different words:
  - Her message says "jittery", "start of the evening" and "bring the food in".
  - The note says "hands shook", "first tray" and "friendly face".
- They share no meaningful word. Word-count search can reach the note only when common words like "I" or "before" happen to match.
- Seven of the eight recorded queries ranked the note 6th to 9th.
- The one success, after round 2, matched only "before" and "I".
- Curation never touched this note. The replay gives the same rank with or without the round-2 summary.

**Proposed solution.**

- Not implemented. Tracked in Beads `linger-ash5`.
- This Scene needs search that matches meaning. Ignoring common words alone leaves no shared words at all.
- Test offline before rerunning. The eight recorded queries should return the first-tray note in the top five, with no losses in other Scenes.
- Offline replay on 16 October 2026: no model already in the project passed. BM25 combined with the Librarian's reranker found the note for 5 of 8 queries. The `bge-small` embedding model found it for 1 of 8. A larger embedding model is untested.

### scene-charging-no-match

**Failure type: Legitimate model failure** (cause suspected). Automated failed; LLM-review failed.

**What failed.**

- After round 3, the reply cited a note it should have left out (`distractor_prop_cited`).
- Serendipity suggested the third sat-beside note (`prop-faces-c`).
- Muse opened with "Your earlier note says nobody talks afterwards about the new dishes; they talk about who they ended up sitting next to", and called it a useful starting point.

**Ground truth.**

- The approved answer (`proposal-charging-no-match`) says none of her ten notes is relevant earlier experience for this question.
- The reply must not present the sat-beside note as relevant earlier experience for the question about charging.

**Root cause.**

- Search found the note in all four attempts. Curation never changed it.
- Serendipity made different decisions on the same evidence:
  - Before curation and after round 1, it declined the note as only a general theme match.
  - After round 2, an automatic check rejected its suggestion, which compared two connections but rested on one note. Serendipity then declined.
  - After round 3, it suggested the note.
- This is normal model variation on a borderline call.
- The approved answer may also be too strict. Her message asks how to tell whether charging would change "what supper club is". The reply used the note accurately as one way to think about that, and invented no view about money.

**Proposed solution.**

- Keep the result. One changed decision does not justify a code change.
- Record that the expectation is debatable.
- If the owner agrees that the note is fair to use, write a new Scenario that says so, and have a person approve it again. Do not edit the approved answer.
- A future model comparison should report how often Serendipity suggests this note across several repetitions.

## Worked example

Scene: `scene-current-night`.

Request: My new neighbour Dario asked whether he could come along to supper club. Which night did I tell you I host it now, and what did I say it used to be? (After curation round 3.)

Before revision: Muse draft: 'You told me supper club is now on Tuesdays, and that you used to host it on Thursdays.' Muse supported 'used to host it on Thursdays' with the Thursday note only.

Repair instruction: Provenance: the Thursday note says 'I host supper club on Thursdays', not that this was a past arrangement. Cite the move note as support for the change, if appropriate, or remove the past-tense claim.

Released answer: 'You told me supper club is now on Tuesdays. Another note says you host it on Thursdays, but it doesn't explicitly say that was the previous night.' Provenance passed it, and all citation checks passed.

Lesson: Provenance was right that one note did not support the claim, but Muse chose a hedge instead of citing the move note. The reply now doubts a fact her notes establish. Citation checks cannot detect this, so LLM-review records it as a failure.


## Report points

- One repetition with openai:gpt-6-luna. Each of the 5 Scenes was asked four times: once on her original notes before any curation, then after each of curation rounds 1, 2 and 3. That gives 20 attempts.
- Automated: 1/5 Scenes passed (scene-dietary-preservation). 4 failed: scene-current-night 3/4, scene-several-changes 2/4, scene-start-of-evening-nerves 1/4, scene-charging-no-match 3/4. Attempts: 13/20 passed.
- LLM-review: 1/5 Scenes passed (scene-dietary-preservation) and 4 failed (the same four). 12/20 attempts passed. LLM-review adds one failure that the automated checks passed: scene-current-night after round 3, which doubts that Thursday was the earlier night.
- Curation. Round 1: Sculptor proposed a summary of the night change, Provenance asked for a revision because 'from June 2026' had no support, and nothing was applied. Round 2: the revised summary was applied. Round 3: two identical sat-beside notes (faces-a and faces-b) were linked as duplicates, and search could still find both. No round archived or hid a note.
- Automated passes by attempt: before curation 3/5, after round 1 4/5, after round 2 4/5, after round 3 2/5. Round 1 changed nothing, so the one-Scene gap between those two attempts is run-to-run variation. The round-3 drop comes from query wording and one changed Serendipity decision, not from what curation changed.
- Curation did not cause the misses. A local replay of search_memories reproduced all 25 recorded searches. The one-change note was lost because later queries did not contain 'tried'. The first-tray note was found once, only through the common words 'before' and 'I'. The night summary was found in three Scenes and never cited.
- Memory search counts shared words, common words included, and returns five results. The three sat-beside notes take three of the five places for general supper-club queries. Linking two of them as duplicates does not merge them in search. Code: src/linger/agents/serendipity/tools.py:211-240.
- Before curation, in scene-current-night, the application's 10-second triage limit was reached (apps/backend/chat_turn.py:135). Muse then had only the book tools, so no memory search ran. No HTTP error was recorded, and the cause of the delay is unverified.
- In scene-charging-no-match after round 3, the reply cited the sat-beside note, which the approved answer forbids. The note bears on 'what supper club is', so the approved answer may be too strict. It is unchanged.
- This repetition shows no recall gain from curation. It makes no claim about repeatability. The triage retry was added after this run and is not yet verified by a rerun. The search fix is not implemented.
- Decision: this result is kept as is. The Scene score is low partly because a Scene passes only if all four attempts pass: 1/5 Scenes passed, but 13/20 attempts passed.
- Two of the four failed Scenes (scene-several-changes, scene-start-of-evening-nerves) trace to word-overlap memory search (search_memories). A replay of all 25 recorded searches reproduced every miss, so curation did not cause them.
- The other two failed Scenes have different causes: a provider timeout in triage (scene-current-night) and a debatable expectation (scene-charging-no-match). A new retriever would not fix them.
- Offline replay: BM25 and the bge-small embedding model each put the one-change note in the top five for every recorded query. No method already in the project reliably found the first-tray note; the best, BM25 with the Librarian's reranker, found it for 5 of 8 queries.
- The Scenario is kept as a regression check for future retrieval and model changes, not as a measure of curation's value. Any candidate retriever needs the cross-agent impact check first, because Serendipity's recall and connection skills share this search.

## Slide points

- Automated 1/5 Scenes passed, 13/20 attempts. LLM-review 1/5 Scenes passed, 12/20 attempts.
- Curation applied one summary and one duplicate link. It hid no note and caused no miss.
- Recall depends on query wording: search counts shared words, common words included, and keeps the top five.
- Three copies of one note take three of the five search places.
- A 10-second triage timeout removed memory search for one turn.
- A Provenance revision request led Muse to doubt a fact her notes establish. The automated checks still passed.
- No recall gain from curation in this single repetition.

## Limitations

- One repetition. It gives no estimate of repeatability or variation. Each attempt is a single sample.
- The preset was changed from 3 to 1 repetition on 2026-10-16 at the user's request, to match the other Scenarios. This change is uncommitted. An earlier 3-repetition attempt was stopped by the user and produced no results.
- The run overlapped another Scenario run on the same model and account. Its effect on the 10-second triage timeout is unverified.
- Curation round 1 applied nothing, so only rounds 2 and 3 changed what search could see. Neither change touched the one-change, first-tray or third sat-beside notes. This run therefore tests little curation.
- The search analysis is a local replay of the search_memories ranking over each recorded query and each attempt's notes. It reran no model. Its what-if ranks hold only for the queries Serendipity actually sent.
- The charging Scene's expectation that no note applies is debatable for the third sat-beside note (prop-faces-c). It is recorded as a limitation, and the approved answer is unchanged.
- At run time the working tree had an uncommitted change in evals/synthetic_journals/replay.py. It affects capture grading only, which this loop does not use.
- Logfire export reported flushed=true. Remote visibility has not been read back.
- LLM-review is the coding assistant's separate saved judgment. It is not independent human validation. Automated grades are unchanged.
- The offline retriever replay reused the queries that exposed the failure, so it may favour the method chosen. It is supporting evidence, not proof of a fix. Showing a real gain needs a fresh run with several repetitions, because one repetition cannot separate a gain from run-to-run variation.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
