# Registering books and resolving their names

Linger uses one reviewed book registry for explicit reading declarations,
Librarian routing, and identity checks on memories. The registry lives in
[`src/linger/corpus/registry.py`](../src/linger/corpus/registry.py). A book's
stable work ID comes from its registration; chat never manufactures an ID
from an unknown title.

The runtime registry and default application grant contain *Alice's Adventures
in Wonderland*, *Animal Farm*, and *The Adventures of Pinocchio*. Book retrieval
requires a validated chapter corpus, a registration, and an application grant
for its exact revision. An explicit `ALLOWED_BOOK_VERSION_IDS` environment value
replaces the default grant.

The repository also contains validated section corpora for *Narrative of the
Life of Frederick Douglass* and *The Story of My Life*. These books remain
disabled until the runtime supports section boundaries.

## Identity and ambiguity

Each `CorpusRegistration` contains a `BookCorpus`, its canonical directory,
and two optional name lists:

| Field | Meaning | Example |
|---|---|---|
| `aliases` | Reviewed, distinctive alternate names that can identify the work | `alice in wonderland` |
| `candidate_aliases` | Broad names that require the reader to identify the book | `wonderland` |

Application code normalizes capitalization, apostrophe variants, whitespace,
and surrounding punctuation. A longer name takes precedence over a shorter
name contained inside it. At the same position, a canonical title or work ID
takes precedence over an alias. Separate explicit book mentions remain
ambiguous; extra character or location cues cannot choose between them.
Books with the same title can be distinguished by their registered authors.

Explicit declarations and title-only answers use exact name matching, with an
optional `by Author` suffix. This also covers a title following a chapter number,
such as "I've finished Chapter 2 of The Orchard Notebook". Free-form Librarian
requests use the same resolver
to find reviewed names within the reader's original message. If there is no
name signal, Librarian can still use its existing catalogue cues. Multiple
qualifying catalogue candidates require clarification, even if their scores
differ. Candidate aliases never become strong memory-identity evidence.

Muse calls the argument-free `librarian_route` only when the reader's words
carry a book cue, such as a title, character, scene, or indirect follow-up to
the book conversation. An active book alone is not a reason to route an
unrelated reflection. The application supplies the original reader message
and caches one routing result for the turn, including concurrent calls.

When current-message routing finds no work, application code can use the
session's active selection if its revision remains allowed and no strong cue
contradicts it. A routed result records its deterministic `selection_basis` as
`resolved_book_identity`, `distinctive_cue`, or `session_selection`. This field
explains book selection; it does not establish reading progress.

An unresolved book declaration clears the previous selection, chapter
candidate, and pending chapter question. A typed identity clarification from `librarian_route` occurs before
private memory selection or full-work boundary inference. After Provenance
passes, application code releases the validated question instead of Muse's
wording. Evidence declarations and non-route tool calls still block release.
When no supported route is found,
Muse asks for a title and author if the answer requires a book, or continues
personal reflection when it does not.

Naming a book establishes identity only. A later title answer does not confirm
an earlier chapter guess. Retrieval still requires explicit current-turn
completion, a validated memory-supported boundary, or exact session-supported
passage permission. Application code enforces the permitted revision and the
chapter ceiling or exact passage IDs. Passage permission does not establish
chapter completion.

Private Librarian inference can grant up to five exact canonical paragraphs
when earlier reader statements support having read the requested scene. The
model identifies the earlier statement IDs, the paragraphs locating that
reading, and the exact requested paragraphs separately. The model assesses
whether the reader reports reading rather than curiosity, an adaptation,
second-hand information, or a reading plan. Application code
checks the supplied IDs, work, revision, and confidence before binding the
grant for the turn. Current-Line-only evidence cannot authorize the grant.
The supplied session context contains at most eight earlier reader messages
and 16,000 characters, preserving complete messages in a contiguous suffix.
The grant neither exposes surrounding paragraphs nor permits Serendipity book
search. Explicit completed-chapter context remains authoritative when present.

Routing returns no passage text. Muse uses the returned identifiers with
`librarian_search`, passing a completed `reading_boundary` for a `routed`
chapter result or `reading_boundary=None` for a `passages` result. The latter
search can return only the granted evidence IDs.

A reply such as "Chapter 3" establishes completed progress only when answering
a pending chapter question for that available book. Switching books discards
the previous book's pending question. A direct `librarian_search` call without
a boundary also checks identity from the original reader message or validated
session selection before it can leave a pending chapter question; Muse's tool
arguments cannot select the book by themselves.

