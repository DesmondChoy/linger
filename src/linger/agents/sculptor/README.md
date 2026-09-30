# Sculptor

Sculptor owns one reusable PydanticAI object, `sculptor_agent`, with two
application-selected skills. Both produce proposals. A separate model run
selects each task's instructions and output schema from
[`skills.py`](skills.py).

| Skill | Typed input and output | Entry point and current consumer |
|---|---|---|
| [Memory curation](skills/memory-curation/SKILL.md) | `AccountScopedMemories` → `SculptorResponse` | `propose_curation` is used by the callable reviewed curation loop and bounded-curation evaluation. |
| [Memory surfacing](skills/memory-surfacing/SKILL.md) | `SurfacingInput` → `SurfacingDecision` | `propose_surfacing` supports offline evaluation only. Chat never runs it, and it has no scheduling or notification consumer. |

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

Both skills have no tools and retain one output retry. Shared instructions in
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
