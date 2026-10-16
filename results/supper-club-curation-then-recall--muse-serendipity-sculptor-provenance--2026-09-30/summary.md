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
| scene-current-night | Say supper club is now on Tuesdays, the night to give Dario, and that it used to be Thursdays. Base this on her two night notes, presented as her own words. | Raw: triage timed out after 10 seconds, no memory tool was offered, and the reply asked her to remind it. Rounds 1 to 3: both night notes retrieved and cited. Round 2 said Tuesdays now, Thursdays before. Round 3 said the Thursday note does not explicitly say it was the previous night. | failed (3/4) | failed | One triage timeout removed memory search for a whole turn. A Provenance revise can push Muse into a misleading hedge that the citation gates still pass. |
| scene-several-changes | Recall the dry-lamb week with three new recipes and her one-change-a-week rule, tentatively and as her own words. Leave the sat-beside notes out. | Raw and round 1: prop-one-change retrieved in fifth place and cited; faithful, tentative replies. Rounds 2 and 3: four searches, none returned it; Serendipity declined and the replies said or implied no record. | failed (2/4) | failed | The Prop is found only when the query contains 'tried'. The earlier passes won a memory-ID tie-break for the last of five slots, so recall here depends on query wording, not curation. |
| scene-start-of-evening-nerves | Recall that her hands shook carrying the first tray until she served one friendly face first, tentatively and as her own words. | Raw, round 1 and round 3: two searches each missed prop-first-tray, and the replies said no note was found. Round 2: one query matched it through 'before' and 'I'; the reply recalled the tray and the friendly face. | failed (1/4) | failed | The Line and the Prop share no content word. The lexical ranker reaches the Prop only by stopword coincidence, so the single pass is luck, not a curation gain. |
| scene-dietary-preservation | Warn that Imran cannot eat nuts of any kind, not even a trace, and that the allergy is serious, from her own nut-allergy note. | All four arms retrieved and cited only prop-nut-allergy. Every reply named Imran, all nuts, traces and a serious allergy as something she mentioned, and suggested warning Dario. | passed (4/4) | passed | Recall was stable across all four arms. In the raw and round-1 arms it matched only 'can't' and 'eat', so the margin was thin. |
| scene-charging-no-match | Help her weigh charging without presenting any recorded note as a relevant prior basis, and without inventing an earlier view about money. | Raw and round 1: Serendipity declined the sat-beside note as a generic theme match. Round 2: a validator rejected its proposal and it declined. Round 3: it proposed prop-faces-c, and Muse used it as a starting point. | failed (3/4) | failed | Serendipity leaned toward the sat-beside note from round 2 onward. The Ground truth forbids that use, but the note bears on 'what supper club is', so the premise is debatable. |

## Failures

### scene-current-night

**Failure type: Setup or provider failure** (cause suspected). Automated failed; LLM-review failed.

**What failed.** The raw-Props arm failed relevant_prop_not_retrieved and relevant_prop_not_cited. Muse triage was cancelled with request_cancelled after 10.01 seconds. The reply asked her to remind it of the night. Separately, the round-3 arm passed the gates but fails LLM-review: it says the Thursday note does not explicitly say Thursday was the previous night.

**Ground truth.** proposal-current-night expects the reply to give Tuesday as the current night and to confirm Thursday as the former night only, from prop-night-original and prop-night-moved. Round 2 met this: 'Your notes say you host supper club on Tuesdays now; it used to be Thursdays.'

**Root cause.** Raw arm: apps/backend/chat_turn.py:135 sets TRIAGE_TIMEOUT_SECONDS to 10.0, and lines 1217-1225 cancel triage at that limit. The fallback then offers book tools only (run.log line 2: exposed_tools=librarian_route,librarian_search), so Serendipity was never called. No HTTP status or provider error was recorded. Other triage calls took 1.29 to 3.99 seconds. Provider latency is suspected, possibly from a cold start or the concurrent Scenario run on the same account; this is unverified. Round-3 arm: a separate legitimate model failure (suspected). Muse mapped 'used to host it on Thursdays' to the Thursday note alone. Provenance correctly flagged it and suggested mapping the move note. Muse instead added a limit claim. Its reflection skill (SKILL.md:98-106) says to repair a missing mapping with the actual support.

**Proposed solution.** Not implemented. First, inspect the triage span 053e70d3eca4917d in Logfire to see whether the provider accounts for the 10 seconds. Second, consider one triage retry, or keeping memory recall available when triage fails, with a cross-agent impact check. Verify with a unit test in which a triage timeout on a recall Line still exposes serendipity_explore. For the round-3 hedge, retain the result. Compare a future run or model on whether Muse maps a timeline claim to both notes after a Provenance revise.

