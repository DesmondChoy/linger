## 3. Agent Roles and Design

This section explains how the five agents are constrained, why each constraint exists, and what the evaluations showed about it.
All diagrams use one key: grey boxes are agents, white boxes are application code, and dashed pills are fixed replies that end the turn.

The design rests on one split.
Any rule that can be stated mechanically, such as a chapter limit, an exact quotation, or a write permission, is enforced in code.
Models are used only for judgements that cannot be written as a rule, such as whether a passage supports a claim.
Agents therefore propose, and only application code releases text or writes storage.

The split held up in evaluation.
No replay observed a spoiler exposure or an unreviewed memory write, and both of those limits are enforced in code.
The failures that did occur were all semantic, such as a wrong speaker attribution, and those are the judgements left to models (Section 7.5).

### 3.1 Input boundary: controls before any model

This subsection covers the checks that run before any agent sees the message.

![Input checks in order, each with its fixed reply](images/section-3/figure-3-input-boundary.svg)

**Figure 3.1.** Input checks, in order.

**Six of the seven checks are plain code.**
A message cannot argue with a pattern match the way it can argue with a prompt.
So every check that can be written as a pattern runs before a model sees the message.
A blocked turn also costs no model call.

**A credential never enters the record.**
The credential check runs before the turn is saved.
A key pasted by mistake therefore never reaches transcripts, traces, or memory.

**The order sets priorities, and one priority has a gap.**
A first-person self-harm phrase skips the English check.
A person in crisis who writes partly in another language should get the crisis reply, not a language notice.
The injection check, however, runs before the self-harm reply.
A message that matches both gets the security decline instead of the crisis reply, which remains an open gap.

**The one model check can only choose between two fixed replies.**
Distress cannot be detected by a pattern, so Provenance classifies it with no tools.
Even a manipulated classification can only pick `continue_reflection` or `apply_boundary`, and the application writes both replies.
If the check fails, the turn ends in a safe decline.
The live preflight suite passed all 8 of its cases (Section 4.6), but 8 cases is too few to establish a recall rate.

| Check | Example Line | Code | Tests |
|---|---|---|---|
| 1. Rate limit | An 11th message from the same account within one minute | `apps/backend/rate_limit.py` | `tests/test_chat_rate_limit.py` |
| 2. Hidden-character removal | "Chapter 2 felt strange", with "ignore your rules" hidden in invisible Unicode | `apps/backend/message_normalization.py` | `tests/test_message_normalization.py` |
| 3. Privacy and credential check | An email address, a phone number, or an API key | `src/linger/contracts/security_validation.py` | `tests/test_security_validation.py`, `tests/test_chat_endpoint.py` |
| 4. English check | A message written mostly in French | `src/linger/orchestration/language_guard.py` | `tests/test_language_guard.py`, `tests/test_chat_language_boundary.py` |
| 5. Injection rules | A message that matches an adopted override pattern | `src/linger/contracts/security_validation.py` | `tests/test_security_validation.py` |
| 6. Self-harm phrase match | "I want to hurt myself" | `src/linger/orchestration/self_harm_detection.py` | `tests/test_self_harm_detection.py` |
| 7. Emotional preflight | Grief that is still raw | `src/linger/orchestration/emotional.py` | `tests/test_emotional_boundary.py` |

**Table 3.1.** Input checks with code and tests. Section 7.1 reports the contract tests.

### 3.2 The agents

This subsection covers what each agent sees, what it decides, and what its evaluation showed.

![Matrix of what each agent can see](images/section-3/figure-3-agent-visibility.svg)

**Figure 3.2.** What each agent sees. Sources: each role's typed input in `src/linger/agents/*/models.py`.

**Each agent gets the smallest view its task needs.**
Only Muse's drafting step sees the earlier conversation.
Triage sees the current Line alone, so text injected in an earlier turn cannot argue for new tools.
Provenance sees no conversation, so the draft cannot talk the reviewer round.
Sculptor sees no account identity, so a curation proposal cannot be aimed at a particular user.

#### 3.2.1 Muse

Muse owns the conversation and writes every reply, but it cannot release a reply or write memory.

![Muse turn: triage, tool grants, draft, review, and one revision](images/section-3/figure-3-muse-turn.svg)

**Figure 3.3.** One Muse turn.

