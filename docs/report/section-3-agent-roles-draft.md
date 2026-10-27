## 3. Agent Roles and Design

This section covers the controls that run before any model, the five agents, the typed hand-offs between them, and the review that runs before release.
Every diagram uses one key: grey boxes are agents, white boxes are application code, and dashed pills are fixed replies that end the turn.
One rule holds throughout: agents decide and propose, and only application code releases text or writes storage.

### 3.1 Input boundary: controls before any model

Every Line passes the checks in Figure 3.1, in order.
Each check either lets the Line continue or ends the turn with a fixed reply.
Only step 7 uses a model: Provenance, with no tools, classifies the Line, and the application chooses the reply.

![Input checks in order, each with its fixed reply](images/section-3/figure-3-input-boundary.svg)

**Figure 3.1.** Input checks, in order. A first-person self-harm phrase skips the English check, so a self-harm statement written partly in another language still reaches the self-harm reply.

| Check | Example Line | Code | Tests |
|---|---|---|---|
| 1. Rate limit | An 11th message from the same account within one minute | `apps/backend/rate_limit.py` | `tests/test_chat_rate_limit.py` |
| 2. Hidden-character removal | "Chapter 2 felt strange", with "ignore your rules" hidden in invisible Unicode | `apps/backend/message_normalization.py` | `tests/test_message_normalization.py` |
| 3. Privacy and credential check | An email address, a phone number, or an API key | `src/linger/contracts/security_validation.py`, `apps/backend/chat_turn.py` | `tests/test_security_validation.py`, `tests/test_chat_endpoint.py` |
| 4. English check | A message written mostly in French | `src/linger/orchestration/language_guard.py` | `tests/test_language_guard.py`, `tests/test_chat_language_boundary.py` |
| 5. Injection rules | A message that matches an adopted override pattern | `src/linger/contracts/security_validation.py`, `apps/backend/chat_turn.py` | `tests/test_security_validation.py` |
| 6. Self-harm phrase match | "I want to hurt myself" | `src/linger/orchestration/self_harm_detection.py` | `tests/test_self_harm_detection.py` |
| 7. Emotional preflight | Grief that is still raw | `src/linger/orchestration/emotional.py` | `tests/test_emotional_boundary.py`; live suite in Section 4.6 |
| None of the above | "I've finished Chapter 2 of Alice. Her changes in size made me feel out of place." | `apps/backend/chat_turn.py` | Continues to Muse |

**Table 3.1.** Input checks, with an example, code, and tests. Section 7.1 reports the contract tests.

### 3.2 The agents

Each agent receives a bounded slice of the turn that the application chooses.
Figure 3.2 shows what each agent can see, so the subsections below do not repeat it.

![Matrix of what each agent can see](images/section-3/figure-3-agent-visibility.svg)

**Figure 3.2.** What each agent sees. Sources: each role's typed input in `src/linger/agents/*/models.py`.

#### 3.2.1 Muse

Muse owns the conversation.
It is the only agent that sees released session history and the only one that writes user-facing prose.
Each turn runs in up to three steps (Figure 3.3).

![Muse turn: triage, tool grants, draft, review, and one revision](images/section-3/figure-3-muse-turn.svg)

**Figure 3.3.** One Muse turn. Triage labels become tool grants in application code; Muse never names its own tools.

- **Step 1, triage.** Muse labels the Line by three needs: book content, memory, and override attempt. The labels carry no tool name. Table 3.2 shows how the application turns them into grants (`src/linger/orchestration/triage.py`).
- **Step 2, draft.** Muse writes the reply and chooses which granted tools to call. It returns a `MuseCandidate`: the reply, an evidence declaration, and one memory nomination or a reason for none.
- **Step 3, revise.** If Provenance asks for a revision, Muse rewrites only the flagged sentences. Sentence labels keep the rest unchanged, and no new tool appears.
- **Cannot.** Muse cannot release its reply, write memory, or write a search query. Its tools take only identifiers or an intent, and the application supplies the user's exact words (`src/linger/agents/muse/tools.py`).

| Triage labels | Tools offered | Pinned Serendipity intent |
|---|---|---|
| `book_content` is yes or unsure | `librarian_route`, `librarian_search` | None |
| `memory` is not `none` | `serendipity_explore` | Set by the memory label, for example `own_earlier_reflections` pins `recall_memory`. A call with another intent is rejected |
| `book_content: no`, `memory: none` | Only tools used in earlier released turns | None |
| `override_attempt: attempted` | Only tools used in earlier released turns, plus book tools if the application's book override is set | None. The override signal is recorded as `attempted` |
| Triage fails | Book tools, plus tools used in earlier released turns | None. The override signal is recorded as `unknown` |