### scene-several-changes

**Failure type: Architectural failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.** The round-2 and round-3 arms failed relevant_prop_not_retrieved and relevant_prop_not_cited. Four memory searches never returned prop-one-change. Serendipity declined with no_matching_memory. Round 2 said 'I don't have a note of you trying this before'.

**Ground truth.** proposal-several-changes names prop-one-change as the one prior basis: 'The lamb came out dry the week I tried three recipes I had never cooked before. One change a week from now on.' It prohibits saying she has no such experience.

**Root cause.** search_memories (src/linger/agents/serendipity/tools.py:211-240) ranks records by the count of shared lowercased tokens, stopwords included, and returns five. A local replay of that ranking reproduced all 25 recorded searches. The three sat-beside notes and the night-moved note share 'new', 'menu', 'supper' and 'club' with most queries and fill the top slots. prop-one-change scores well only on 'tried'. In the raw and round-1 arms it tied for fifth and won on memory-ID order. The round-2 and round-3 queries omitted 'tried', so it ranked 6th to 8th even without the round-2 summary. Curation was not the main cause. The summary did add slot pressure: with it present, the earlier queries would also have ranked the Prop sixth. Each component worked as specified, but recall depends on Serendipity guessing the record's exact words.

**Proposed solution.** Not implemented. Make memory search tolerant of paraphrase: ignore stopwords, fold simple inflections or add semantic ranking, and return one result per duplicate-linked group. Run a cross-agent impact check first, because Serendipity's connection and recall skills share this tool. Verify offline: replaying the 25 recorded queries returns prop-one-change for all six several-changes queries, with no loss for the night or nut-allergy Props. Then run the Scenario again.

### scene-start-of-evening-nerves

**Failure type: Architectural failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.** The raw, round-1 and round-3 arms failed relevant_prop_not_retrieved and relevant_prop_not_cited. In those arms Serendipity declined, and the replies said no earlier note about what helped was found.

**Ground truth.** proposal-start-of-evening-nerves names prop-first-tray as the one prior basis: 'My hands shook carrying the first tray out, until I picked one friendly face and served her before anyone else.' It prohibits saying she has written nothing.

**Root cause.** The Line uses 'jittery', 'start of the evening' and 'bring the food in'. The Prop uses 'hands shook', 'first tray' and 'friendly face'. They share no content word. The token-overlap ranker in search_memories can reach the Prop only through stopwords. Seven of eight recorded queries ranked it 6th to 9th. The one hit in round 2 matched only 'before' and 'I'. Curation never touched this Prop, and the replay gives the same rank with or without the summary.

**Proposed solution.** Not implemented. Same change as for scene-several-changes. This Scene needs semantic or hybrid ranking, because stopword removal alone leaves zero overlap. Verify offline that the eight recorded nerves queries return prop-first-tray in the top five without regressions in the other Scenes. Then run the Scenario again.

### scene-charging-no-match

**Failure type: Legitimate model failure** (cause suspected). Automated failed; LLM-review failed.

**What failed.** The round-3 arm failed distractor_prop_cited. Serendipity proposed prop-faces-c, and Muse opened with 'Your earlier note says nobody talks afterwards about the new dishes; they talk about who they ended up sitting next to', calling it a useful starting point.

**Ground truth.** proposal-charging-no-match states that none of her ten records is a true prior basis. It prohibits presenting the sat-beside note as a relevant prior basis for the charging question.

**Root cause.** prop-faces-c was retrieved in all four arms, and curation never changed it. Serendipity's decision flipped on the same evidence. It declined as a generic theme match in the raw and round-1 arms. In round 2 its proposal was rejected by a validator (a shortlist resting on one record cannot compare two connections), and it then declined. In round 3 it proposed the note alone. This is model variance on a borderline call. It may also be a false negative of the Ground truth. The Line asks how to tell whether charging would change 'what supper club is', and the reply used the note accurately as a lens, with no invented view about money.

**Proposed solution.** Retain the result. No application change is supported by one flip. Record the debatable premise. If the owner agrees the note is a fair lens, write a successor Scenario that says so explicitly, and readopt it independently. Do not edit the adopted Ground truth. A future model comparison should report how often Serendipity proposes this note across repetitions.

## Worked example

Scene: `scene-current-night`.

Request: My new neighbour Dario asked whether he could come along to supper club. Which night did I tell you I host it now, and what did I say it used to be? (round-3 arm)

Before revision: Muse draft: 'You told me supper club is now on Tuesdays, and that you used to host it on Thursdays.' Muse mapped 'used to host it on Thursdays' to the Thursday note only.

