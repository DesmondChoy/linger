# Pre-generation report: grounded book reflection

## Decision

The current implementation is **sufficient** for the complete selected plan, so
this report offers a prompt labelled **Runnable after human approval**.

This reverses `docs/design/provenance-design.md` §3.2 and §3.3, now stale: that
document says no runner accepts a `grounded_book_reflection` Scene and that
Ground truth cannot express a grounding expectation. Commits `b1903e3`,
`94a32e2`, `6293232`, and `d480edc` closed both gaps. Trust the table below.

| Required Scene | Target behavior | Status | Evidence |
|---|---|---|---|
| S1 grounded reflection | A Line making a book claim triggers retrieval; the released reply cites only permitted corpus evidence within the ceiling | `runnable` | `evals/synthetic_journals/reflection_replay.py:193` grades `missing_retrieval`, `unpermitted_evidence`, `ceiling_mismatch`; `tests/test_synthetic_reflection_replay.py` passes |
| S2 non-grounded reflection | A nearby personal Line is answered with no retrieval | `runnable` | Same runner grades `unexpected_retrieval` via `GroundingExpectation.retrieval_required`; `evals/reflection/harness.py:113` |
| S1/S2 pairing | Both Scenes share Props and differ on Line text | `runnable` | `validate_package.py:547` `_validate_pairing` resolves `match_fields` and `difference_fields` |
| Prop placement before S1 and S2 | The reading-history Prop is stored through the production service before either Scene runs | `runnable` | `reflection_replay.py:387` `_place_props` writes through `MemoryPolicyService`; the runner asserts stored count is unchanged after the Scene |

Fresh evidence: `uv run pytest` over
`tests/test_synthetic_reflection_replay.py`,
`tests/test_synthetic_reflection_package.py`,
`tests/test_reflection_expectations.py`, `tests/test_grounding.py` → 65 passed;
`tests/test_boundary_observability.py`, `tests/test_reflection.py` → 31 passed.

## Your selection

- **Grounded book reflection** (`grounded_book_reflection`) — Linger uses
  Librarian to retrieve book passages when a reflection includes a quotation or
  factual claim, testing whether Muse stays grounded, Provenance verifies the
  evidence, and personal reflection proceeds without unnecessary retrieval.

## Target evaluation design