**Table 3.2.** Triage labels and the tools they offer. Code: `src/linger/orchestration/triage.py`. Tests: `tests/test_muse_tool_exposure.py`, `tests/test_muse_turn_triage.py`.

#### 3.2.2 Librarian

Librarian keeps book answers within what the user has read.
It has no tools: search, fusion, reranking, and permission checks are application code.
Figure 3.4 shows its two stages: resolve the reading boundary, then find and judge evidence inside it.

![Librarian: boundary resolution, then planning, retrieval, and judgement](images/section-3/figure-3-librarian.svg)

**Figure 3.4.** Librarian's chain of typed judgements. Grey steps are model runs; white steps are application checks.

- **Private inference.** Boundary inference may read full-work candidates to locate the user. It has authority to locate, never to disclose.
- **Lifetime.** An inferred ceiling lasts one turn and never widens a confirmed one. The application saves user-confirmed chapters per account and work.
- **What Muse sees.** A fixed application sentence about evidence strength, never Librarian's free-text reason.
- **Code.** `src/linger/agents/librarian/`, `src/linger/orchestration/boundary.py`, `src/linger/orchestration/evidence_strength.py`, `apps/backend/hybrid_librarian.py`.

#### 3.2.3 Serendipity

Serendipity returns one supported connection, a recall of the user's own words, or a typed decline.
The application builds its scope and rechecks its output (Figure 3.5).

![Serendipity: scope, bounded search loop, recheck](images/section-3/figure-3-serendipity.svg)

**Figure 3.5.** One Serendipity request. The intent selects the skill; a recall request grants memory search only.

- **Bounded run.** At most 14 tool calls and 16 model requests: one book search, one web search, and a page for each web result, twice over (`src/linger/orchestration/connection.py`).
- **Decline on a tie.** A tie between the top two candidates produces a decline, which the proposal contract also enforces.
- **Recheck.** Output is rejected if its evidence exceeds the grant or cites a web page not opened in this run.

#### 3.2.4 Provenance

Provenance is the independent reviewer.
It has no tools, no conversation history, and a fresh typed input on every run.
One agent runs three skills: emotional preflight (Section 3.1), candidate review (Section 3.4), and curation review (Section 3.6).

![Provenance: input ordered by trust, three decisions, and two other skills](images/section-3/figure-3-provenance.svg)

**Figure 3.6.** Provenance candidate review. Its input separates trusted application context from untrusted tool outcomes and the untrusted candidate.

- **Separate decisions.** The response decision and the capture decision are separate, so an acceptable reply can still have its memory nomination vetoed.
- **Reject, never revise.** A finding of spoiler, prompt injection, policy override, harmful content, or instruction disclosure requires rejection.
- **Code.** `src/linger/agents/provenance/skills.py`, `src/linger/agents/provenance/review_validation.py`.

Sculptor does not run during a chat turn; Section 3.6 covers it.

### 3.3 Reasoning boundary: typed hand-offs

Agents never call each other (Figure 1, Section 2.1).
Every hand-off passes through application code as a typed object.

The application enforces four rules on every hand-off:

- **Typed and minimal.** Each hand-off is a Pydantic object that carries only the fields the next step needs and rejects unknown fields. Full transcripts are never passed.
- **Identifiers looked up again.** Ids that an agent returns are resolved by the application; unknown ids are rejected.
- **Exact wording.** Book searches use the user's exact words, never a model's paraphrase.
- **Scope before content.** Retrieval selects eligible chapters before it opens any unit file, so units beyond the reading position never reach a model.

| Hand-off | Input to output | Authority note |
|---|---|---|
| Application to Provenance, preflight | `EmotionalBoundaryInput` to `EmotionalBoundaryAssessment` | Current Line and versioned policy only |
| Application to Muse, triage | `TurnTriageInput` to `TurnNeeds` | Labels only; the application decides the grants |
| Application to Muse, draft | `MuseDraftInput` or `MuseRevisionInput` to `MuseCandidate` | A revision keeps the original turn's authority; at most one is permitted |
| Muse to Librarian, via tools | `librarian_route`, `librarian_search` to `LibrarianResponse` | Muse writes no query; the application supplies the request id and scope |
| Application to Librarian | Boundary, event, plan, and assessment inputs to typed decisions | Spans must be exact user text; the chapter grant comes from supporting records, not the model's number |
| Muse to Serendipity, via tool | `serendipity_explore` to `ConnectionProposal`, `MemoryRecall`, or `ConnectionDecline` | Fresh dependencies per request; cited ids and scope rechecked after the run |
| Serendipity to Librarian, via tool | `search_librarian` to `InternalSearchResult` | `work_ids` outside the grant are rejected; ids must appear in the run ledger |
| Application to Provenance, review | `ProvenanceInput` to `ProvenanceReview` | A revision review carries one resolution per earlier finding |
| Application to Sculptor | `AccountScopedMemories` to `CurationProposal` or `NoCurationProposal` | Account identity excluded |
| Application to Provenance, curation | `CurationReviewInput` to `CurationProvenanceReview` | The verdict must echo the proposal digest |
| Application to Memory and Policy Service | `ApprovedCuration` or `AutomaticMemoryCandidate` | Refused if the digest, sources, capture policy, or sensitivity check fails |

