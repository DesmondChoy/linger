# Sculptor

Sculptor owns one reusable PydanticAI object, `sculptor_agent`, with two
application-selected skills. Both produce proposals. A separate model run
selects each task's instructions and output schema from
[`skills.py`](skills.py).

| Skill | Typed input and output | Entry point and current consumer |
|---|---|---|
| [Memory curation](skills/memory-curation/SKILL.md) | `AccountScopedMemories` → `SculptorResponse` | `propose_curation` is used by the callable reviewed curation loop and bounded-curation evaluation. |
| [Memory surfacing](skills/memory-surfacing/SKILL.md) | `SurfacingInput` → `SurfacingDecision` | `propose_surfacing` supports offline component evaluation. It has no production scheduling or notification consumer. |

Curation receives two to twelve existing memories selected for one account.
The model sees only their IDs and text. It proposes a duplicate link, derived
summary, topic group, retrieval tombstone, retrieval restore, or no change.
Strict schemas and application validation reject malformed proposals and IDs
outside the supplied batch. The callable `run_curation_loop` asks Provenance
to review a digest-bound plan before the Memory & Policy Service can apply it.
The service checks account scope, source hashes, and current curation state.
This workflow is separate from conversation turns.

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

Offline surfacing scores do not establish the conversational
`proactive_memory_surfacing` Objective. That target also requires reviewed
capture, applied curation, later memory use in a fresh session, and reviewed
response release. Scheduled operational playbooks remain unimplemented.

See the [runtime architecture](../../../../docs/agent-skills.md),
[Sculptor design](../../../../docs/design/sculptor-design.html), and
[Sculptor evaluations](../../../../evals/sculptor/README.md).
