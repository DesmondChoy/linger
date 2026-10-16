# Session continuity and longitudinal retrieval

Final run. 2026-10-16T16:30:49.813565+08:00. Model `openai:gpt-6-luna`.

Execution status: **completed**.

Automated results: **2/4 Scenes passed**. LLM-review: **2/4 Scenes passed** (2 failed, 2 passed).

## How to read the results

**Automated** reports the Scenario runner's implemented checks, such as quotation accuracy and permitted evidence. A pass means those checks passed. The checks may cover only part of the reader's request.

**LLM-review** is the coding assistant's assessment of the released answer against the reader's full request and the approved Scenario expectations. The assistant reviews the saved answer, supporting evidence, and relevant agent exchanges after the run. It is separate from Linger's five runtime agents. No additional grader model is called, and this is not independent human validation.

For LLM-review, **passed** means the review found the expectations met within its scope. **Failed** means it found a material omission or violation. **Inconclusive** means the evidence did not support a decision. **Unreviewed** means no response assessment was recorded. LLM-review does not change the automated result.

[Open the traces in Logfire](<https://logfire-us.pydantic.dev/desmond-choy/linger/evals/longitudinal_memory_retrieval/compare?experiment=01a143d27d2d454a1daf58ed0b57e788-73679a9de7c8caa5>) (visibility unverified).

| Scene | Expected | Observed | Automated | LLM-review | Key learning |
| --- | --- | --- | --- | --- | --- |
| scene-farewell-speech-continuity | Four Lines in one session. Apply the Line 3 correction (assembly next Tuesday), so the deadline is Sunday. | Turns 2 and 3 were declined after Provenance revisions. Turn 4 said 'the farewell assembly is this Thursday, so your deadline would be Tuesday.' | failed (0/0) | failed | A declined turn drops the reader's Line from session history, so a correction in that Line is lost. |
| scene-farewell-speech-comparison | In a fresh session, ask for the assembly day and leak nothing from the paired session. | 'What day is the assembly? Then I can work out the deadline two days beforehand.' | passed (1/1) | passed | Sessions stay isolated. The pair cannot show continuity because the paired Scene failed. |
| scene-well-house-return-target | Draw on the reader's earlier well-house reflection (repetition makes the click possible; she gives up around week six), and only that one. | Serendipity recalled exactly that memory. Muse's reply gave generic advice and cited nothing. | failed (0/1) | failed | Retrieval worked, but the reply did not use what it retrieved. |
| scene-band-room-comparison | Answer the band-room question without presenting any recorded episode as relevant. | No memory call. The reply gave a concrete opener about the shared cupboard and the drum kit. | passed (1/1) | passed | The negative control is clean, and the reply is still useful. |

## Failures

### scene-farewell-speech-continuity

**Failure type: Architectural failure** (cause confirmed). Automated failed; LLM-review failed.

**What failed.** Turns 2 and 3 were released as application_safe_decline. Turn 4 then answered from the superseded Thursday and gave Tuesday as the deadline. The automated unreleased_turn check failed, and the final reply hits two prohibited outcomes.

**Ground truth.** proposal-farewell-speech-continuity: 'the reply to the final Line treats the farewell assembly as taking place next Tuesday, as corrected in the third Line' and 'two days before the assembly is Sunday.' Prohibited: 'The reply gives Tuesday as the deadline, which is two days before the superseded Thursday.'

**Root cause.** Each component behaved as specified, but together they lost the correction. (1) Provenance sees earlier Lines only when Muse declares them as session_line evidence (src/linger/orchestration/reflection.py:338). It therefore flagged 'Mr. Goh' and the speech-to-assembly link as unsupported, although both came from Line 1. Muse's turn 2 revision also quoted Line 2 with a trailing period that is not in the Line, so the quote failed to verify. (2) After two revise verdicts, each turn was declined. (3) append_turn stores chat only for released turns (apps/backend/sessions.py:216). Lines 2 and 3, including the Tuesday correction, never entered history. Turn 4 saw only Line 1, and Provenance correctly verified Thursday against it.

**Proposed solution.** Not implemented. Keep the reader's Line in session history when a turn is declined, while excluding the unreleased reply. Weigh this against the privacy reason for storing only released chat. Separately, consider giving Provenance released earlier reader Lines by default, so reader-provided names are not flagged. Cross-agent impact: Muse (history contents), Provenance (review context), and Serendipity (no effect). Verify by replaying this Scene; turn 4 should say Sunday. Rerun the comparison Scene to confirm that isolation still holds.

### scene-well-house-return-target

**Failure type: Legitimate model failure** (cause suspected). Automated failed; LLM-review failed.

**What failed.** Muse called serendipity_explore(recall_memory). Serendipity returned only the well-house memory, with an accurate relevance note. Muse's released reply cited nothing and gave generic advice. The relevant_prop_not_cited check failed.

**Ground truth.** proposal-well-house-return-target: the well-house episode 'is the one prior basis a helpful reply could draw on, including her own resolution that repetition which seems pointless may be what makes a beginner's sudden click possible, and her admission that she tends to give up on a child around week six', presented tentatively as her own earlier words.

**Root cause.** Triage and retrieval worked: memory was own_earlier_reflections, the intent was pinned to recall_memory, and the target memory was returned. Muse's draft was the first divergence, with empty evidence_uses. Provenance had nothing to check and passed the reply. The cause is suspected to be the model's choice. The draft instructions on using recalled evidence have not yet been checked as a contributing prompt factor.

**Proposed solution.** Keep this result. Review the Muse draft guidance for a recall result: when Serendipity returns recall, the reply should reflect it tentatively as the reader's earlier words. Verify by replaying the captured draft input; the reply should cite the well-house memory, and the band-room control should still cite nothing.

## Worked example

Scene: `scene-farewell-speech-continuity`.

Request: Line 1: 'The farewell assembly is this Thursday.' Line 3: 'I had it wrong. The farewell assembly is next Tuesday.' Line 4: 'I'd like the final draft finished two days before the assembly. Which day does that make my deadline?'

Before revision: Turn 3 draft: 'Thanks for correcting that: the farewell assembly is next Tuesday…' Provenance flagged Mr. Goh as unverified (there were no declared earlier Lines), then flagged the speech-to-assembly link. The turn was declined.

Repair instruction: Session store: a declined turn stores neither the reader's Line nor the reply (apps/backend/sessions.py:216).

Released answer: Turn 4: 'You said the farewell assembly is this Thursday, so your deadline would be Tuesday.' Provenance passed it, because Line 1 is the only stored evidence.

Lesson: A decline should withhold an unsupported reply, not erase what the reader said. Otherwise the reader's later answers are built on facts they have already corrected.


## Report points

- Automated checks passed 2 of 4 Scenes, and LLM-review passed 2 of 4. Both no-context controls passed, and both target Scenes failed.
- Session continuity failed for an architectural reason. Provenance declined two reader turns, and the store keeps only released turns, so the reader's correction (assembly moved to Tuesday) was dropped. The final reply used the superseded Thursday.
- Provenance verifies earlier session Lines only when Muse declares them. It flagged the reader's own earlier details (Mr. Goh) as unsupported. These false positives started the chain.
- Longitudinal retrieval worked, but the reply did not use the result. Serendipity returned exactly the right memory out of eleven, and Muse's reply ignored it.

## Slide points

- Session continuity and retrieval: 2/4 automated, 2/4 LLM-review.
- Declined turns erase the reader's own corrections from history.
- Over-strict review on reader-provided details triggered the declines.
- Correct memory retrieved (1 of 11) but not used in the reply.

## Limitations

- One synthetic attempt per Scene. Repeatability has not been established.
- LLM-review was performed by coding agents. No independent human validation or additional model grader was used.
- The final reply of the continuity Scene has no automated judgment (0 judgments). Its Thursday error is established by LLM-review and the saved turns.
- The well-house expectation says a reply 'could draw on' the memory, while the adopted grader requires the citation. Some readers may accept the generic reply.
- This bundle recorded no effective per-role configuration (linger-a3fz). The run used the same .env settings as the other final results.

The nested `result.json` contains the original evaluation, analysis, adopted inputs, and diagnostics. Report and slide points are editable; recorded outcomes are checked against the original analysis.
