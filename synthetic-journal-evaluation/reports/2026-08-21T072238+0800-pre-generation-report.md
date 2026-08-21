# Pre-generation report — memory lifecycle and bounded curation

## Snapshot
`main` @ `2174f37`, working tree **dirty** (modified `pyproject.toml`,
`synthetic-journal-evaluation/evaluation-objectives.yaml`, skill `SKILL.md`;
untracked selector `scripts/`, `tests/`, `ui/`). 2026-08-21T07:22:38+0800.
Catalog `synthetic-journal-evaluation-objectives`, SHA-256 `bee94fcd…7802aa`.
Inspected: `src/linger/services/memory.py`, `src/linger/agents/sculptor/`,
`src/linger/orchestration/curation.py`, `apps/backend/main.py` (memory routes),
`docs/specification.md` §4–6, §7.2.1; `tests/test_memory_{service,api}.py`,
`tests/test_sculptor_{agent,evals}.py`.

## Selected scenarios
`user_controlled_memory_lifecycle` · `bounded_memory_curation`

## Source decision — memory-only
Neither objective requires book evidence; every declared input resolves from
repository contracts or run state. Inspecting `data/corpus/` would be busywork.

## Verdict — **not ready**
Decisive reason: the project has adopted **no output contract** for backstories, props,
scenes, or lines. `synthetic-journal-coverage/` is empty and no schema exists in
`src/` or `apps/`. The prompt below carries a marked unresolved slot.

## Proposed generator prompt
```
You have read-only access to the current Linger checkout. Inspect these paths
at invocation time rather than trusting any summary of them:
  src/linger/services/memory.py         save, correction, deletion, versioning
  apps/backend/main.py                  non-conversational memory routes
  src/linger/agents/sculptor/models.py  allowed proposal types, input bounds

Write natural first-person journal material for one fictional person.

A. Source text for one explicit save; later replacement text that corrects its
meaning more clearly and accurately; then an intention to delete that record
and its earlier versions. Both wordings belong to the same person's history.
Express intent in the person's own words. Invent no account, event, or memory
identifiers.

B. A bounded group of reflections accumulated over time containing an exact
duplicate pair, related but distinct records, a later refinement, and unrelated
noise. Keep every reflection understandable on its own. Include one group that
warrants no reorganisation. Use natural repetition, never evaluator labels.

Avoid conversational phrases standing in for executed controls, and any
instruction about how the material should later be organised.

<<UNRESOLVED: output format, file layout, record schema. None is adopted.
Do not invent one.>>
```

## Representative Lines, hypotheses, evaluation
"Writing this down so I stop losing it: …" → save. Later: "That is not quite
what I meant — closer to …" → correction. Then: "Take that one out entirely."
Hypothesis: the two saves yield one active version with a preserved
supersession link; deletion removes the whole family. Curation Lines are not
conversational — a bounded batch yields exactly one typed proposal or an
explicit no-change. Measure control-event accuracy, version integrity, deletion
recall; curation precision and no-change accuracy. Treat response text as
hypothesis, not oracle.

## Architecture mapping
Deliberately agent-light. Lifecycle touches **no agent**: `POST/PUT/DELETE
/api/memories` reach `MemoryPolicyService` directly (`main.py:664,689,716`),
which alone owns identity, idempotency, immutable versions, and family-cascade
deletion. Curation adds one proposal-only agent with no tools, bounded to 2–12
records. **Muse, Librarian, Serendipity and Provenance are expected not to
participate at all** — that non-participation is itself the observable claim,
and it exercises the authority boundary in `docs/specification.md` §4.

## Academic alignment
Speaks to the briefing's questions on shared-memory common services and on
explainability and traceability (p.9), and feeds report sections on memory
mechanisms, responsible-AI governance, and testing and evaluation (p.13).
Deletion and correction under user authority are concrete accountability
evidence (p.11 success criteria). These are opportunities the artefacts invite,
not stated requirements.

## Gaps, risks, opportunity
1. **Proposals cannot be applied.** `docs/specification.md:141` has the Memory
   & Policy Service applying permitted derived changes; the service has no
   derived-summary, topic-group, or duplicate-link storage. Curation is
   proposal-only end to end today.
2. No scheduled or batch curation entry point exists; `propose_curation` has no
   caller in `apps/backend/`.
3. Unresolved output contract — see verdict.

*Developer inspiration, not adopted scope:* a Line correcting a memory that a
prior curation grouped, then deleting it, to test whether derived artefacts
follow the source. Smallest build-out: persist derived changes with source
references, and cascade them on delete. Not proposed for adoption here.

**Human decision required: approve, revise, or abandon this plan.**