**Table 3.3.** Typed hand-offs, in the order they occur.

Figure 3.7 shows one recorded hand-off.

```json
{
  "tool_name": "librarian_search",
  "request": {
    "work_id": "pg11",
    "book_version_id": "pg11-v01b38ea4",
    "max_final_evidence": 5
  },
  "outcome": "success",
  "response": {
    "kind": "result",
    "outcome": "evidence_found",
    "evidence_strength": "sufficient",
    "strength_reason": "The requested reference to Alice's changes in size is directly …",
    "searched_scope": {
      "work_id": "pg11",
      "book_version_id": "pg11-v01b38ea4",
      "max_chapter_inclusive": 2
    }
  }
}
```

**Figure 3.7.** One recorded Librarian hand-off. The request carries no search text, and the response states the scope it searched: up to chapter 2.

### 3.4 Output boundary: review and release

Every Muse candidate passes the same path before release (Figure 3.8).
Any failure ends in a safe decline: fixed text that reveals nothing from the rejected candidate and writes nothing.

![Release path: validator, Provenance review, one revision, release recheck, safe decline, memory capture](images/section-3/figure-3-release.svg)

**Figure 3.8.** From candidate to release. Only text that passes every check, or an application-authored safe decline, reaches the user.

| Check | What it rejects | Code |
|---|---|---|
| Candidate validator | Claimed spans that are not exact reply text; evidence ids that do not resolve. The error goes back to Muse for repair | `src/linger/agents/muse/agent.py` |
| Review validation | A review inconsistent with its input. The application computes the quotation checks itself and judges the reviewer's audit against them | `src/linger/agents/provenance/review_validation.py` |
| Evidence binding | A declaration that does not bind to the request-scoped index, which holds only records retrieved this request or cited earlier in the session | `src/linger/orchestration/turn_context.py` |
| Release recheck | Leaked Muse instructions, a wrong source location, or a quote missing from the reply or the record | `src/linger/orchestration/reflection.py`, `src/linger/orchestration/instruction_leak_detection.py` |

**Table 3.4.** Application checks on the output path.

A Provenance pass is necessary but never sufficient: a confident review cannot release a quotation the index cannot bind.
Figure 3.9 shows a review that sent a draft back once before passing it.

```json
{
  "provenance_verdicts": ["revise", "pass"],
  "finding_codes": ["unsupported_claim"],
  "revision_count": 1
}
```

**Figure 3.9.** A recorded Provenance outcome. The first review found an unsupported claim; the revised candidate passed.

### 3.5 Worked example: one turn through all five agents

This subsection follows one message through the system.
It is Scene 09 of Maya's Scenario, the evaluation Scenario that uses all five agents (Section 4.2.1).

Maya Tan is a synthetic user: an arts coordinator in Singapore who helps run a reading circle.
Her account holds 15 memories, including one from 12 September: she promised to host her reading circle next month.
In Scene 09 she writes:

> "I keep coming back to that idea that we're just a bundle of perceptions. I'm a different person at work than with my old friends. And the thing I said I'd host next month: every time something more fun comes up, I tell myself one more day of not preparing won't matter. Does anything I've read back up the idea that when my mood shifts I'm not really the one who promised, so I'm off the hook?"

In short: I keep changing, so am I still bound by my promise?
Table 3.5 shows what each agent saw and decided. Serendipity reaches the book through Librarian, so step 5 runs inside step 4.