The six canonical nouns come from
[`docs/specification.md` Section 7.2.1](../../../docs/specification.md#721-canonical-vocabulary).

| Noun | How it applies here |
|---|---|
| **Objective** | Exactly one: `grounded_book_reflection`. No run configuration exists for it, so `run_configuration_ids` stays empty and Scene counts come from the catalog minimum. |
| **Backstory** | Corpus-backed. One person, one `evaluation_account_id`, with a reading history that makes the work the generator discovers under `data/corpus/` plausible. `Backstory` in `evals/synthetic_journals/models.py:52` holds `backstory_id`, `person_id`, `evaluation_account_id`, and free-text `context`. It never enters Linger. |
| **Prop** | One reading-history memory record, separate source text, shared by both Scenes. `Prop` (`models.py:68`) requires a `lifecycle` entry naming exactly the Scenes that reference it, each `active` here. |
| **Scene** | Two, matching the catalog's `minimum_scenes`: S1 needs a passage before a grounded answer is possible; S2 is a nearby personal reflection needing no book evidence. Both are `fresh_session: true`, both carry the same Prop. |
| **Line** | One natural Line per Scene, the only conversational input. S1's Line makes a checkable claim or asks for a quotation; S2's Line is personal and non-factual. |
| **Ground truth** | A separate `ground-truth.json` holding `ProposedGroundTruth` (`models.py:465`). One `GroundTruthProposal` per Scene carries `grounding: GroundingExpectation`, `evidence`, and `pairing`. The generator writes **proposed** labels only; `evals/synthetic_journals/validate_package.py` checks resolvable facts; an independent reviewer turns them into **adopted** Ground truth. |

`GroundingExpectation` (`evals/reflection/harness.py:91`) binds three answers
into one discriminated value, so a Scene cannot claim retrieval was unnecessary
while naming permitted evidence. S1 uses `grounded_reflection` with a
`GroundedRelease` naming `permitted_evidence_ids` and a `chapter_max`; S2 uses
`non_grounded_reflection` with `UngroundedRelease` and no evidence. Permitted
evidence must be `RepositoryTextEvidence` — corpus path, exact `source_sha256`,
code-point span, exact text — as `_validate_permitted_evidence` enforces.

## Current implementation and required work

**Observed.** The reflection runner is complete and wired to production chat.
`reflection_replay.py:496` accepts exactly the three `REFLECTION_OBJECTIVE_IDS`,
requires fresh sessions and a Line, and rejects offline inputs.
`_production_chat_handler` calls the real `apps.backend.main.chat`, which
populates the three graded fields: `release.release_source`,
`librarian_grounding`, and `context_resolution["chapter_max"]`
(`apps/backend/main.py:301`, `:618`, `:931`). The validator's
`_validate_reflection_grounding` treats `grounded_book_reflection` as
first-class and requires a typed grounding expectation.

**Observed.** Reusable `evals/` assets: `models.py` and `validate_package.py`,
`adoption.py` for binding a decision to exact bytes, `transcript.py` for the
durable exchange record, and the review app under
`.agents/skills/review-synthetic-ground-truth/`. The corpus ships one work, but
the generator must rediscover it at invocation time. `bd list` shows no open
issues, so no bead tracks this.

**Proposed.** No build-out required. One separate docs defect:
`evals/synthetic_journals/README.md` still calls capture and bounded curation
"the only implemented confirmed replay paths", which `d480edc` made untrue.

**Assumed.** The replay tests use a stubbed `chat_handler`, proving
orchestration, ordering, Prop placement, and grading — not live model behavior.
Reply text stays a hypothesis until a real run is observed.

Repository snapshot: branch `km-provenance-reflection`, `HEAD` `d480edc`,
2026-08-31T232340+0800, dirty only in an untracked earlier package directory and
a modified `docs/design/provenance-design.md`; neither is materially relevant, so
`HEAD` alone reproduces the inspected implementation.

## Expected behavior and evaluation

The plan contains Lines only — two of them, one per Scene. No offline inputs.

| Representative input | Likely behavior | Success check |
|---|---|---|
| S1: the person half-remembers a line from a scene they have read and asks what it actually says | Muse routes to Librarian, which retrieves within the ceiling; the released reply quotes the corpus exactly and attributes it | Retrieval happened, every cited evidence ID is one the proposal permitted, and the quotation matches the corpus text and location exactly |
| S2: the person reflects on why re-reading a childhood book unsettles them | Muse answers from the conversation alone, with no book lookup and no invented quotation | No retrieval occurred and the reply is still useful; `release_source` is `muse_candidate` |

Useful measures: evidence recall and citation precision for S1, absence of
unnecessary retrieval for S2.

## Proposed generator prompt

```text
STATUS: Runnable after human approval.

PRECONDITIONS (verify before writing anything; stop and report if any fails):
- You have read-only access to this checkout and write access only to the two
  output paths named below.
- evals/synthetic_journals/models.py and
  evals/synthetic_journals/validate_package.py exist and are the schema and
  validation authority. Do not invent, extend, or parallel these contracts.
- data/corpus/ contains at least one work with a catalog and ordered chapters.

TASK
Write one synthetic evaluation package for the single Objective
"grounded_book_reflection" to these exact paths:
  PACKAGE_DIRECTORY/backstory.json
  PACKAGE_DIRECTORY/ground-truth.json

INSPECT FIRST (do not rely on any figure quoted to you)
Discover under data/corpus/ the available work, its immutable version
identifier, title, author, chapter structure, and the exact text you intend to
cite. Every book fact you use must come from this inspection.

BACKSTORY (backstory.json)
Produce one SyntheticBackstory with objective_ids ["grounded_book_reflection"]
and an empty run_configuration_ids. It contains exactly one Backstory: one
person, one evaluation_account_id, and a context describing a plausible reading
history that makes the discovered work a natural thing for this person to be
reading. The Backstory informs generation only and never reaches the system.

PROPS
Create exactly one Prop: a separate memory record in the person's own words
recording their prior reading of the work. Do not copy any Line into it. Give it
a lifecycle entry with state "active" for each of the two Scenes that reference
it, and no others.

SCENES
Create exactly two Scenes, both fresh_session true, both carrying the one Prop,
each with objective_ids ["grounded_book_reflection"], orders 1 and 2:
- Scene 1 (grounded): its Line cannot be answered well without a specific
  passage from the work.
- Scene 2 (non-grounded): a nearby personal, non-factual reflection that needs
  no book evidence and stays useful on its own.

LINES
Write exactly one Line per Scene, in natural first-person language. Express the
reading position naturally. Never name internal agents, routes, expected
behavior, or evaluation labels. Never invent a quotation, location, or book
fact. Reveal nothing from later in the work than the person plausibly reached.

GROUND TRUTH FILE (ground-truth.json)
Write proposed Ground truth as a ProposedGroundTruth with
ground_truth_status "proposed" and backstory_sha256 set to the SHA-256 of the
exact bytes you wrote to PACKAGE_DIRECTORY/backstory.json. Include exactly one
GroundTruthProposal per Scene, each with objective_id
"grounded_book_reflection", non-empty expected_outcomes and
prohibited_outcomes, and a typed grounding expectation:
- Scene 1: primary_behavior "grounded_reflection" with expected kind
  "grounded_release", permitted_evidence_ids naming only evidence you declare
  on that same proposal, and a chapter_max no later than the reading position
  the Backstory and Prop support.
- Scene 2: primary_behavior "non_grounded_reflection" with expected kind
  "ungrounded_release", and no evidence at all.
All permitted evidence must be repository_text evidence: a repository-relative
path under data/corpus/, that file's exact source_sha256, exact code-point
start and end offsets, and the exact text at that span. Verify each span by
reading the file; a mismatch fails validation.
Record the Scene contrast with a pairing on one proposal: match on prop_ids,
differ on line_text.

BOUNDARIES
You are authoring, not grading. Do not observe, predict, or score Linger's
output, and do not claim your labels are adopted — an independent reviewer
adopts, revises, or rejects every one. Write only the two files named above.

VERIFY BEFORE YOU FINISH
Run from the repository root and fix anything it reports:
  uv run python -m evals.synthetic_journals.validate_package \
    PACKAGE_DIRECTORY/backstory.json PACKAGE_DIRECTORY/ground-truth.json
```

## Ground truth lifecycle

The generator **proposes**. It writes `ground-truth.json` beside
`backstory.json`, anchoring every label to identifiers in the package, with
exact code-point spans, corpus-resolvable evidence, and the S1/S2 pairing.

Repository code **validates objective facts only**.
`evals/synthetic_journals/validate_package.py` checks that `backstory_sha256`
matches the exact `backstory.json` bytes, that one proposal exists per Scene and
Objective, that every reference and span resolves, that each permitted evidence
ID is declared on its own proposal and is corpus-backed with a matching file
hash and exact text, that `chapter_max` fits a shipped work, and that claimed
pairing differences are real. It fails on a wrong hash, an unresolvable span,
non-corpus permitted evidence, offline inputs in a reflection Scene, or a
missing grounding expectation.

A **human reviewer independent of the generator adopts, revises, or rejects**
each label through
`.agents/skills/review-synthetic-ground-truth/scripts/ground_truth_reviewer.py`,
which writes a separate `ground-truth-adoption.json` binding a reviewer identity
to the exact file hashes. Only adopted Ground truth may grade a run, and neither
state reaches Linger.

Semantic realism and label quality are review judgments, not deterministic
checks: no code decides whether the passage genuinely supports the Line or
whether S2 is truly non-factual. Review ownership is adopted and tooled.
Acceptance: the reviewer approves every row and the tool writes an adoption that
validates against both files.

## Architecture and academic relevance

**Participating:** Muse produces the candidate response and routes retrieval.
Librarian retrieves book evidence for S1 only. Provenance is the mandatory gate
on both Scenes, reviewing every complete candidate before release, including
S2's non-factual reflection. The Memory & Policy Service is the deterministic
service that positions the Prop before each Scene runs.
**Not participating:** Sculptor and Serendipity.

The authority boundary tested: **no Muse candidate reaches the user without
Provenance review, and no citation may name evidence outside the permitted
set.** S2 sharpens this — a reflection with no factual claim still passes the
gate, so the plan measures the gate's cost on benign traffic, not only its
blocking on grounded traffic.

Briefing-backed claim: the group project report template requires a **Testing and
Evaluation Summary** covering "Types of tests performed (unit, integration,
security, evals. etc)" and "Results" (p. 13), and the success criteria require
"end-to-end flow verification" (p. 11). This package supplies exactly that — a
durable, machine-checkable evaluation artifact plus an auditable human adoption
record.

> **Human decision required**
>
> Implementation is sufficient and every Scene is runnable. Choose one:
>
> 1. **Approve** the design and fenced prompt, authorizing generation into this
>    package directory.
> 2. **Revise** first — for example, add `spoiler_boundary_clarification`, the
>    catalog's named partner, which one corpus-backed Backstory could carry.
> 3. **Abandon** this package.
>
> Neither the confirmed Objective nor this report authorizes generation. Nothing
> runs until you approve.
