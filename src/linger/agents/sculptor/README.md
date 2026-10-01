# Sculptor

Sculptor owns one reusable PydanticAI object, `sculptor_agent`, with five
application-selected skills. All produce proposals. A separate model run
selects each task's instructions and output schema from
[`skills.py`](skills.py).

| Skill | Typed input and output | Entry point and current consumer |
|---|---|---|
| [Memory curation](skills/memory-curation/SKILL.md) | `AccountScopedMemories` → `SculptorResponse` | `propose_curation` is used by the callable reviewed curation loop and bounded-curation evaluation. |
| [Memory surfacing](skills/memory-surfacing/SKILL.md) | `SurfacingInput` → `SurfacingDecision` | `propose_surfacing` supports offline evaluation only. Chat never runs it, and it has no scheduling or notification consumer. |
| [Retrieval error analysis](skills/retrieval-error-analysis/SKILL.md) | `ErrorAnalysisInput` → `ErrorAnalysis` | `propose_error_analysis`, offline Experiment 4 only. |
| [Retrieval research](skills/retrieval-research/SKILL.md) | `ResearchInput` → `ResearchSpecification` | `propose_research`, offline Experiment 4 only; web search with budgets. |
| [Chapter cues](skills/chapter-cues/SKILL.md) | `ChapterCueRevisionInput` → `ChapterCueRevision` | `propose_chapter_cues` supports the offline chapter-cue experiment (`evals/librarian/chapter_cue_recall.py`). It revises every chapter's description, characters, and retrieval cues from practice search outcomes; a human approves each proposal before search reads it. |

Curation receives two to twelve existing memories selected for one account.
The model sees their IDs, text, and `recorded_at` when the application knows
when each was captured, and, once any curation exists, the
application-owned `existing_curation` for those memories: duplicate links,
retrieval tombstones, derived summaries, and topic groups. An undated batch without existing curation keeps the same user JSON as before,
although the skill instructions changed. Production batches are dated from
each record's capture time. It proposes a duplicate link, derived
summary, topic group, retrieval tombstone, retrieval restore, or no change.
Strict schemas and application validation reject malformed proposals and IDs
outside the supplied batch. The callable `run_curation_loop` asks Provenance
to review a digest-bound plan before the Memory & Policy Service can apply it.
The service checks account scope, source hashes, and current curation state.
This workflow is separate from conversation turns. Standalone bounded-curation
replay without an injected handler runs the same loop in an isolated temporary store and records the review decision,
application result, audit verification, and resulting retrieval IDs. Ground
truth can grade these outcomes alongside proposal quality and source preservation.
A replay does not establish later conversational retrieval quality.

Surfacing receives bounded memories, an explicit current time, current context,
and prior suggestions. It returns `surface_now`, `defer`, or `do_not_surface`.
The model never receives account identity. Application validation checks the
schema, source IDs, and any future reconsideration time. A deferral does not
schedule work, and a proposal does not deliver a message.

Chapter cues receives a book's chapter text and current cues, a word budget,
and earlier rounds of practice outcomes, including the failure patterns it
named before. It returns the failure patterns it sees and cues for every
chapter. The `SculptorTaskValidation` capability retries missing or repeated
chapters and over-budget cues within the run. It never changes book text,
and only an approved proposal reaches search, through a temporary corpus copy.

Retrieval error analysis and retrieval research support Experiment 4
(`evals/librarian/research_loop.py`). Error analysis reads practice retrieval
traces and returns a note per trace and counted failure categories. Research
reads the owner-approved analysis, searches the web through a per-run
`ResearchSearch` capability (Exa `web_search` and `get_page`, with search and
page budgets, opening only URLs it found), and returns a specification that a
developer builds. Both run at high reasoning effort.

Only retrieval research has tools. Memory curation and surfacing retain one
output retry; chapter cues, error analysis, and research retain two. Shared instructions in
`agents.sculptor` in the [`prompt catalogue`](../../prompts/prompt_catalog.yaml)
contain the common trust and authority rules. Each run adds only the selected
`SKILL.md`, with no retained history or shared request state. Fingerprints cover
the effective instructions and contracts. `build_sculptor_agent` accepts an
injected model; production model overrides cover both skills.

Surfacing is offline only; chat never runs it. Scheduled operational playbooks
remain unimplemented.

See the [runtime architecture](../../../../docs/agent-skills.md),
[Sculptor design](../../../../docs/design/sculptor-design.html), and
[Sculptor evaluations](../../../../evals/sculptor/README.md).
