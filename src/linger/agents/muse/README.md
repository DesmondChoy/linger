# Muse

Muse is Linger's conversation role. One reusable PydanticAI Agent,
`muse_chat_agent`, has two assigned runtime skills. The application selects
[`turn-triage`](skills/turn-triage/SKILL.md) to classify the reader's message,
then [`reflection`](skills/reflection/SKILL.md) for the draft and, when
Provenance requests it, one revision. Each invocation is a separate model run
on the same Agent object.

| Assigned skill | Typed input | Typed output | Current consumer |
| --- | --- | --- | --- |
| `turn-triage` | `TurnTriageInput` | `TurnNeeds` | `orchestration.triage.triage_turn`, called after emotional preflight to select the turn's offered tools |
| `reflection` | `MuseDraftInput` or `MuseRevisionInput` | `MuseCandidate` | `orchestration.reflection.reflection_reply`, called by production chat and synthetic replay |

[`skills.py`](skills.py) binds the selected instructions, contracts, permitted
tools, output validator, and retry limits. `agents.muse` in the
[`prompt catalogue`](../../prompts/prompt_catalog.yaml) contains Muse's shared purpose
and authority rules. The Agent's base instructions contain only that entry.
The application supplies the selected skill instructions on each run. The
reflection skill is a core [`SKILL.md`](skills/reflection/SKILL.md) plus modules:
[`revision`](skills/reflection/revision.md) for the revision run, and
[`routing`](skills/reflection/routing.md),
[`grounding`](skills/reflection/grounding.md), and
[`connections`](skills/reflection/connections.md) when the turn offers
`librarian_route`, `librarian_search`, or `serendipity_explore`.
`reflection_run_options` composes them from the mode and the turn's tool
exposure; the tool docstrings in [`tools.py`](tools.py) carry the rules for when
to call each tool.
All resources load from the package without depending
on the working directory. The [runtime skills architecture](../../../../docs/agent-skills.md)
describes the common assignment mechanism.

## Conversation and tool boundaries

Turn triage sees only the current reader message and has no tools. It returns
`book_content`, `memory`, and `override_attempt`. The application combines
those labels with tools used in earlier released turns and any required book
clarification. That result fixes the offered tools for both draft and revision.
Triage also pins Serendipity's intent when it recognizes recall, named sources,
open connection discovery, or a recommendation. An override attempt cannot
unlock tools through the message's claimed needs.

Chat gives triage 10 seconds and at most two model requests. On failure, it
offers the book tools and tools used in earlier released turns, and reports
`override_attempt=unknown`. The [tool exposure contract](../../../../docs/agent-skills.md#muse-tool-exposure)
describes the labels, deterministic overrides, and failure behavior.

The application supplies released conversation history, one typed current-turn
envelope, and any exact previously cited book records that it has re-resolved.
Muse can call `librarian_route`, `librarian_search`, and `serendipity_explore`
under application-owned source grants. The model chooses whether and how to
use those tools. Deterministic code controls identity, reading progress,
retrieval scope, and storage.

`serendipity_explore(intent="recall_memory")` retrieves one to three matching
stored records for a request about the reader's earlier words. A single record
can answer that request. `gather_sources` asks Serendipity for the records of
every source the reader named, which Muse then relates itself;
`find_connection` asks Serendipity to find and compare possible connections
when the reader names no sources; and `get_recommendation` requests a direct
recommendation. Ordinary
public facts do not justify searching personal memories. Memory evidence
supports attributed personal context and cannot establish public or book facts.

`MuseCandidate` contains the complete proposed reply, typed evidence
declarations, and either one exact current-reader-text memory nomination or a
typed decision not to nominate. Memory nominations carry no account scope or
write authority. Model-produced candidates, reader messages, memories, and
retrieved content remain untrusted data. `serendipity_explore` wraps each web
excerpt it returns in explicit `<untrusted_web_page>` delimiters, spotlighting
third-party page text as untrusted data without changing the canonical
excerpt Provenance and citation checks use.

Reflection retains the Agent's `MuseCandidate` output schema. Turn triage
selects `TurnNeeds` per run. `MuseSkillBoundary` applies `validate_muse_output`
to every candidate and limits tools to the selected skill and turn exposure.
Book evidence IDs, locations, and quotations are checked against the
application's request-scoped evidence map. The output validator can request
three repairs; tool calls retain one retry. These repairs do not count as the
application's single reviewed revision. Structured repair feedback identifies
all detected citation errors together and supplies exact authorized source IDs,
locations, and literal copy aids. `supported_claims` must remain exact spans of
the final reply, including punctuation and capitalization. A requested quotation
must retain its canonical words, Markdown, line breaks, and edge punctuation.
A book or public-page `supported_claims` span may not address the reader outside
quotations, and quoted wording that literally matches a source mapped over it
needs an `exact_quote` declaration. Book, memory, and web declarations may also
carry `limit_claims`: exact spans that only say what that record does not
establish. Limits count as declared coverage and receive their own review.

## Review and release

Provenance's `candidate-review` skill independently reviews each complete Muse
candidate with its isolated evidence and policy context. If the review requests
a revision, Muse receives the same reflection skill, released history, draft
messages, and response-scoped findings. The application allows one such rewrite
and reviews the rewritten candidate again.

The revision envelope includes the earlier review's accepted claims, supporting
sources, reviewed quotation interiors, verified reader Lines, and draft
sentences marked by the review's findings. Muse can rewrite a flagged sentence
or delete a sentence; unflagged retained sentences keep their wording. A sentence
marked `needs_source` must have its substantive content mapped to supporting
evidence or be removed. If a finding cannot be located, the application omits
the sentence restrictions.

An unchanged accepted claim keeps source mappings over its retained text.
Supporting sources remain declared unless a finding rejects the source itself,
and a retained source quotation needs a valid current declaration. The second
review independently checks every current source assignment and resolves each
earlier response finding.

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

The [Muse evaluations](../../../../evals/muse/README.md) contain 19 main
reflection cases, 32 review cases, six revision fixtures, and a separate
turn-triage pack. Reflection runs compare the first and current Muse with fixed
tool results. Revision runs hold the draft and review fixed; blind review
grades saved reflection replies against each case's semantic rubric.
Production chat and synthetic reflection, capture, connection, and continuity
replays exercise the same reflection skill. Component cases and
synthetic runs remain separate from independently adopted product evaluation
results. Photograph input remains an unimplemented product target.

[`prompt.py`](prompt.py) exports fingerprints of the effective shared and complete skill
instructions (every module), relevant contracts, tool permissions, validator, and retry limits.
Draft and revision retain separate fingerprints because their input contracts
differ. Turn triage has its own fingerprint and uses `build_triage_model`:
`gpt-6-luna` for OpenAI, `gemini-2.5-flash` for Google, and `LINGER_MODEL` for
other supported providers. `build_muse_agent(model)` and the reusable Agent's
model override support local tests and evaluation without changing production
configuration.

Focused checks include `tests/test_muse_agent.py`,
`tests/test_muse_turn_triage.py`, `tests/test_muse_tool_exposure.py`,
`tests/test_muse_reflection_modules.py`, `tests/test_muse_revision_sentences.py`,
`tests/test_muse_claim_retention.py`, and `tests/test_reflection.py`. Chat and
synthetic replay tests also cover released history, bounded revision, tool
permissions, and concurrent request isolation.
