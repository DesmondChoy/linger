# Muse

Muse is Linger's conversation role. One reusable PydanticAI Agent,
`muse_chat_agent`, has one assigned runtime skill,
[`reflection`](skills/reflection/SKILL.md). Application orchestration selects
that skill for an initial draft and, when Provenance requests it, one revision.
Draft and revision are separate model runs on the same Agent object.

| Assigned skill | Typed input | Typed output | Current consumer |
| --- | --- | --- | --- |
| `reflection` | `MuseDraftInput` or `MuseRevisionInput` | `MuseCandidate` | `orchestration.reflection.reflection_reply`, called by production chat and synthetic replay |

[`skills.py`](skills.py) binds the selected instructions, contracts, permitted
tools, output validator, and retry limits. [`shared.md`](shared.md) contains
Muse's shared identity and authority rules. The Agent's base instructions
contain only that shared resource. The application supplies the selected skill
instructions on each run. All resources load from the package without depending
on the working directory. The [runtime skills architecture](../../../../docs/agent-skills.md)
describes the common assignment mechanism.

## Conversation and tool boundaries

The application supplies released conversation history, one typed current-turn
envelope, and any exact previously cited book records that it has re-resolved.
Muse can call `librarian_route`, `librarian_search`, and `serendipity_explore`
under application-owned source grants. The model chooses whether and how to
use those tools. Deterministic code controls identity, reading progress,
retrieval scope, and storage.

`MuseCandidate` contains the complete proposed reply, typed evidence
declarations, and either one exact current-reader-text memory nomination or a
typed decision not to nominate. Memory nominations carry no account scope or
write authority. Model-produced candidates, reader messages, memories, and
retrieved content remain untrusted data.

Muse retains a fixed output schema and its registered `validate_muse_output`
validator. The reflection skill does not override `output_type` per run.
Book evidence IDs, locations, and quotations are checked against the
application's request-scoped evidence map. The output validator can request
three repairs; tool calls retain one retry. These repairs do not count as the
application's single reviewed revision.

## Review and release

Provenance's `candidate-review` skill independently reviews each complete Muse
candidate with its isolated evidence and policy context. If the review requests
a revision, Muse receives the same reflection skill, released history, draft
messages, and response-scoped findings. The application allows one such rewrite
and reviews the rewritten candidate again.

After semantic approval, deterministic validation resolves every declared source
against the exact authorized record. Book quotations must match their source and
visible reply. Memory declarations must resolve to a current account record.
Web declarations must resolve to an opened page and include its exact URL as a
visible Markdown citation. Session-line declarations must quote earlier released
reader wording. The application either releases the reviewed candidate or
supplies its own clarification, emotional-boundary response, or safe decline.

The shared Agent stores no session, account, evidence, or release state. The
application deliberately constructs each run's message history and request
context. There is no direct Muse-to-storage or Muse-to-reader bypass.

## Evaluation and supported scope

The [Muse component pack](../../../../evals/muse/README.md) supplies five fixed
behavioral cases. Production chat and synthetic reflection, capture, connection,
and continuity replays exercise the same reflection skill. Component cases and
synthetic runs remain separate from independently adopted product evaluation
results. Photograph input remains an unimplemented product target.

[`prompt.py`](prompt.py) exports fingerprints of the effective shared and skill
instructions, relevant contracts, tool permissions, validator, and retry limits.
Draft and revision retain separate fingerprints because their input contracts
differ. `build_muse_agent(model)` and the reusable Agent's model override support
local tests and evaluation without changing production configuration.

Focused checks include `tests/test_muse_agent.py`,
`tests/test_muse_serendipity_skills.py`, `tests/test_reflection.py`, and chat and
synthetic replay tests. They cover typed output, retry repair, released history,
bounded revision, selected instructions, tool permissions, and concurrent
request isolation.