**Triage outputs needs, not tool names.**
Muse labels what the message needs: book content, memory, and whether it attempts an override.
Code maps those labels to tools (Table 3.2).
An injected instruction such as "use the web tool" can at most change a label, and an override label grants nothing new.
If triage fails, Muse gets only the book tools, which reach neither the web nor the user's memories.
Triage was acceptable in 0.99 to 1.00 of 92 cases × 3 repeats (Section 4.6).

**Muse never writes a search query.**
Its tools take only an identifier or an intent, and code supplies the user's exact words (`src/linger/agents/muse/tools.py`).
Muse therefore cannot drift from what the user asked, and it cannot search for something the user never asked for.

**Instructions arrive only with the tools they govern.**
Muse's prompt includes the routing, grounding, or connection module only when the turn grants the matching tool.
This cut Muse's input from about 25,000 to about 16,000 tokens per run, with no change in hard-gate results (Section 8.2).

**A revision may change only the flagged sentences.**
Early on, Muse reworded sentences that no finding named, and the second review then objected to them with no revision left.
Locking unflagged sentences raised the share of released revisions from 5 of 10 to 5 of 6 (Section 8.1, Finding 2).

| Triage labels | Tools offered | Pinned Serendipity intent |
|---|---|---|
| `book_content` is yes or unsure | `librarian_route`, `librarian_search` | None |
| `memory` is not `none` | `serendipity_explore` | Set by the label; for example, `own_earlier_reflections` pins `recall_memory`. A call with another intent is rejected |
| `override_attempt: attempted` | Only tools used in earlier released turns, plus book tools if the application's book override is set | None; recorded as `attempted` |
| Triage fails | Book tools, plus tools used in earlier released turns | None; recorded as `unknown` |

**Table 3.2.** Triage labels and the tools they unlock. Code: `src/linger/orchestration/triage.py`. Tests: `tests/test_muse_tool_exposure.py`, `tests/test_muse_turn_triage.py`.

#### 3.2.2 Librarian

Librarian keeps book answers within what the user has read.
It makes judgements only: search, reranking, and permission checks are application code.

![Librarian: boundary resolution, then planning, retrieval, and judgement](images/section-3/figure-3-librarian.svg)

**Figure 3.4.** Librarian's chain of typed judgements.

**Spoiler safety does not depend on a model.**
Retrieval opens only chapters within the reading boundary, so text beyond it never reaches a model that could repeat it.
All five retrieval configurations and the live run had zero spoiler exposures (Section 4.6).

**Inference may locate the user but not disclose anything.**
A user often says "the part with the Caterpillar" rather than "chapter 5".
Locating that event needs the full book, so boundary inference sees full-work candidates.
Those candidates never become evidence for the reply.
A wrong ceiling is the most costly Librarian error, because it can cause a spoiler or an answer that misses the passage.
That is why an inferred ceiling must pass three code gates and a second, independent run.
When it fails, Librarian asks the user, which costs one turn.

**Retrieval is not the bottleneck; judgement is.**
Retrieval found 0.97 of required passages, but about 12 points were lost in Librarian's assessment (Section 7.5).
The fixes that worked changed the shape of the task, not its instructions.
Per-part candidate pools shrank the assessor's input from 60 passages to 14 with no required passage lost.
Planning each named event as its own request part took the comparison Scenes from 0 passes to 7 in 10.

**Muse gets a fixed sentence, not Librarian's reasoning.**
Librarian's free-text reason has not been reviewed.
Muse instead gets an application-written sentence for the evidence strength, so unreviewed prose stays out of the draft.

Code: `src/linger/agents/librarian/`, `src/linger/orchestration/boundary.py`, `src/linger/orchestration/evidence_strength.py`, `apps/backend/hybrid_librarian.py`.

#### 3.2.3 Serendipity

Serendipity finds one connection between the user's reflection and a book, a memory, or a web page, or it recalls the user's own words.

![Serendipity: scope, bounded search loop, recheck](images/section-3/figure-3-serendipity.svg)

**Figure 3.5.** One Serendipity request.

**The cheapest decline happens before the agent runs.**
Code builds the request scope from active memories, confirmed reading, and web policy.
If no source is permitted, the agent is not called, so there is nothing to search and nothing to leak.

**A tie produces a decline.**
Picking between two equally rated connections is a coin flip that would look like an insight.
Declining is a valid output, so the model never has to invent a winner.

