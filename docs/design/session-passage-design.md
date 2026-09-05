# Session-supported exact passages

## Problem

Muse could see earlier conversation messages, but private Librarian inference
received only the current message and saved memories. With memory capture off,
a reader could describe reaching a scene and then ask for a quotation from it,
yet receive another progress question. Passing history alone was insufficient:
the existing permission meant a completed chapter, which could expose later text.

## Usage

The chat workflow supplies original reader messages before running Muse:

```python
	statements = sessions.reader_statements(request.session_id)
	statements_token = set_reader_statements(statements)
	routing_token = set_routing_context()
	# Existing reflection execution runs inside the token setup/finally cleanup.
```

Muse still calls `librarian_route()` without arguments. The application passes
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
statement IDs, reading-support paragraph IDs, and requested paragraph IDs.
Librarian owns canonical window verification and paragraph decomposition.
Boundary orchestration validates every selected ID, work, revision, and
confidence before constructing `PassageGrant` from canonical records.

`PassageScope` contains only eligible IDs, work, and revision. Retrieval re-fetches
the exact grant records and requires full equality before strength review.
Only selected grounding records enter the turn evidence ledger. Private reading
anchors and neighboring paragraphs do not become public evidence automatically.

Release uses one current scope: a chapter `ReleaseScope` or a `PassageScope`.
An explicit chapter boundary wins over inferred passage permission. Both draft
and revision checks validate scope and canonical record equality. Provenance
receives passage IDs without a chapter ceiling and reviews the whole answer.
The existing exact previously released evidence exception remains unchanged.

Routing is computed once per turn behind a shared lock. Repeated or concurrent
route calls reuse that decision. Clarification takes precedence in the final
route-result reduction and blocks a subsequent search. No route can accumulate
more permission by asking again. Turn cleanup removes the grant. Only evidence
cited in a successfully released answer can be re-resolved in a later turn.

Passage permission never sets `ConfirmedReading`. Serendipity therefore gains
no book search from this path, and memory capture remains a separate policy.

## Synthesis decision

Two designs were compared: a dedicated passage extension and a replacement of
all reading authority with a chapter-or-passage union. The dedicated extension
was selected because confirmed chapter progress remains a useful distinct fact.
It adopts the other design's mutually exclusive release scope and shared
retrieval checks, without migrating chapter-specific connection contracts.

A second private judge or retrieval pass was rejected. One private discovery
and judgment can choose a chapter candidate, exact passages, or clarification.
Treating session messages as saved memories was also rejected because that
would erase their provenance and couple conversation continuity to capture.

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
