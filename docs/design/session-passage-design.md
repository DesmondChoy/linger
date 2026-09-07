# Session-supported exact passages

## Scope

Private Librarian inference receives the current reader message, bounded
original reader statements from the session, and eligible saved memories.
A reader can describe reaching a scene and ask for a quotation from it with
memory capture off. Exact passage permission supports this request without
granting access to the rest of the chapter.

## Usage

The chat workflow supplies original reader messages before running Muse:

```python
	statements = sessions.reader_statements(request.session_id)
	statements_token = set_reader_statements(statements)
	routing_token = set_routing_context()
	# Reflection execution runs inside the token setup/finally cleanup.
```

Muse calls `librarian_route()` without arguments when the reader's words carry
a book cue. An active book selection alone does not justify a route call.
The application passes
the original current message and the reader-history snapshot to private
inference. A `passages` result names the work, immutable revision, and eligible
paragraph IDs. Muse requests grounding through the existing tool:

```python
	await librarian_search(
		query=reader_question,
		work_id=route.work_id,
		book_version_id=route.book_version_id,
		reading_boundary=None,
	)
```

The query can affect relevance, not permission. Even a larger chapter argument
cannot extend the exact eligible paragraphs.

## Shape and ownership

`ReaderStatement` contains a source ID and complete original text. Sessions
derives the latest eight retained reader messages under a 16,000-character
budget, with stable reader ordinals and no second content store. It keeps a
contiguous recent suffix rather than skip a large intervening message that
could contain a correction. An oversized latest message yields no history.

`PassageInferenceDecision` is private model output. It separates earlier reader
statement IDs, reading-support paragraph IDs, and requested paragraph IDs, and
declares its own `authorization_basis` of `session_supported` or `line_only`.
Librarian owns canonical window verification and paragraph decomposition.
Boundary orchestration validates every selected ID, work, revision, and
confidence before constructing `PassageGrant` from canonical records; it
rejects any `line_only` decision and any cited statement that does not itself
strongly identify the work through reviewed names or distinctive catalogue
cues. Weak, incidental, or ambiguous references fail this deterministic check.
The private model separately judges whether those statements establish that
the reader has reached each requested passage.

`PassageScope` contains only eligible IDs, work, and revision. Retrieval re-fetches
the exact grant records and requires full equality before strength review.
Only selected grounding records enter the turn evidence ledger. Private reading
anchors and neighboring paragraphs do not become public evidence automatically.

Release uses one current scope: a chapter `ReleaseScope` or a `PassageScope`.
An explicit chapter boundary wins over inferred passage permission. Both draft
and revision checks validate scope and canonical record equality. Provenance
receives passage IDs without a chapter ceiling and reviews the whole answer.
Exact evidence cited in a previously released reply has a separate reuse
exception.

Routing is computed once per turn behind a shared lock. Repeated or concurrent
route calls reuse that decision. Clarification takes precedence in the final
route-result reduction and blocks a subsequent search. No route can accumulate
more permission by asking again. Turn cleanup removes the grant. Only evidence
cited in a successfully released answer can be re-resolved in a later turn.

Passage permission never sets `ConfirmedReading`. Serendipity therefore gains
no book search from this path, and memory capture remains a separate policy.

## Design rationale

Passage permission is a dedicated extension because confirmed chapter progress
is a distinct fact. Mutually exclusive release scopes and shared retrieval
checks keep the two permissions separate without changing chapter-specific
connection contracts.

One private discovery and judgment can choose a chapter candidate, exact
passages, or clarification. Session statements retain their original provenance
and remain separate from saved memories, so continuity does not depend on
capture.

## Limits and verification

Canonical paragraph identity is deterministic. Whether the reader has actually
read that paragraph is a model judgment. Curiosity, adaptations, second-hand
mentions, conflicting progress, and inseparable unreached material must produce
uncertainty rather than permission. General partial-chapter ceilings remain
unsupported. A paragraph grant does not imply knowledge of its whole scene.

The local regressions cover original history handoff, canonical paragraph
isolation, exact fetch, draft and revision release, neighboring-text rejection,
clarification precedence, and Serendipity isolation. The two-message Alice
regression runs the production chat workflow with stubbed model decisions and
memory capture off. It proves the application handoffs, not live model judgment.
Existing synthetic chapter objectives explicitly reject passage outcomes as
outside their ground-truth contract rather than invent a chapter ceiling.