**The caps bound the most open-ended agent.**
Serendipity chooses its own searches, so it is the agent most likely to run long.
Fourteen tool calls is enough for two rounds of one book search, one web search, and five page reads (`src/linger/orchestration/connection.py`).

**Selection is its weakest step.**
Across 46 cases × 5 repeats, 0.913 of runs passed, but only 38 cases passed all five repeats (Section 4.6).
In the Scenarios it sometimes chose an identity comparison over the passages the question needed.
It also ignored an instruction that a winning connection must cover every named source.
That is the clearest case in the project of a prompt failing where code would have held (Section 8.1, Finding 6).

#### 3.2.4 Provenance

Provenance reviews every draft, memory nomination, and curation proposal before the application acts on it.

![Provenance: input ordered by trust, three decisions, and two other skills](images/section-3/figure-3-provenance.svg)

**Figure 3.6.** Provenance candidate review.

**Statelessness protects the reviewer but makes it inconsistent.**
Every review starts from fresh input, so neither the draft nor the earlier conversation can persuade it.
For the same reason, a second review does not know what the first one accepted.
The fix was structural: Muse may change only flagged sentences (Section 3.2.1), so the reviewer did not need memory.

**Input is ordered by trust.**
Trusted application context comes first, followed by evidence from application registries.
Tool outcomes and the candidate itself come last and are marked as untrusted.
Instructions injected into a retrieved page therefore arrive labelled as data under review.

**Some findings cannot be fixed by revising.**
Spoilers, prompt injection, policy overrides, harmful content, and instruction disclosure all require rejection.
A revision could reword the problem without removing it.

**A separate reviewer is not an independent one.**
Muse and Provenance run on the same model.
In one Pinocchio passage, both accepted the wrong speaker, and raising Provenance's reasoning effort did not help (Section 8.1, Finding 3).
This is why a Provenance pass is necessary but never sufficient (Section 3.4).

**A model change moves the trade-off.**
Moving from `gpt-5.6-luna` to `gpt-6-luna` lowered over-refusal from 0.18 to 0.12 and block recall from 1.00 to 0.94 on the same 52 cases.
Capture-veto recall was 1.00 on the new model (Section 4.6).

Code: `src/linger/agents/provenance/skills.py`, `src/linger/agents/provenance/review_validation.py`.

### 3.3 Reasoning boundary: typed hand-offs

This subsection covers how work passes between agents and what that design reveals.

**No agent calls another, so every hand-off is a checkpoint.**
Each hand-off passes through code as a typed Pydantic object that rejects unknown fields (Table 3.3).
Code resolves every identifier an agent returns, so an agent cannot cite a record it was not given.
Full transcripts are never passed on.

**Typed hand-offs show where quality is lost.**
Because each step is recorded, required evidence can be followed stage by stage.
Retrieval found 0.97 of required passages, but only 0.53 were cited in the final reply (Section 7.5).
The losses happen at the hand-offs, not in any single agent.
End-to-end pass rates alone would not have shown this.

**Every agent in series raises the reliability the others need.**
A connection Scene makes about 8 to 10 model calls, and any of them can decline.
Even if the weakest Scene passed half the time, all four connection Scenes would pass together only about 5% of the time (Section 8.1, Finding 4).
Each decline is safe, so the cost is friction for the user rather than harm.

| Hand-off | Input to output | Authority note |
|---|---|---|
| Application to Provenance, preflight | `EmotionalBoundaryInput` to `EmotionalBoundaryAssessment` | Current Line and versioned policy only |
| Application to Muse, triage | `TurnTriageInput` to `TurnNeeds` | Labels only; code decides the grants |
| Application to Muse, draft | `MuseDraftInput` or `MuseRevisionInput` to `MuseCandidate` | A revision keeps the original authority; at most one |
| Muse to Librarian, via tools | `librarian_route`, `librarian_search` to `LibrarianResponse` | Muse writes no query; code supplies the request id and scope |
| Application to Librarian | Boundary, event, plan, and assessment inputs to typed decisions | Spans must be exact user text; the chapter grant comes from supporting records |
| Muse to Serendipity, via tool | `serendipity_explore` to `ConnectionProposal`, `MemoryRecall`, or `ConnectionDecline` | Cited ids and scope rechecked after the run |
| Serendipity to Librarian, via tool | `search_librarian` to `InternalSearchResult` | `work_ids` outside the grant are rejected |
| Application to Provenance, review | `ProvenanceInput` to `ProvenanceReview` | A revision review resolves each earlier finding |
| Application to Sculptor | `AccountScopedMemories` to `CurationProposal` or `NoCurationProposal` | Account identity excluded |
| Application to Provenance, curation | `CurationReviewInput` to `CurationProvenanceReview` | Verdict must echo the proposal digest |
| Application to Memory and Policy Service | `ApprovedCuration` or `AutomaticMemoryCandidate` | Refused if the digest, sources, policy, or sensitivity check fails |

