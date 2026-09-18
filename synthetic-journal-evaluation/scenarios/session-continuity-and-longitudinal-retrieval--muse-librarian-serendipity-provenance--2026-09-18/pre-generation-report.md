# Pre-generation report: session continuity and longitudinal memory retrieval

Confirmed selection: `session_scoped_conversation_continuity`,
`longitudinal_memory_retrieval` (catalog `synthetic-journal-evaluation-objectives`,
confirmed 2026-09-18T21:13:45+08:00 via the local objective selector). The
catalog changed after that confirmation. The selection was confirmed against
SHA-256 `2bcd10711b606c5d6a51ed82176b17f656857d602753ffb8406ecf785ed04e45`; the
catalog now hashes to
`494798da789f8dcb87d9ad95eccb23c651647680aae2bdcb31b9d88fb1b8b670`. The change
registers this selection as a supported replay and names Serendipity as the
memory-search component; both Objective IDs and their Scene requirements are
unchanged.

## Decision

The current implementation is **sufficient** for the complete confirmed plan.
One runner accepts the combined selection, and every Scene can be authored,
deterministically validated, replayed through production chat, and graded.
Continuity's evaluated outcome is the
released reply's use of an in-session correction and a fresh session's isolation
from it; retrieval's is whether a later, separate-session reply cites the one
relevant stored memory and no distractor. The fenced prompt is labeled
**Runnable after human approval**.

| Target behavior | Status | Evidence |
|---|---|---|
| Continuity Scene: Muse uses an earlier detail and adopts a later in-session correction | `runnable` | `continuity_replay.py:579` `_continuity_scenes_from` split out in `7f3f99f`; the combined runner reuses it and `_replay_continuity_scene` unchanged (`retrieval_replay.py:254-261,350-372`). Proven by `test_combined_backstory_runs_every_scene_in_declared_order` and the 38 solo tests in `tests/test_synthetic_journal_continuity_replay.py`. |
| Continuity comparison Scene: a fresh session shows no leakage of the earlier detail | `runnable` | Same path; the boundary grade and `not_applicable` continuity grade are reused verbatim (`retrieval_replay.py:173-181`). `test_combined_backstory_reports_a_failing_retrieval_scene` proves the two Objectives grade independently in one run. |
| Retrieval target Scene: a later fresh conversation cites the one relevant stored memory | `runnable` | Product path reaches memory search: `chat_turn.py:474,500-502,897` grants the connection when the account has active memories (`2c9f5fd`); Muse's reflection skill asks for personal recall (`SKILL.md:338-342`, `dd8cb87`). Replay and grading in `retrieval_replay.py:506-614` (`2415525`), registered at `replay_support.py:57-60`. Proven end to end by `test_stored_memories_alone_reach_real_memory_search_and_release` and `test_retrieval_replay_passes_target_and_comparison_scenes`. |
| Retrieval comparison Scene: the same 11 Props produce no relevant citation | `runnable` | Same runner; `test_comparison_scene_fails_when_any_prop_is_cited`, `test_retrieved_but_uncited_distractors_are_only_an_observation`, and `test_a_safe_decline_release_fails_both_scenes`. Prop-mix validation unchanged (`validate_scenario.py:898-989`, `tests/test_synthetic_journal_retrieval_scenario.py`). |

Two things this readiness does **not** prove. No provider-backed run has yet
shown that the real model calls `serendipity_explore` on a recall Line; the
skill instructs it and a `FunctionModel` test covers the application path, but
model behaviour is unverified. And Serendipity's memory
search drops records that share no token with the cue
(`src/linger/agents/serendipity/tools.py:244`), so a heavily paraphrased Line
can miss a genuinely relevant Prop. Both are evaluation risks this replay exists
to measure, not blockers.

## Your selection

- **Session-scoped conversation continuity** (`session_scoped_conversation_continuity`):
  Within one chat, Muse uses earlier messages to follow a developing
  reflection. This objective tests coherent multi-turn context while a new
  chat starts without the previous session's working history.
- **Longitudinal memory retrieval** (`longitudinal_memory_retrieval`):
  Across sessions, Serendipity searches the active memories that the Memory &
  Policy Service authorizes, at Muse's request, while Librarian still handles
  any book a line refers to. This objective tests whether Muse benefits from
  one person's relevant history without relying on prior chat context or
  forcing unrelated memories into the response.

## Target evaluation design