## Add a book

Ask the [corpus-formatting skill](../.agents/skills/format-book-corpus/SKILL.md)
to "format and enable this book for Librarian" to include registration and
access in the same task. Formatting alone creates corpus artifacts without
changing runtime access. Adding a folder does not register or enable a book.
Reader uses the same registry and access grant: enabled chapter books appear on
its shelf automatically. No separate frontend book entry is required. Reader
navigation does not establish reading progress for chat.

1. Use the [corpus-formatting workflow](../.agents/skills/format-book-corpus/SKILL.md)
   to preserve the immutable source, create canonical chapters, and review
   semantic chapter metadata. Reuse the shared corpus lifecycle with a
   source-specific adapter. For an existing corpus, run its validation check
   without regenerating canonical files. Confirm that its units and locations
   match the chapter runtime before registration.
2. Add its `CorpusRegistration` in `src/linger/corpus/registry.py`. Keep stable
   identity and author information in `BookCorpus`. Classify broad or shared
   names as candidate aliases.
3. Run the registration check:

   ```bash
   uv run python -m src.linger.corpus.registry
   ```

   The check reports invalid keys or revision directories, empty or conflicting
   alias declarations, duplicate authoritative names, and aliases overlapping
   another book's title or candidate alias. Shared titles with distinct authors
   are supported, but require disambiguation at runtime. Shared candidate-only
   aliases are allowed. Resolve reported collisions by correcting metadata or
   making an ambiguous alternate name candidate-only.
4. Run the adapter's corpus check and the cross-book tests:

   ```bash
   uv run python -m src.linger.corpus.book your.adapter.module check
   uv run pytest tests/test_book_registry.py tests/test_librarian.py tests/test_book_context.py tests/test_librarian_route_e2e.py -q
   ```

   Cover the new book's reviewed names and relevant ambiguity cases. Verify
   denial without an exact revision grant and retrieval within the permitted
   chapter boundary. A title alone must not establish completed reading progress.
   The normal test suite also checks the shipped registry for registration errors.
5. Enable its exact revision in `allowed_book_version_ids` when the corpus is
   ready for use. The application defaults live in `apps/backend/config.py`.
   Inspect the target application's `ALLOWED_BOOK_VERSION_IDS` environment
   override, which is a JSON array of revision IDs. Add the revision to the
   effective grant while preserving existing grants. Registration alone does
   not bypass that access check.
6. Run the repository tests after changing registration and access. Restart the
   backend to load the updated registry and settings. Report the enabled work,
   exact revision, effective grant, and validation results.

Muse obtains identifiers from validated context and tool results. Each
registered book uses the shared prompt and routing implementation.

## Responsibility boundaries

![Shared book resolution and agent responsibilities](images/book-identity-and-agent-responsibilities.png)

The diagram shows chapter clarification carryover and application-owned
identity, session-state, and release checks. The separate offline Sculptor
step describes optional metadata proposals for human review.

| Owner | Responsibility |
|---|---|
| Human reviewer | Approves book identity, aliases, and semantic metadata |
| Deterministic corpus tooling | Preserves source bodies and IDs, validates canonical files, and derives `catalog.json` |
| Sculptor, optional offline assistance | Proposes semantic chapter metadata for review; does not write the catalogue or rewrite source bodies |
| Application code | Resolves identities, validates chapter authority, controls session state, enforces access, and releases replies |
| Muse | Decides when conversation needs a lookup, asks clarifying questions, and drafts replies |
| Librarian | Proposes an inferred boundary when needed and supplies evidence through the bounded retrieval service |
| Provenance | Runs safety preflight and reviews Muse's complete draft; cannot grant access or release a reply itself |
| Serendipity | Proposes connections; does not own catalogue construction or book identity |

The catalogue remains a deterministic projection of canonical chapter metadata.
Reviewed book aliases live in the registry, not in model-generated catalogue
JSON. Runtime Sculptor handles memory curation. Book registration is a reviewed
source-code workflow and does not accept arbitrary uploads or fuzzy name matches.

## Mixed literary sections

Works with letters and prefatory material use the
[canonical section format](corpus/canonical-sections.md). *Narrative of the Life
of Frederick Douglass* and *The Story of My Life* use schema 2 section artifacts.
The chapter-based runtime rejects section metadata, including a section file
placed beneath a chapter catalogue. Section IDs and section reading boundaries
need separate runtime implementation before these books can be enabled. Keep
their natural units intact. Relabeling sections as chapters would discard the
meaning of their locations and reading boundaries.