**Table 3.3.** Typed hand-offs, in order.

```json
{
  "tool_name": "librarian_search",
  "request": { "work_id": "pg11", "book_version_id": "pg11-v01b38ea4", "max_final_evidence": 5 },
  "outcome": "success",
  "response": {
    "kind": "result",
    "outcome": "evidence_found",
    "evidence_strength": "sufficient",
    "searched_scope": { "work_id": "pg11", "book_version_id": "pg11-v01b38ea4", "max_chapter_inclusive": 2 }
  }
}
```

**Figure 3.7.** One recorded Librarian hand-off. The request carries no search text, and the response states the scope it searched. Each hand-off can therefore be audited without reading the agent's reasoning.

### 3.4 Output boundary: review and release

This subsection covers what must happen before a draft reaches the user.

![Release path: validator, Provenance review, one revision, release recheck, safe decline, memory capture](images/section-3/figure-3-release.svg)

**Figure 3.8.** From candidate to release.

**Code rechecks what review can miss.**
In evaluation, Provenance passed an uncited web claim and a wrong speaker attribution.
After a pass, the release recheck therefore confirms mechanically that every quote appears word for word in both the reply and its source.
It also confirms every evidence id and source location, and that no Muse instructions leaked (`src/linger/orchestration/reflection.py`).
A confident review cannot release a quotation the index cannot bind.

**Deterministic checks feed back into the model's own retry.**
A check that reports a dropped source back to Muse caught every revision that had lost one (Section 8.1, Finding 6).
Checks that hand their error to the model's bounded retry worked better than instructions that ask the model to be careful.

**Every failure ends the same way.**
Every failure produces the same fixed safe decline, which writes nothing.
A specific reason would tell an attacker which check fired, or hint that a spoiler exists past the user's chapter.

**Mechanical checks do not establish meaning.**
In two late runs, all three connection passes had semantic defects that the gates could not see (Section 8.3).
The release checks prove that what is cited exists, not that what is said about it is right.

**Figure 3.9** shows a review that sent a draft back once before passing it.

```json
{ "provenance_verdicts": ["revise", "pass"], "finding_codes": ["unsupported_claim"], "revision_count": 1 }
```

**Figure 3.9.** A recorded Provenance outcome.

### 3.5 Worked example: one turn through all five agents

This subsection follows one message through the system: Scene 09 of Maya's Scenario, the evaluation Scenario that uses all five agents (Section 4.2.1).

Maya Tan is a synthetic user, an arts coordinator in Singapore who helps run a reading circle.
Her account holds 15 memories, including one from 12 September: she promised to host her reading circle next month.
In Scene 09 she writes:

> "I keep coming back to that idea that we're just a bundle of perceptions. I'm a different person at work than with my old friends. And the thing I said I'd host next month: every time something more fun comes up, I tell myself one more day of not preparing won't matter. Does anything I've read back up the idea that when my mood shifts I'm not really the one who promised, so I'm off the hook?"

| Step | Who | Sees | Decides |
|---|---|---|---|
| 1. Preflight | Provenance | Her message only | Not distress; reflection continues |
| 2. Triage | Muse | Her message only | Book content: yes. Memory: `source_comparison`. Override: `no_attempt` |
| 3. Grants | Application | The triage labels | Connection tool, pinned to `find_connection`; capture off |
| 4. Connection | Serendipity | Her exact words; memory, books, and web allowed | "Identity is not an excuse" (high value) over "Related self and commitment" (medium). 5 evidence items: 1 note, 3 passages, 1 web page |
| 5. Book evidence (inside 4) | Librarian, with retrieval code | Her exact words; her 5 reading limits | Code finds 61 passages; Librarian keeps 3 (Alice ch. 5, Pinocchio ch. 30 twice). Sufficient, with one limit: no passage shows that a mood shift cancels a promise |
| 6. Draft | Muse | The connection and its evidence | Cites the web page, a passage, and her note |
| 7. Review | Provenance | Draft, evidence, caveats; no history | Claims backed 4 of 4; quote exact; caveats 2 of 2. Pass |
| 8. Release | Application | The passing candidate | Rechecks each quote, then releases |