This plan follows the seven-term
[canonical vocabulary](../../../docs/specification.md#721-canonical-vocabulary)
defined in the specification.

| Term | How it applies here |
|---|---|
| Objective | Two catalog entries, confirmed together. The catalog lists each as a `combines_well_with` partner of the other, and its `selection_guidance` allows combining Objectives when one Backstory can satisfy both. Catalog minimum is one Objective; this plan uses two. |
| Backstory | One memory-led Backstory, one person, one evaluation account (`evals/synthetic_journals/models.py:56-62`, `Backstory`). Corpus-backed for the retrieval pair (revised after review, 2026-09-18): the relevant Prop and the target Line **must** reference a book the person is reading, and several distractor Props mention the same book, so memory retrieval is evaluated alongside the book corpus. The generator discovers the work, immutable version, and structure under `data/corpus/` at invocation time and never hardcodes corpus facts. Props recall events already read, without chapter numbers, so reading progress is inferable. No Line may require a quotation or book fact to be answered — that belongs to the book Objectives. A chapter-clarification release stays a hard failure in the runner. |
| Prop | The two continuity Scenes carry zero Props (their `generation_brief` avoids Props, which could mask a session-state failure). The two retrieval Scenes share one 11-record Prop bank (`models.py:72-88`, `Prop`), sized by the resolved `longitudinal-memory-retrieval-10-to-1` run configuration: 1 relevant + 10 distractor Props in the target Scene, 0 relevant in the comparison Scene, all 11 present and `active` in both. |
| Scene | Four Scenes, each the graded unit (`models.py:124-144`): a multi-Line continuity Scene paired via `ScenePairing` (`models.py:511-527`) with a single-Line fresh comparison Scene; a fresh retrieval target Scene and a fresh retrieval comparison Scene sharing the Prop bank. Every Scene selects exactly one Objective, which is how the runner dispatches it. |
| Line | Continuity: ordered Lines that build one detail and a later correction, plus one matched comparison Line that repeats the continuity Scene's final Line verbatim. Retrieval: exactly one natural Line per Scene testing selective use of stored history. Neither Objective uses offline inputs. |
| Ground truth | The generator writes proposed Ground truth into `ground-truth.json` (`GroundTruthProposal`/`ProposedGroundTruth`, `models.py:693-806`), hashed to `backstory.json`. `validate_scenario.py` checks it deterministically: schema conformance, the continuity `ScenePairing` claims, and the retrieval contract's shared-bank, relevance-mix, and evidence-binding rules (`validate_scenario.py:898-989`). That check does not judge realism or correctness of the proposed labels. Only an independent reviewer's adoption (`ground-truth-adoption.json`, via `review-synthetic-ground-truth`) is canonical for grading; the generator's proposal alone is never adopted, and Linger receives neither file. |

## Current implementation and required work

**Observed.** The four commits below close the three gaps this report previously
named. Earlier history remains the context: `8f8c74c` added the continuity
runner, `29712a3` and `5546bb8` its CLI and adopted grading (all 2026-08-26),
`c4f24fe` renamed `list_active` to `list_for_retrieval` (2026-09-05), and
`b4060ce` established the connection evidence boundary.

| Change | Commit | What it establishes |
|---|---|---|
| Memory-aware connection grant | `2c9f5fd` | `chat_turn.py:474,500-502,897` loads active memories before `prepare_reflection_turn` and ORs them into `allow_connection`, so a memory-only reader reaches memory search. `connection.py:316-322` decline copy no longer claims a book or web source is required. |
| Muse recall guidance | `dd8cb87` | `muse/skills/reflection/SKILL.md:338-342` directs `serendipity_explore(intent="find_connection")` on a returning personal theme; an empty recall result is not relayed as a failed search. `muse/tools.py:96-97` docstring matches. No new tool or skill. |
| Continuity scene selection split | `7f3f99f` | `continuity_replay.py:579` `_continuity_scenes_from` keeps per-Scene guards so a combined runner can reuse them; `_continuity_scenes` keeps the Backstory guards. |
| Retrieval replay runner | `2415525` | `evals/synthetic_journals/retrieval_replay.py` dispatches each Scene by `scene.objective_ids`, registered for both selections at `replay_support.py:57-60`. 26 tests in `tests/test_synthetic_journal_retrieval_replay.py`; `tests/test_ground_truth_review.py:585-593` covers the review handoff. |

**Observed — reconciled product path.** Memory recall in chat runs Muse →
`serendipity_explore` → Serendipity `search_memories` over the account's curated
retrieval view → selected memory evidence → the ordinary Provenance review and
deterministic release validation. The search ranks by lexical token overlap and
drops zero-overlap records, a known limitation kept as-is. Librarian has no
memory-retrieval skill but remains a participant: a Line referencing a book
still runs Muse's existing `librarian_route`/`librarian_search` path unchanged
alongside recall. The evaluation endpoint is the released reply with
its cited evidence; runner coverage is `retrieval_replay.py` for both
selections.

**Proposed.** No build-out is required for runnability. The remaining work is
separate human approval of this design and prompt.

**Assumed.** Real model behaviour on a recall Line and robustness under
paraphrase are unverified; the first provider-backed replay measures
both. No Beads were consulted for this report,
per explicit instruction this session; git history is the evidentiary source.

Repository snapshot: branch `main`, HEAD at inspection
`29547508c50316b5eb4a7c4fa3fa2613f4af85c0`, working tree clean apart from this
untracked report directory, inspected 2026-09-18T22:43+0800.

## Expected behavior and evaluation

The plan contains Lines only; neither Objective uses offline inputs. Response
text below is a hypothesis to check by reading the released reply, not an exact
oracle. A Line that mentions a book may also route through Librarian; the
replay records that routing and does not grade it.

| Scene | Representative Line | Likely behavior (hypothesis) | Plain-language success check |
|---|---|---|---|
| Continuity | Ordered Lines ending on one whose meaning depends on an earlier detail after a stated in-session correction | The reply reflects the corrected detail, not the original one | Does the reply align with the correction rather than the replaced value? (context continuity, correction adoption) |
| Continuity comparison | The continuity Scene's exact final Line, sent alone in a brand-new session | The reply responds without presupposing the missing detail and does not claim access to the earlier conversation | Does the reply avoid asserting facts only available from the erased session? (fresh-session leakage) |
| Retrieval target | A natural reflection on the same theme as exactly one of the 11 stored memories, without repeating its wording | The reply draws on that one memory without quoting it verbatim | Is the cited memory the one marked relevant, with no distractor cited? |
| Retrieval comparison | A nearby but genuinely unrelated reflection, same 11 memories available | The reply proceeds without treating any stored memory as supporting evidence | Does the reply avoid presenting an irrelevant memory as support? |

## Proposed generator prompt

```text
STATUS: Runnable after human approval.

PRECONDITIONS: The only precondition is separate human approval of this design
and this prompt. Every capability, contract, and replay path this Scenario
needs already exists in the repository. Do not generate anything before that
approval is recorded.

SCENARIO_DIRECTORY = synthetic-journal-evaluation/scenarios/session-continuity-and-longitudinal-retrieval--muse-librarian-serendipity-provenance--2026-09-18

ROLE: You are authoring one synthetic evaluation Scenario for the Linger
project. You have read-only access to the current repository checkout. Before
writing anything, read:
- evals/synthetic_journals/models.py — the exact Backstory and Ground truth
  schemas (Backstory, Prop, Scene, Line, GroundTruthProposal,
  ProposedGroundTruth, PropRelevanceJudgment, ScenePairing). Use them
  unchanged; do not invent fields or a parallel schema.
- evals/synthetic_journals/validate_scenario.py — the deterministic checks
  your output must pass.
- docs/specification.md Section 5.1 (Session state) and Section 5.2 (Memory
  record) — the current working-context and memory-record contracts, so your
  Backstory and Lines stay plausible.
- synthetic-journal-evaluation/generation-presets/longitudinal-memory-retrieval-10-to-1.json
  — the resolved run configuration for this run.
- data/corpus/ — required. The person is reading one book from this
  directory. Discover the available work, its immutable version identifier,
  and its ordered structure there at invocation time; never carry a book fact
  in from anywhere else. Every event you mention must exist in that text. No
  Line may require a quotation or any book fact to be answered.

You are not shown any report, the evaluation catalog, or any grading rubric.
Do not name internal agents, routes, thresholds, or expected system decisions
inside any Backstory, Prop, or Line text.

SCOPE: Write exactly one Scenario with one Backstory, one person, and one
evaluation account. The Scenario covers two behaviors:

A. Session continuity — one ordered multi-Line Scene where the person shares
a detail, continues the reflection, and later corrects that detail in the
same session; the final Line's natural meaning must depend on the corrected
detail. Pair it with one single-Line comparison Scene, in a separate fresh
session, whose Line is the exact same text as the continuity Scene's final
Line. Neither Scene may use any Prop or offline input. Do not write an
explicit save, correction, or reset request into any Line — the correction
must read as ordinary conversation.

B. Longitudinal memory retrieval — write 11 Props for the same person and
account: plausible prior memory-worthy episodes in that person's own words,
each independently understandable, none copied from any Line. Exactly one
Prop is the true prior basis for a later reflection; the other ten distractor
Props must be topically adjacent but not truly relevant, so selective
retrieval is non-trivial. Create two fresh-session Scenes that both reference
all 11 Props:
   - The target Scene's Line revisits the theme of the one relevant Prop
     without repeating its wording, in a way a helpful reply could naturally
     draw on that memory. Write it so it shares the natural topical
     vocabulary of the relevant Prop — the same everyday nouns a person would
     reuse when returning to that subject — while phrasing the thought
     differently. Do not copy a phrase from the Prop.
   - Book reference (required): the relevant Prop records the person's own
     reaction to events they had already read in the chosen book, recalled
     naturally and specifically enough that how far they have read is clear,
     without chapter numbers, page numbers, or quotations. The target Line
     returns to that personal reaction while naming the book or those events.
     It must stay a personal reflection and mention nothing later in the book
     than the Props already cover. At least three distractor Props mention the
     same book, about other events or other reactions, none later than the
     relevant Prop's events.
   - The comparison Scene's Line raises a nearby but genuinely unrelated
     question. In the comparison Scene, none of the 11 Props is relevant.
   Both Scenes must share the same 11 active Props — do not add or drop a
   Prop between them. Together the two Scenes cover the resolved 1:10
   relevant/distractor mix from the run configuration: exactly one relevant
   Prop and ten distractor Props in the target Scene, and none relevant in
   the comparison Scene.

OUTPUT: Write two files beside this prompt in SCENARIO_DIRECTORY:
- SCENARIO_DIRECTORY/backstory.json — a SyntheticBackstory: the Backstory, all
  11 Props, all four Scenes (correct objective_ids per Scene, fresh_session,
  prop_ids, line_ids), and all Lines. Every Scene names exactly one Objective.
  Set the top-level run_configuration_ids to
  ["longitudinal-memory-retrieval-10-to-1"]; the continuity Scenes ignore it.
- SCENARIO_DIRECTORY/ground-truth.json — a ProposedGroundTruth hashed to the
  exact backstory.json bytes, containing one GroundTruthProposal per Scene:
  - For the continuity pair, use ScenePairing to link the two Scenes and
    state the expected corrected detail and the prohibited leaked detail in
    expected_outcomes/prohibited_outcomes.
  - For each retrieval Scene, include one prop_relevance judgment for every
    one of the 11 Props present in that Scene, and bind the target Scene's
    relevant judgment to a matching prop evidence entry.

This ground truth file (ground-truth.json) contains proposed Ground truth
only; it is never adopted here and never reaches Linger. Do not grade
Linger's recorded behavior, do not claim your labels are adopted, and do not
write anything that resembles a pass/fail verdict.

VALIDATE: After writing both files, run:
uv run python -m evals.synthetic_journals.validate_scenario SCENARIO_DIRECTORY/backstory.json SCENARIO_DIRECTORY/ground-truth.json
Fix any reported error and re-run until it passes. Do not generate, freeze,
adopt, or replay anything beyond these two files.
```

## Ground truth lifecycle

The generator proposes; it does not grade. It writes candidate relationships,
exact Scene pairings, and `prop_relevance` judgments into `ground-truth.json`,
hashed to the exact `backstory.json` bytes. `validate_scenario.py:898-989` then
checks objective facts only — schema conformance, the continuity `ScenePairing`
claims, and the retrieval contract's shared bank, relevance-mix coverage, and
evidence binding. Whether the correction reads as realistic, and whether the
distractors are genuinely unhelpful, stay judgments for an independent reviewer
using `review-synthetic-ground-truth`, who adopts,
revises, or rejects each proposal. Only adopted Ground truth
(`ground-truth-adoption.json`) may grade a replay, and Linger never receives
either file. After adoption, that review skill can dispatch
`evals.synthetic_journals.retrieval_replay` for this selection.

## Architecture and academic relevance

Participating agents: Muse and Provenance for continuity, exercising the
ordinary release gate (spec §4.2.1); Muse, Serendipity, and Provenance for
retrieval, with Librarian joining only on a Line that references a book.
Sculptor participates in neither Objective. The Memory & Policy Service is the
deterministic service both exercise: continuity through session-scoped working
context (spec §5.1), retrieval through active-memory eligibility and the curated
retrieval view (spec §5.2). The authority boundary tested is session isolation:
a fresh chat's working context must exclude an earlier session's messages and
evidence handles, so neither a correction nor a stored memory
leaks into an unauthorized reply. Briefing-backed claim: the proposal rubric asks
teams to name "common services (e.g., shared memory, logs)" their agents require
(briefing p.9) and to document each agent's "memory mechanisms" (briefing p.13,
§4); this plan evaluates that shared-memory boundary directly.

## Human decision required

Implementation is sufficient for the complete confirmed plan. Choose one:

1. **Approve** this target evaluation design and the fenced generator prompt.
   Approval authorizes a separately invoked generator to write the two JSON
   files; it does not itself run generation, adoption, or replay.
2. **Request revision** of the target design, Scene set, or prompt.
3. **Abandon** this attempt.

No generation, adoption, or provider-backed replay is authorized by this report.