| Step | Who | Sees | Decides | Boundary |
|---|---|---|---|---|
| 1. Preflight | Provenance | Her message only | Not distress; reflection continues | No tools |
| 2. Triage | Muse | Her message only | Book content: yes. Memory: `source_comparison`. Override: `no_attempt` | Labels carry no tool name |
| 3. Grants | Application | The triage labels | Connection tool granted, pinned to `find_connection`; memory capture off | The application passes her exact words |
| 4. Connection | Serendipity | Her message; allowed sources: memory, books, web | Picks "Identity is not an excuse" (direct fit, high value) over "Related self and commitment" (medium value). Returns a tentative claim, a follow-up question, and 5 evidence items: 1 note, 3 book passages, 1 web page | No account identity; at most 14 tool calls |
| 5. Book evidence | Librarian, with retrieval code | Her message; her 5 reading limits | Plans three lookups from her exact words. Code finds 61 passages; Librarian keeps 3 (Alice ch. 5, Pinocchio ch. 30 twice), judged sufficient, with one stated limit | Code never reads past her chapter |
| 6. Draft | Muse | Serendipity's connection and evidence | Drafts a reply citing the web page, a book passage, and her note | Cannot release its draft |
| 7. Review | Provenance | Draft, evidence, caveats; no history | Claim groups backed 4 of 4; quote exact; caveats 2 of 2. Verdict: pass | Pass required before release |
| 8. Release | Application | The passing candidate | Rechecks each quote against source and reply, then releases | Only code releases text |

**Table 3.5.** Scene 09, step by step.

The released reply opens: "I don't see Hume's account backing the 'off the hook' conclusion …".
It cites Hume without making him a rule, uses her own note and Pinocchio chapter 30, and leaves the judgement to her.
The Scene passed all six graded stages on live replay.
Figures 3.10 to 3.13 show each agent's step as recorded in the trace.

*[Figure 3.10, existing. Scene 09, Muse: triage labels become code grants.]*

*[Figure 3.11, existing. Scene 09, Serendipity: searches, ranks, and returns one connection.]*

*[Figure 3.12, existing. Scene 09, Librarian: plans and judges; code stops at her page.]*

*[Figure 3.13, existing. Scene 09, Provenance: reviews twice; code releases.]*

### 3.6 Sculptor in the background

Sculptor does not take part in a chat turn.
It curates memories after a capture, and it can propose system improvements offline.
In both roles it only proposes: it has no account identity and cannot edit a memory.

**Curation.**

1. After a new capture, the application selects that record and up to 11 earlier records with matching terms.
2. Sculptor sees only memory id, text, and recording time. It proposes one action or no change.
3. The application binds the proposal, source hashes, and curation state into one plan digest.
4. Provenance reviews the plan against the exact sources; its verdict must echo the digest.
5. The Memory and Policy Service re-reads and re-hashes the sources, rejects stale state, and appends one immutable audit event.

Originals are never edited (`src/linger/orchestration/curation.py`). Table 3.6 shows two examples from the evaluation.

| Case | Stored notes | Sculptor's proposal | Key learning |
|---|---|---|---|
| Same fact, new words | "Library card expires 30 Nov; renew at the branch" and "Renewal due by 30 Nov so I can keep borrowing" | Link the two notes as duplicates | One fact is stored once in the curated view |
| Fact changed over time | Reading plan on 3 Aug: weekdays 9:30 pm. On 18 Aug: weekdays 7:00 am. On 9 Sep: Saturdays 9 to 10. A 10 Sep note about a tap washer is left out | New summary: now Saturday 9 to 10, weekdays only as extras | "What's my reading plan?" finds one current summary instead of three versions |

**Table 3.6.** Two curation examples. The originals stay untouched.

*[Figure 3.14, existing. Sculptor curates memories in the background.]*

**Supervised improvement.**
In Experiment 4 (1 October 2026), Sculptor analysed retrieval misses, researched a remedy, and specified a fix.
Its diagnosis: Librarian's assessor received only 3 candidate passages per planned part, which cut correct passages.
The fix keeps 20 per part.
A person approved every step, a developer built the fix behind an evaluation-only option, and the held-back set stayed unseen during the work.

| Search | Practice selected | Held-back selected | Words handed over (practice / held-back) | Input tokens per practice need | Key learning |
|---|---|---|---|---|---|
| Before: Sculptor's tags (Stage 2) | 17/20 | 16/20 | 1,278 / 958 | 4,571 | Correct passages were cut at 3 per part |
| After: 20 per part (Round 1) | 20/20 | 20/20 | 4,837 / 4,811 | 11,399 | No question got worse, but Librarian reads 3.8 times the words (5 times on held-back) and 2.5 times the input tokens |

**Table 3.7.** Experiment 4 results. The held-back set was used before, in Experiment 3. Source: `docs/evaluation/retrieval-research-experiment-4-2026-10-01.md`.

The setting is not active for users, and Sculptor gained no runtime authority.
Harness² (Xu et al., 2026) runs a similar propose, probe, and compose loop with no person in it; in Linger, a person approves each round.

*[Figure 3.15, existing. Sculptor helps improve the system, and a person approves each round.]*