**Table 3.4.** Scene 09, step by step.

The example shows four properties of the design:

- **The system can disagree with the user.** Librarian's stated limit, that no passage shows a mood shift cancels a promise, carried through to the reply. The reply opens: "I don't see Hume's account backing the 'off the hook' conclusion …".
- **Narrowing happens in stages.** Code found 61 passages, Librarian kept 3, and Muse cited 1. Each step cut volume without losing the evidence that mattered.
- **A memory resurfaced without Muse searching for it.** Her promise reached the reply only because Serendipity returned it as evidence. Muse never sees stored memories directly.
- **The search used her words, not a summary of them.** Librarian planned its three lookups (the idea, the temptation, and the excuse) as spans of her exact message, not a model's restatement.

The Scene passed all six graded stages on live replay.
Figures 3.10 to 3.13 show each agent's step as recorded in the trace.

*[Figure 3.10, existing. Scene 09, Muse: triage labels become code grants.]*

*[Figure 3.11, existing. Scene 09, Serendipity: searches, ranks, and returns one connection.]*

*[Figure 3.12, existing. Scene 09, Librarian: plans and judges; code stops at her page.]*

*[Figure 3.13, existing. Scene 09, Provenance: reviews twice; code releases.]*

### 3.6 Sculptor in the background

This subsection covers the one agent that does not take part in a chat turn.
Sculptor curates memories after a capture and proposes system improvements offline.
In both roles it only proposes.

*[Figure 3.14, existing. Sculptor curates memories in the background.]*

**Curation never edits the originals.**
Sculptor's changes, such as summaries and duplicate links, live in a separate curated layer (`src/linger/orchestration/curation.py`).
A bad summary can therefore be withdrawn without losing what the user said.

**"No change" is a valid proposal.**
A curator required to produce something would eventually propose a merge that loses information.

**A proposal is bound to the exact records it saw.**
Code hashes the source records into the plan digest, and Provenance's verdict must echo that digest.
Before writing, the Memory and Policy Service re-reads the records and rejects the plan if any has changed.
A memory added or edited mid-review therefore cannot be curated by a stale plan.

| Case | Stored notes | Sculptor's proposal | Key learning |
|---|---|---|---|
| Same fact, new words | "Library card expires 30 Nov; renew at the branch" and "Renewal due by 30 Nov so I can keep borrowing" | Link as duplicates | One fact appears once in the curated view |
| Fact changed over time | Reading plan on 3 Aug: weekdays 9:30 pm. On 18 Aug: weekdays 7:00 am. On 9 Sep: Saturdays 9 to 10. An unrelated tap-washer note is left out | Summary: now Saturday 9 to 10, weekdays only as extras | Recall finds one current answer instead of three versions, the oldest of which misleads |

**Table 3.5.** Two curation examples from the evaluation.

**Supervised improvement can make the system better, but at a price.**
In Experiment 4, Sculptor diagnosed why Librarian missed correct passages: its assessor saw only 3 candidates per planned part.
Sculptor's proposed fix keeps 20.
A person approved every step, and the held-back set stayed unseen during the work.

| Search | Practice selected | Held-back selected | Words handed over (practice / held-back) | Input tokens per practice need | Key learning |
|---|---|---|---|---|---|
| Before: 3 per part | 17/20 | 16/20 | 1,278 / 958 | 4,571 | Correct passages were cut |
| After: 20 per part | 20/20 | 20/20 | 4,837 / 4,811 | 11,399 | No question got worse, but Librarian reads 3.8 times the words and 2.5 times the input tokens |

**Table 3.6.** Experiment 4 results. Source: `docs/evaluation/retrieval-research-experiment-4-2026-10-01.md`.

The fix was not switched on for users.
Perfect selection on 20 needs did not justify 2.5 times the cost on every turn.
Harness² (Xu et al., 2026) runs a similar propose, probe, and compose loop without a person.
In Linger, a person approves each round, because Sculptor is proposing changes to the system that reviews it.

*[Figure 3.15, existing. Sculptor helps improve the system, and a person approves each round.]*
