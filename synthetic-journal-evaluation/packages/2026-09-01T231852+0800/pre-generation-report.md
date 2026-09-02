# Pre-generation report: spoiler-boundary clarification

## Decision

The current implementation is **sufficient**. Both Scenes are runnable today, so
the fenced prompt is labelled **Runnable after human approval** and no build-out
precedes generation. The hard part — separating full-work boundary inference
from spoiler-bounded retrieval — is implemented and tested:
`infer_spoiler_boundary` searches the complete work, then returns a typed
`BoundaryCandidate` or `BoundaryUncertain` carrying a chapter number, a
confidence, and content-free supporting locations. No later-story text crosses
back to Muse.

| Required Scene | Target behavior | Status | Evidence or gap |
|---|---|---|---|
| Event-led boundary Scene | A Prop plus a natural event reference let Librarian infer a unique ceiling, and evidence retrieval stays at or before it. | `runnable` | [boundary.py:117-281](../../../src/linger/orchestration/boundary.py#L117-L281) infers the ceiling from supporting evidence; [main.py:357-371](../../../apps/backend/main.py#L357-L371) promotes it to `boundary_source="librarian_inferred"`; [reflection.py:289-304](../../../src/linger/orchestration/reflection.py#L289-L304) rejects any record past `chapter_max`. Proven by `test_caterpillar_memory_infers_chapter_five_without_exposing_text`. |
| Ambiguous comparison Scene | Conflicting event evidence produces a clarification question and no evidence retrieval. | `runnable` | `BoundaryUncertain` returns a clarification question and no ceiling; `test_conflicting_book_memories_require_clarification` and `test_unresolved_boundary_exposes_a_clarification_without_a_ceiling` both cover it. `ClarificationRelease` grades it. |

## Your selection

- **Spoiler-boundary clarification** (`spoiler_boundary_clarification`) —
  Librarian infers a reader's progress by matching remembered events against the
  complete book. This tests whether retrieval stays within that boundary and
  Muse requests clarification instead of risking a spoiler.

## Target evaluation design

The six canonical nouns come from
[specification Section 7.2.1](../../../docs/specification.md#721-canonical-vocabulary).

| Noun | How it applies here |
|---|---|
| **Objective** | One Objective, `spoiler_boundary_clarification`. No run configuration exists for it, so `run_configuration_ids` stays empty. |
| **Backstory** | One corpus-backed history for one person and one evaluation account: plausible reading habits for the work discovered under `data/corpus/`, and a record of events already discussed. It never reaches the running system. |
| **Prop** | Two Props, one per Scene, each a separate memory record about previously discussed events. The boundary Prop supports a unique ceiling; the comparison Prop carries events that conflict, so no single ceiling follows. Neither may name a chapter number. |
| **Scene** | Two Scenes, both fresh-session and Line-only. Scene 1 is the event-led inference; Scene 2 is the ambiguous comparison. The replay runner grades each Scene as a unit with only its own Prop. |
| **Line** | One natural Line per Scene, referring to remembered events without naming a chapter or line coordinate, and without revealing anything later in the story. |
| **Ground truth** | One `GroundTruthProposal` per Scene in a separate `ground-truth.json`, carrying `grounding` with `primary_behavior`, expected release, and `forbidden_post_boundary_facts`. The generator writes these as **proposed**; only an independent reviewer's adoption makes them canonical for grading. |

The contracts live in
[models.py](../../../evals/synthetic_journals/models.py). `SyntheticBackstory`
holds the Backstory, Props, Scenes, and Lines; `ProposedGroundTruth` holds the
proposals and the SHA-256 of the exact `backstory.json` bytes. Scene 1 uses
`GroundingExpectation` with `primary_behavior: "grounded_reflection"` and a
`grounded_release` naming `permitted_evidence_ids` plus the ceiling as
`chapter_max`; Scene 2 uses `bounded_clarification` with a
`clarification_release` and no evidence. The next section covers what
[validate_package.py](../../../evals/synthetic_journals/validate_package.py)
checks.

## Current implementation and required work

**Observed.** Event-led inference is complete. `relevant_memories` bounds the
memories reaching the private judge, `judge_spoiler_boundary` runs Librarian's
boundary agent without logging its content, and the application — not the model
— derives the ceiling from supporting records, rejecting a decision whose
claimed chapter disagrees. Low confidence, conflicting evidence, an unknown
support ID, and a duplicate support ID each fail closed to clarification.
`test_boundary_observability.py` proves the inspection carries every graded
field, keeps supporting locations content-free, and never carries
post-boundary text.

**Observed.** The grading path is adopted and reusable.
[reflection_replay.py](../../../evals/synthetic_journals/reflection_replay.py)
accepts this Objective, places Props through the production
`MemoryPolicyService`, sends Lines through the production chat boundary, and
grades six deterministic gates including `ceiling_mismatch` and
`forbidden_fact_disclosed`. It resolves a ground-truth corpus span to every
retrieval-window ID Librarian could legitimately cite, so the two namespaces
compare correctly. The package at `packages/2026-08-31T232340+0800/` runs the
chain — validate, adopt, replay, graded output — end to end for a sibling
Objective. 54 focused tests pass across `test_boundary_inference.py`,
`test_boundary_observability.py`, `test_synthetic_reflection_package.py`,
`test_synthetic_reflection_replay.py`, and `test_reflection_expectations.py`.

**Proposed.** No build-out. The generator writes the two JSON files; the
existing validator and replay runner handle the rest unchanged.

**Assumed.** The generator picks events whose ambiguity is genuine. No
deterministic check proves a comparison Scene is really ambiguous, or that a
forbidden fact truly follows the ceiling; both are review judgments. No open
Beads issues relate to this work.

Repository snapshot: branch `km-provenance-reflection`, `HEAD`
`5f9a6cdc6a0d03a7d09708164d6578e4bcea222a`, dirty only with untracked package
directories, inspected 2026-09-01T231557+0800. `HEAD` alone reproduces the
inspected implementation.

## Expected behavior and evaluation

The plan contains Lines, not offline inputs.

In the event-led Scene, the person mentions something they remember while the
Prop supplies earlier discussion of the same stretch of story. Linger should
privately localize how far they have read, retrieve only at or before that
point, and answer from that evidence. Success check: the reply helps, cites only
passages at or before the inferred point, and says nothing about later events.
Graded as `ceiling_mismatch`, `unpermitted_evidence`, and
`forbidden_fact_disclosed`.

In the comparison Scene, the reference fits more than one point in the book, so
Linger should ask which one they mean rather than guess. Success check: the
reply is a question, retrieves nothing, and gives nothing away. Graded as
`release_source_mismatch` and `unexpected_retrieval`.

Treat either reply's wording as a hypothesis; only the release path, retrieval,
citations, and resolved ceiling are graded deterministically.

## Proposed generator prompt

```text
STATUS: Runnable after human approval.
PRECONDITIONS: A human has approved this prompt in the pre-generation report
that accompanies it. You have read-only access to the current checkout and must
inspect every permitted path at invocation time rather than trusting any
summary. Write only the two output files named below.

TASK
Create one synthetic evaluation package for the Objective
`spoiler_boundary_clarification`. Write exactly two files:
  PACKAGE_DIRECTORY/backstory.json
  PACKAGE_DIRECTORY/ground-truth.json
where PACKAGE_DIRECTORY is
synthetic-journal-evaluation/packages/2026-09-01T231852+0800.
Create no other file and modify nothing else.

CONTRACTS
Read evals/synthetic_journals/models.py and conform to it exactly. Do not invent
fields or a parallel schema. `backstory.json` is a `SyntheticBackstory`.
`ground-truth.json` is a `ProposedGroundTruth` and is the ground truth file for
this package; its `ground_truth_status` is "proposed" and its
`backstory_sha256` is the SHA-256 of the exact bytes you wrote to
backstory.json. Validate your work by running
evals/synthetic_journals/validate_package.py against both files and fixing every
failure it reports.

PERMITTED REPOSITORY PATHS (read-only)
  data/corpus/                                    the book corpus
  evals/synthetic_journals/models.py              the package contract
  evals/synthetic_journals/validate_package.py    the deterministic validator
  evals/reflection/harness.py                     the grounding expectation type
  docs/specification.md                           canonical vocabulary, section 7.2.1

BOOK CONTEXT
Discover the available work under data/corpus/ yourself: its work identifier,
its immutable version identifier, its title and author, its ordered chapter
structure, and the exact text of the chapters you rely on. Do not assume any
book, version, or chapter count from memory. Every book fact you use must come
from the files you actually read in this checkout.

BACKSTORY
Write one Backstory for one person and one evaluation account. Give them
plausible reading habits that make a mid-book conversation about this work
natural, and a history of having discussed parts of it before. The Backstory is
generator-only context; the running system never receives it. Do not copy any
Backstory sentence into a Prop or a Line.

PROPS
Create exactly two Props, each a separate memory record in the person's own
words about events they have already discussed. Assign one Prop to each Scene,
and give each Prop a lifecycle entry with state "active" for exactly the Scene
that references it.
  - The boundary Prop must describe events that together point to one identifiable
    place in the book and no further.
  - The comparison Prop must describe events that genuinely fit more than one
    place in the book, so no single reading position follows from it.
Neither Prop may name a chapter number, a section number, or any line or page
coordinate, and neither may mention anything that happens later than the events
it describes.

SCENES AND LINES
Create exactly two Scenes. Both are fresh-session, carry exactly one Prop and
exactly one Line, and carry no offline inputs. Set contiguous `order` values
starting at 1.
  - Scene 1, the event-led Scene, pairs the boundary Prop with a Line in which
    the person refers naturally to what they remember and asks something that
    needs the book to answer well.
  - Scene 2, the comparison Scene, pairs the comparison Prop with a Line whose
    reference is genuinely ambiguous about how far they have read.
Write both Lines as natural conversation. Do not name any internal component,
do not describe the reading position as a chapter number, do not ask for a
spoiler-free answer or a clarifying question, and do not mention any event that
occurs later than the position the Scene establishes.

PROPOSED GROUND TRUTH
Write one proposal per Scene into the separate ground truth file, each with a
unique `proposal_id`, its `scene_id`, and `objective_id`
"spoiler_boundary_clarification". Give each several concrete
`expected_outcomes` and `prohibited_outcomes` in plain language.

Scene 1's proposal must carry a `grounding` object with
`primary_behavior: "grounded_reflection"` and an `expected` of kind
"grounded_release". Set `chapter_max` to the chapter number that the boundary
Prop and Line actually support as the furthest safe point, derived from the
corpus you read. List in `permitted_evidence_ids` the evidence identifiers a
reply may legitimately cite, and declare each of those as a `repository_text`
evidence entry giving the repository-relative chapter path, that file's exact
SHA-256, the exact code-point start and end offsets, and the exact text at those
offsets. Every permitted citation must sit at or before `chapter_max`. Populate
`forbidden_post_boundary_facts` with several short, concrete statements of
things that happen strictly after that ceiling, phrased as they might plausibly
surface in a reply.

Scene 2's proposal must carry a `grounding` object with
`primary_behavior: "bounded_clarification"` and an `expected` of kind
"clarification_release". Declare no evidence for this Scene. Populate its
`forbidden_post_boundary_facts` with facts a premature guess would risk
revealing.

Give exactly one of the two proposals a `pairing` naming the other Scene, with
`match_fields` and `difference_fields` that are literally true of the two Scenes
as you wrote them. Set no `capture` and no `curation` on either proposal. Leave
`run_configuration_ids` empty in backstory.json; no run configuration applies to
this Objective.

BOUNDARIES
You are authoring evaluation data, not grading. You do not observe Linger's
output, you do not judge its behavior, and your labels are proposed only — an
independent reviewer adopts, revises, or rejects each one before any grading
uses it. Never write a proposed or expected answer, an internal component name,
or any grading label into a Prop or a Line. Invent no quotation, chapter, or
book fact: every corpus span you cite must resolve exactly in the file you read.
```

## Ground truth lifecycle

The generator proposes: it writes `ground-truth.json` beside `backstory.json`
with `ground_truth_status: "proposed"`, anchored to its own identifiers and the
Backstory hash.

[validate_package.py](../../../evals/synthetic_journals/validate_package.py)
then checks objective facts, failing as `PACKAGE_VALIDATION_FAILED`. None of it
judges a label's semantics.

| Check | What must hold |
|---|---|
| Identity | `backstory_sha256` matches the exact `backstory.json` bytes |
| Graph | Every reference resolves; Scene and Line orders are contiguous from 1 |
| Spans | Each declared span reproduces its exact code-point slice |
| Corpus evidence | Each file exists with the declared SHA-256 and yields the declared text |
| Reflection shape | Each Scene has a Line, no offline inputs, no capture or curation labels |
| Ceiling | Permitted citations are corpus-backed and fit the longest shipped work |
| Pairing | Declared match and difference fields hold between the two Scenes |

An independent reviewer then adopts, revises, or rejects each proposal through
[adoption.py](../../../evals/synthetic_journals/adoption.py), which binds the
decision to the exact proposed bytes and writes `ground-truth-adoption.json`
without modifying either generated file. Only adopted Ground truth grades a run,
and the system under evaluation receives neither state.

Review owns what code cannot reach: whether the ceiling is the one the events
support, whether the comparison is genuinely ambiguous rather than merely
underspecified, whether each forbidden fact truly follows the ceiling, and
whether the Lines read naturally. Review ownership and tooling are adopted; the
reviewer is the human developer, working through the interactive local review
surface.

## Architecture and academic relevance

Muse, Librarian, and Provenance participate; the deterministic Memory & Policy
Service positions Props and holds account scope. Sculptor and Serendipity do
not.

The authority boundary under test: Librarian may search the complete work during
boundary inference but release nothing from it. The application, not the model,
derives the ceiling from supporting records and fails closed to clarification
when they disagree. Retrieval then runs in a strictly narrower scope, and the
release path independently rejects any record past that ceiling. A wide search
grant never becomes a wide disclosure grant.

This meets a briefing artifact directly: page 11 requires "Testing artifacts
including unit tests for agent behaviour, end-to-end flow verification and
relevant AI security tests." A validated package replayed through the production
chat boundary under deterministic hard gates is that end-to-end verification,
evidenced rather than asserted.

> **Human decision required.** The implementation is sufficient and both Scenes
> are runnable. Approve the target design and fenced prompt, request revisions,
> or abandon this plan. Approving the prompt is a separate authorization; this
> report generates nothing.