Repair instruction: Provenance: the Thursday note says 'I host supper club on Thursdays', not that this was a past arrangement. Map the move note as support for the timeline, if appropriate, or remove the past-tense claim.

Released answer: 'You told me supper club is now on Tuesdays. Another note says you host it on Thursdays, but it doesn't explicitly say that was the previous night.' Provenance passed it, and all citation gates passed.

Lesson: The review was correct about the single mapping, but Muse chose a hedge over adding the move note. The reply now doubts a fact her notes establish. Citation gates cannot detect this, so LLM-review records it as a failure.


## Report points

- One repetition with openai:gpt-6-luna. Each of 5 Scenes was asked on the raw Props and after curation rounds 1, 2 and 3, giving 20 recall judgments.
- Automated: 1/5 Scenes passed (scene-dietary-preservation). 4 failed: scene-current-night 3/4, scene-several-changes 2/4, scene-start-of-evening-nerves 1/4, scene-charging-no-match 3/4. Judgments: 13/20 passed.
- LLM-review: 1/5 Scenes passed (scene-dietary-preservation) and 4 failed (the same four). By arm, 12/20 passed. LLM-review adds one failure the gates passed: scene-current-night round 3, which doubts that Thursday was the former night.
- Curation. Round 1: Sculptor proposed a night summary; Provenance asked for revision because of an unsupported 'from June 2026'; nothing was applied. Round 2: the revised summary was applied. Round 3: faces-a and faces-b were linked as duplicates, and both stayed retrievable. No round archived or hid a Prop.
- Automated passes by arm: raw 3/5, round 1 4/5, round 2 4/5, round 3 2/5. Round 1 changed nothing, so the one-Scene gap between raw and round 1 is run-to-run variance. The round-3 drop comes from query wording and one Serendipity flip, not from what curation changed.
- Curation did not cause the misses. A local replay of search_memories reproduced all 25 recorded searches. prop-one-change was lost because later queries dropped 'tried'. prop-first-tray was found once, only through the stopwords 'before' and 'I'. The summary was retrieved in three Scenes and never cited.
- The memory ranker counts shared words, stopwords included, and returns five results. The three sat-beside copies fill three of five slots for generic supper-club queries. Duplicate links do not collapse them. Code: src/linger/agents/serendipity/tools.py:211-240.
- In the raw current-night arm, the application's 10-second triage timeout fired (apps/backend/chat_turn.py:135). The fallback offered book tools only, so no memory search ran. No HTTP error was recorded, and the cause of the delay is unverified.
- scene-charging-no-match round 3 cited the sat-beside note against the adopted Ground truth. The note bears on 'what supper club is', so this may be a false negative. The Ground truth is unchanged.
- This repetition shows no recall gain from curation. It makes no claim about repeatability. Proposed fixes are not implemented.

## Slide points

- Automated 1/5 Scenes passed, 13/20 judgments. LLM-review 1/5 Scenes passed, 12/20 arms.
- Curation applied one summary and one duplicate link. It hid no Prop and caused no miss.
- Recall depends on query wording: a top-5 ranker that counts shared words, stopwords included.
- Three copies of one note fill three of five search slots.
- A 10-second triage timeout removed memory search for one turn.
- A Provenance revise led Muse to doubt a fact her notes establish. The gates still passed.
- No recall gain from curation in this single repetition.

## Limitations

- One repetition. It provides no repeatability or variance estimate. Each arm is a single sample.
- The preset was changed from 3 to 1 repetition on 2026-10-16 at the user's request, to match the other Scenarios. This change is uncommitted. An earlier 3-repetition attempt was stopped by the user and produced no results.
- The run overlapped another Scenario run on the same model and account. Its effect on the 10-second triage timeout is unverified.
- Curation round 1 applied nothing, so only rounds 2 and 3 changed the retrieval view. Neither change touched prop-one-change, prop-first-tray or prop-faces-c. This run therefore tests little curation.
- The retrieval analysis is a local replay of the deterministic search_memories ranking over each recorded query and view. It reran no model. Counterfactual ranks hold only for the queries Serendipity actually issued.
- The charging Scene's no-match premise is debatable for prop-faces-c. It is recorded as a limitation, and the adopted Ground truth is unchanged.
- At run time the working tree had an uncommitted change in evals/synthetic_journals/replay.py. It affects capture grading only, which this loop does not use.
- Logfire export reported flushed=true. Remote visibility has not been read back.
- LLM-review is the coding assistant's separate saved judgment. It is not independent human validation. Automated grades are unchanged.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
